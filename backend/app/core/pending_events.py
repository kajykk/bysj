"""事务提交后再发布事件（M14 修复，2026-10-20 ROUND_19）。

问题（审查报告 M14）
-------------------
``warning.created`` 原先在 ``_check_warning_trigger`` 里 ``flush()`` 之后立即发布，
而 ``commit()`` 由调用方稍后执行。后果：

1. 订阅方用**独立 session** 回查 ``warning_id`` 时读到空行（行还没提交）；
2. 若事务随后回滚（如同一评估流程里的后续步骤失败），**事件已发、数据不存在** ——
   指标与推送口径出现"幽灵预警"。

同仓 ``review_service`` 的既有做法是"先 commit 再 publish"，但那是单点写法；
``_check_warning_trigger`` 有 3 个调用方（``risk_service`` / ``user_data_service`` /
``model_predict._common``），提交时机各不相同，不能在服务层各自记得" publish 前先
commit"。

做法
----
用 SQLAlchemy 的 ``after_commit`` 会话事件：服务层只**登记**事件，
事务真正提交后由钩子统一发布；回滚则事件随事务一起消失（永不发布）。

边界
----
- 登记在 ``session.sync_session``（AsyncSession 的同步 Session）上，
  用 ``WeakKeyDictionary`` 持有，避免 ``id()`` 复用导致跨会话串话；
- ``after_rollback`` 同步丢弃该会话的待发布事件 —— 回滚的事务不配发事件；
- 发布走 ``event_bus.publish_sync``（``put_nowait``，非阻塞），
  故同步钩子里不会引入 await；
- 登记本身不改变任何既有事务语义，也不新增静默降级路径：
  发布失败（队列满）的记账仍在 ``event_bus`` 内。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.event_bus import event_bus

if TYPE_CHECKING:  # pragma: no cover - 仅类型标注
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# sync_session -> [(event_type, data), ...]
_PENDING: "WeakKeyDictionary[Session, list[tuple[str, dict[str, Any]]]]" = (
    WeakKeyDictionary()
)


def _drain(session: Session) -> list[tuple[str, dict[str, Any]]]:
    return _PENDING.pop(session, [])


@event.listens_for(Session, "after_commit")
def _publish_after_commit(session: Session) -> None:
    """事务提交后发布本会话登记的事件（M14）。

    回滚的事务不会触发本钩子 ⇒ 订阅方永远看不到未提交/已回滚的事件。
    """
    events = _drain(session)
    for event_type, data in events:
        try:
            event_bus.publish_sync(event_type, data)
        except Exception:  # pragma: no cover - publish_sync 内部已兜住队列满
            logger.warning(
                "after_commit 发布事件失败: %s", event_type, exc_info=True
            )


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    """事务回滚 ⇒ 丢弃本会话登记的事件（永不发布）。"""
    dropped = _drain(session)
    if dropped:
        logger.info(
            "after_rollback 丢弃 %d 个待发布事件（事务未提交，事件不发出）",
            len(dropped),
        )


def schedule_after_commit(
    db: AsyncSession, event_type: str, data: dict[str, Any]
) -> None:
    """登记一个事件，待 ``db`` 当前事务提交后发布（M14）。

    用法::

        schedule_after_commit(self.db, "warning.created", {...})

    注意：事件在**提交之后**才发，因此同一调用栈里若紧接着读总线是读不到的
    （用例见 ``tests/test_p2_47_round19_m_batch2.py`` 的 M14 段）。
    """
    sync_session = db.sync_session
    _PENDING.setdefault(sync_session, []).append((event_type, data))
