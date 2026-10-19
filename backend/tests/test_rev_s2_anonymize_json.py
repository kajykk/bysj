"""REV-2026-10-20 S2 回归：GDPR 匿名化写入的危机关键词必须是合法 JSON 数组。

缺陷链条（改前）：
- 写入侧 ``gdpr_service_anonymize._step_anonymize_pii_texts`` 把
  ``CrisisEvent.crisis_keywords``（JSON 数组文本列）写成 ``ANON_TEXT``
  即 ``"[ANONYMIZED]"``；
- 读取侧 ``review_service`` 直接 ``json.loads`` 且无 try/except；
- 结果：任何用户行使被遗忘权后，其历史危机事件让**同租户所有管理员**的
  危机事件列表整页 500，且数据已落库、重启不自愈。

本文件的两条断言分别钉住「写」与「读」：
1. 走真实 ``_step_anonymize_pii_texts`` 之后，列值是合法 JSON 数组、
   ``handled_action`` 不再落在 ``_ALLOWED_CRISIS_ACTIONS`` 之外；
2. 存量脏行（旧版匿名化产物）能让列表正常返回，坏行降级为 ``[]``。

为什么必须跨模块：写入侧与读取侧各自单测都能绿，但契约不成立（附录 C）。
"""

from __future__ import annotations

import json

from app.models.review import CrisisEvent
from app.models.user import User
from app.schemas.review import CrisisEventFilter
from app.services.review_service import CrisisEventService, _ALLOWED_CRISIS_ACTIONS


def _mk_user() -> User:
    from app.core.pii_crypto import compute_blind_index
    from app.core.security import get_password_hash

    email = "rev_s2@test.com"
    return User(
        id=9001,
        username="rev_s2_student",
        email=email,
        email_hash=compute_blind_index(email, "email"),
        password_hash=get_password_hash("testpass123"),
        role="user",
        status="active",
        tenant_id=1,
    )


async def test_anonymize_writes_valid_json_and_clear_action(db_session):
    """匿名化写出的危机关键词必须是 JSON 数组，处置动作不得破坏枚举语义。"""
    from app.services.gdpr_service import GDPRService

    db_session.add(_mk_user())
    await db_session.flush()

    event = CrisisEvent(
        user_id=9001,
        trigger_source="text",
        crisis_keywords=json.dumps(["自杀", "自伤"], ensure_ascii=False),
        input_summary="我想结束这一切",
        handled_action="escalate",
        status="escalated",
    )
    db_session.add(event)
    await db_session.commit()

    service = GDPRService(db_session)
    counts = await service._step_anonymize_pii_texts(9001)
    assert counts["crisis_events"] == 1
    await db_session.flush()

    stored = await db_session.get(CrisisEvent, event.id)
    assert stored is not None

    # 1) 列语义：可被 json.loads 解析为 list（改前是 "[ANONYMIZED]"，这里会抛）
    parsed = json.loads(stored.crisis_keywords)
    assert isinstance(parsed, list)
    # 2) 不残留任何危机关键词原文（被遗忘权）
    assert "自杀" not in stored.crisis_keywords
    assert "自伤" not in stored.crisis_keywords
    # 3) handled_action 若保留必须仍在白名单内；当前实现置空
    assert stored.handled_action is None or stored.handled_action in _ALLOWED_CRISIS_ACTIONS
    # 4) 原文摘要已脱敏
    assert stored.input_summary != "我想结束这一切"


async def test_anonymized_event_still_listable(db_session):
    """匿名化之后，同租户管理员仍能正常列出危机事件（不 500）。"""
    from app.services.gdpr_service import GDPRService

    db_session.add(_mk_user())
    await db_session.flush()
    db_session.add(
        CrisisEvent(
            user_id=9001,
            trigger_source="text",
            crisis_keywords=json.dumps(["自杀"], ensure_ascii=False),
            handled_action="notify_counselor",
            status="reviewed",
        )
    )
    await db_session.commit()

    await GDPRService(db_session)._step_anonymize_pii_texts(9001)
    await db_session.commit()

    page = await CrisisEventService(db_session).get_crisis_events(
        CrisisEventFilter(page=1, page_size=20), tenant_id=1
    )
    assert page["total"] == 1
    assert page["items"][0]["crisis_keywords"] == []


async def test_legacy_dirty_row_is_tolerated(db_session):
    """存量脏行（旧版匿名化写入的 "[ANONYMIZED]"）不得打挂整页。

    改前 ``json.loads`` 无容错，单条坏行让列表推导整体抛 JSONDecodeError。
    """
    db_session.add(_mk_user())
    await db_session.flush()
    dirty = CrisisEvent(
        user_id=9001,
        trigger_source="legacy",
        crisis_keywords="[ANONYMIZED]",
        status="detected",
    )
    healthy = CrisisEvent(
        user_id=9001,
        trigger_source="text",
        crisis_keywords=json.dumps(["自伤"], ensure_ascii=False),
        status="reviewed",
    )
    db_session.add_all([dirty, healthy])
    await db_session.commit()

    page = await CrisisEventService(db_session).get_crisis_events(
        CrisisEventFilter(page=1, page_size=20), tenant_id=1
    )

    assert page["total"] == 2
    by_source = {item["trigger_source"]: item for item in page["items"]}
    # 坏行降级为 []，正常行保持原值
    assert by_source["legacy"]["crisis_keywords"] == []
    assert by_source["text"]["crisis_keywords"] == ["自伤"]
