"""SEC-FIX-2026-10-05: 告警升级状态机 P1→P0 卡死回归测试.

缺陷:
    compute_escalation 的 severity 取自 ``detail["severity"]``（escalation.py:81），
    但 P1→P0 升级分支只写 ``escalation_level=1``，**从不回写 severity**。

    于是升级后 severity 仍是 "P1"，下一轮判定全部落空:
      - 第 85 行 ``severity == "P1"`` 因 ``escalation_level < 1`` 不成立被跳过；
      - 第 95/105 行的 ``severity == "P0"`` 判定**永假**。

    后果: P1 告警在 10 分钟升级为 level=1 后**永久停滞**，
    docstring 承诺的「30 分钟未确认 P0 → 再次通知」与
    「1 小时 → 记录 OperationLog 合规追踪」**永不发生** ——
    已升级的告警从此静默，无人再被提醒。
    这是 P1 告警的**默认路径**，不是边界情况。

为什么既有测试没抓到:
    tests/test_escalation.py 的 29 项测试全部是**单点判定** ——
    每次都直接 ``_make_alert(severity="P1"/"P0", age_minutes=..., escalation_level=...)``,
    从不把上一步的 decision.detail 喂回下一轮。于是每一步单独看都「正确」，
    串起来才暴露卡死。本文件按真实的多轮时间推进来驱动状态机。

修复:
    1. compute_escalation 的 P1→P0 分支在 detail 中一并写入 ``severity: "P0"``；
    2. apply_escalation 落库时以 ``new_severity`` 为准兜底提升 severity。

关于确定性时钟（flake 修复）:
    本文件初版用 ``datetime.now()`` 作为基准，且在 ``_drive`` 的每轮里
    **各调一次** ``_now()``（一次构造 alert 的 created_at，一次作为
    compute_escalation 的 now）。于是实际 age = 目标值 + (T2 - T1)，
    其中 T2-T1 是两行代码的执行耗时。escalation 恰好是 10min/30min/1h
    的**阈值边界逻辑**，多轮驱动时若某个"目标值"贴着阈值（31min vs 30min、
    61min vs 60min），就会在慢机器或高负载下随机翻转 → CI 间歇性红。

    改为以固定基准时刻 ``_T0`` 构造所有时间：created_at 由 _T0 推导，
    now 也由 _T0 推导，两者关系完全确定，与机器性能和执行顺序无关。
    DB 往返导致的 created_at 精度截断也因余量放大到分钟级而不受影响。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.models.admin import OperationLog
from app.monitoring.escalation import ESCALATION_THRESHOLDS, EscalationDecision, compute_escalation

# 固定基准时刻（naive UTC，与被测代码的 naive 约定一致）。
# 用它替代 datetime.now() 是本文件确定性化的关键 —— 见模块 docstring「关于确定性时钟」。
_T0 = datetime(2026, 10, 5, 12, 0, 0)


def _now() -> datetime:
    """固定基准时刻（naive UTC）。

    ⚠️ 必须是**固定值**而非 datetime.now()：escalation 是 10min/30min/1h 的
    阈值边界逻辑，用真实时钟会让"恰好贴着阈值"的用例随机翻转（flake）。
    所有需要体现"时间推进"的场景都应通过 _at() 显式给出时刻。
    """
    return _T0


def _at(minutes_after_t0: float) -> datetime:
    """基准时刻 _T0 之后若干分钟 —— 显式表达"多轮时间推进"."""
    return _T0 + timedelta(minutes=minutes_after_t0)


def _alert(
    age_minutes: float,
    detail: dict[str, Any],
    alert_id: int = 1,
    at: datetime | None = None,
) -> Any:
    """构造一条 alert_fired 的 OperationLog（不落库，纯内存对象）.

    Args:
        age_minutes: 告警触发至今的分钟数（相对 ``at``）
        detail: 该时刻的告警 detail（决定 severity / escalation_level）
        alert_id: 行 id
        at: 判定时刻，缺省为基准 _T0。created_at = at - age_minutes，
            这样 age 精确等于 age_minutes，不受执行耗时影响。
    """
    now = at if at is not None else _T0
    return OperationLog(
        id=alert_id,
        operator_id=None,
        operator_role="system",
        action_type="alert_fired",
        target_type="alert",
        target_id=None,
        detail=json.dumps(detail, ensure_ascii=False),
        created_at=now - timedelta(minutes=age_minutes),
    )


def _p1_detail() -> dict[str, Any]:
    return {
        "rule": "HighErrorRate",
        "severity": "P1",
        "fingerprint": "fp-1",
        "labels": {"alertname": "HighErrorRate"},
        "annotations": {},
        "message": "err",
    }


def _drive(alert_age_minutes: float, rounds: list[float]) -> list[EscalationDecision]:
    """按给定时间点序列驱动状态机，模拟 Celery beat 的多轮扫描.

    每轮: 用上一轮 decision.detail 作为新的 detail（与 apply_escalation 落库后的
    真实行为一致），模拟真实的时间推进。

    告警固定在 _T0 触发（created_at = _T0 - alert_age_minutes），
    每一轮判定时刻为 _T0 + round_minutes。这样每轮的 age **精确等于**
    round_minutes，与执行耗时、机器负载完全无关（确定性，见模块 docstring）。

    Args:
        alert_age_minutes: 告警触发至今的分钟数（相对 _T0，固定）
        rounds: 每一轮判定时「距告警触发」的分钟数序列

    Returns:
        每一轮的决策列表
    """
    detail = _p1_detail()
    created_at = _T0 - timedelta(minutes=alert_age_minutes)
    out: list[EscalationDecision] = []
    for age in rounds:
        a = _alert(0, detail, at=_T0)
        # created_at 固定，覆盖成告警真实触发时刻，使 age 精确 = age
        a.created_at = created_at
        d = compute_escalation(a, _T0 + timedelta(minutes=age))
        out.append(d)
        if d.should_escalate and d.detail is not None:
            detail = dict(d.detail)  # 落库：下一轮读到的是新 detail
    return out


class TestP1EscalationStateMachine:
    """P1 告警的完整升级链路 —— 这是缺陷真正发生的地方."""

    def test_p1_detail_severity_promoted_on_escalation(self) -> None:
        """核心断言: P1→P0 升级时 detail['severity'] 必须变成 "P0".

        这是修复的直接目标。原实现只写 escalation_level，severity 仍是 "P1"。
        """
        a = _alert(10, _p1_detail())
        d = compute_escalation(a, _now())

        assert d.should_escalate is True
        assert d.new_severity == "P0"
        assert d.detail is not None
        assert d.detail["escalation_level"] == 1
        # 关键: severity 必须被提升
        assert d.detail["severity"] == "P0", (
            f"升级后 severity 仍为 {d.detail.get('severity')!r} —— "
            "下一轮 severity=='P0' 判定会永假，状态机卡死"
        )

    def test_p1_escalated_alert_is_not_stuck(self) -> None:
        """回归: P1 升级到 level=1 后，后续必须能继续升级（不卡死）.

        这是缺陷的行为表现：升级后 t=31/61/120/240 分钟全部 should_escalate=False。

        阈值余量说明: 判定时刻刻意避开阈值边界（10/30/60min）——
        用 11/35/65/120/240，确保即使 created_at 有微秒级截断也不会翻转。
        """
        # created_at 距 _T0 240 分钟（足够覆盖全部阈值）
        # 依次在 11 / 35 / 65 / 120 / 240 分钟处判定
        decisions = _drive(240, [11, 35, 65, 120, 240])

        assert decisions[0].should_escalate is True, "11 分钟应首次升级"
        assert decisions[0].detail["escalation_level"] == 1

        # 关键断言：35 分钟应触发 P0 重复通知（level=2）
        assert decisions[1].should_escalate is True, (
            "P1 升级后 35 分钟应触发 P0 重复通知 —— "
            "若为 False，说明 severity 未回写，状态机已卡死"
        )
        assert decisions[1].detail["escalation_level"] == 2

        # 65 分钟应到 level=3 (P0-1h 合规追踪)
        assert decisions[2].should_escalate is True
        assert decisions[2].detail["escalation_level"] == 3

        # 已达最高级，后续不再升级
        assert decisions[3].should_escalate is False
        assert decisions[4].should_escalate is False

    def test_escalation_level_monotonic_increase(self) -> None:
        """升级级别必须单调递增到 3 并停住，不出现回退或跳空."""
        decisions = _drive(300, [11, 12, 35, 36, 65, 66, 120, 240])

        levels = [d.detail["escalation_level"] for d in decisions if d.should_escalate]
        assert levels == sorted(levels), f"升级级别非单调: {levels}"
        assert max(levels) == 3, f"应升到最高级 3, 实际 {levels}"

    def test_reason_reflects_later_stages(self) -> None:
        """后续轮次的 reason 应体现 P0 阶段，而非停留在 P1 阶段."""
        decisions = _drive(240, [11, 35, 65])

        assert "P1" in decisions[0].reason
        # 第二轮起应体现 P0 相关语义
        assert "P0" in decisions[1].reason or "repeat" in decisions[1].reason
        assert "P0-1h" in decisions[2].reason


class TestThresholdBoundaryDeterminism:
    """阈值边界的确定性 —— 这组用例当初正是 flake 的来源.

    escalation 的判定全是 `age >= 阈值` 形式（10min / 30min / 1h）。
    初版测试用 datetime.now() 且在多轮驱动中每轮各调一次 _now()，
    实际 age = 目标值 + 执行耗时，导致「恰好贴着阈值」的用例在慢机器上
    随机翻转。现已改为固定基准时钟，本类用例锁定边界语义不再漂移。
    """

    def test_exact_threshold_triggers(self) -> None:
        """age **恰好等于**阈值时应触发（`>=` 而非 `>`）."""
        t_p1 = ESCALATION_THRESHOLDS["P1_to_P0"].total_seconds() / 60
        assert t_p1 == 10
        a = _alert(10, _p1_detail(), at=_at(10))
        # 显式确认构造正确: age 必须精确等于 10min（否则下面的断言无意义）
        assert (a.created_at is not None) and (_at(10) - a.created_at) == timedelta(minutes=10)
        d = compute_escalation(a, _at(10))
        assert d.should_escalate is True, "age 恰等于 10min 应触发 P1→P0"

    def test_just_below_threshold_does_not_trigger(self) -> None:
        """age 略小于阈值时不应触发.

        ⚠️ 两个必须注意的构造要点（初版都踩了）:
        1. age 必须与 `at` 联动 —— `_alert(age_minutes, ..., at=X)` 的语义是
           created_at = X - age_minutes，compute_escalation 的 now 也传 X。
           若 at 与 age_minutes 不匹配，实际 age 会是两者之差。
        2. `age_minutes` 的单位是**分钟**。阈值 P1_to_P0 = 10min = 10 分钟，
           而 timedelta(minutes=10) 是 10 分钟 —— 但若误写成
           `10 * 60 - 0.000001/60`（当成秒换算），实际 age 会变成 599.99 分钟，
           远超阈值 → 反而触发升级。表现为 reason 里显示 "599min"。
           正确写法是 `10 - 1e-6/60`（从 10 分钟里减 1 微秒）。
        """
        # 判定时刻固定在 _at(75)，告警 created_at 比它早 (10min - 1µs)
        just_under = 10 - 0.000001 / 60  # 分钟（= 10min - 1µs）
        a = _alert(just_under, _p1_detail(), at=_at(75))
        # 显式确认构造正确: age 必须精确等于 just_under 分钟（否则断言无意义）
        actual_age = _at(75) - a.created_at  # type: ignore[operator]
        assert abs(actual_age - timedelta(minutes=just_under)) < timedelta(microseconds=1), (
            f"构造错误: 实际 age={actual_age}, 期望≈{timedelta(minutes=just_under)}"
        )
        d = compute_escalation(a, _at(75))
        assert d.should_escalate is False, (
            f"age 略小于 10min 不应升级, 实际 reason={d.reason!r}"
        )

    def test_repeat_and_final_boundaries(self) -> None:
        """P0 的 30min / 60min 边界语义确定."""
        p0 = _p1_detail() | {"severity": "P0", "escalation_level": 0}
        # 30min 边界
        d = compute_escalation(_alert(30, dict(p0), at=_at(30)), _at(30))
        assert d.should_escalate is True
        assert d.detail["escalation_level"] == 2

        # 60min 边界（level=1 时会先命中 30min? 不 —— level<2 条件不成立）
        p0_l1 = _p1_detail() | {"severity": "P0", "escalation_level": 1}
        d2 = compute_escalation(_alert(60, dict(p0_l1), at=_at(60)), _at(60))
        assert d2.should_escalate is True
        assert d2.detail["escalation_level"] == 2

    def test_drive_is_deterministic_across_repeated_calls(self) -> None:
        """同一输入重复驱动多轮，结果必须逐轮一致（flake 的直接反证）."""
        results = [_drive(240, [11, 35, 65, 120, 240]) for _ in range(5)]
        baseline = [
            (d.should_escalate, d.detail.get("escalation_level") if d.detail else None)
            for d in results[0]
        ]
        for i, run in enumerate(results[1:], start=2):
            got = [
                (d.should_escalate, d.detail.get("escalation_level") if d.detail else None)
                for d in run
            ]
            assert got == baseline, f"第 {i} 次驱动结果与第 1 次不一致（flake）"


class TestApplyEscalationPersistsSeverity:
    """apply_escalation 落库时必须写入 severity（仅改 compute 不够）.

    沿用 tests/test_escalation.py 的做法：真实 db_session 落库后重新查询，
    而不是 mock db.execute —— 后者只能验证「赋值给了内存对象」，无法证明
    severity 真的进了数据库。P0 的 severity 是从 DB 读出来的（compute_escalation
    的第 81 行），只有真落库才能证明修复有效。
    """

    @staticmethod
    def _make_detail(severity: str) -> dict[str, Any]:
        return _p1_detail() | {"severity": severity}

    @staticmethod
    async def _persist(db_session, detail: dict[str, Any], decision: EscalationDecision):
        from unittest.mock import AsyncMock, patch

        from app.monitoring.escalation import apply_escalation

        alert = OperationLog(
            operator_id=None,
            operator_role="system",
            action_type="alert_fired",
            target_type="alert",
            detail=json.dumps(detail, ensure_ascii=False),
            # 固定基准时刻，避免 DB 往返 + 真实时钟导致的阈值漂移（flake）
            created_at=_T0 - timedelta(minutes=30),
        )
        db_session.add(alert)
        await db_session.flush()
        decision.alert_id = alert.id

        with patch("app.monitoring.escalation.CompositeNotifier") as mock_notifier:
            mock_notifier.return_value.send = AsyncMock(return_value={"webhook": True})
            executed = await apply_escalation(db_session, [decision])
        await db_session.commit()
        return alert, executed

    async def test_severity_written_back_to_db(self, db_session) -> None:
        """P1→P0 决策落库后, DB 中的 detail['severity'] 应为 "P0".

        只改 compute_escalation 是不够的 —— 如果 apply_escalation 仍写原始
        d.detail，下一轮 compute 从 DB 读到的仍是旧 severity，缺陷照旧复现。
        """
        from sqlalchemy import select

        # 构造一个「decision.detail 里没有 severity」的决策：
        # 若无落库兜底，DB 里就仍无 severity，状态机会卡死
        decision = EscalationDecision(
            alert_id=0,
            should_escalate=True,
            new_severity="P0",
            reason="P1 unconfirmed, escalating to P0",
            detail={k: v for k, v in _p1_detail().items() if k != "severity"} | {
                "escalation_level": 1
            },
        )

        _, executed = await self._persist(db_session, self._make_detail("P1"), decision)
        assert len(executed) == 1

        row = (
            await db_session.execute(select(OperationLog).where(OperationLog.id == executed[0].alert_id))
        ).scalar_one()
        persisted = json.loads(row.detail)
        assert persisted["severity"] == "P0", (
            f"落库 detail 缺 severity='P0'，实际 {persisted.get('severity')!r} —— "
            "下一轮 compute 读到旧 severity 会再次卡死"
        )
        assert persisted["escalation_level"] == 1

    async def test_existing_severity_not_overwritten_wrongly(self, db_session) -> None:
        """decision.detail 已含正确 severity 时，落库结果应保持一致."""
        from sqlalchemy import select

        decision = EscalationDecision(
            alert_id=0,
            should_escalate=True,
            new_severity="P0",
            reason="r",
            detail=self._make_detail("P0") | {"escalation_level": 2},
        )

        _, executed = await self._persist(db_session, self._make_detail("P0"), decision)
        row = (
            await db_session.execute(select(OperationLog).where(OperationLog.id == executed[0].alert_id))
        ).scalar_one()
        persisted = json.loads(row.detail)
        assert persisted["severity"] == "P0"
        assert persisted["escalation_level"] == 2

    async def test_end_to_end_no_stuck_after_p1_escalation(self, db_session) -> None:
        """端到端: 走完整的 apply → 从 DB 重读 → 再决策, 确认不再卡死.

        这是缺陷的真实场景。旧代码在这里必然失败：第一次 apply 后 DB 里
        severity 仍是 "P1"，重读再判定就会返回 should_escalate=False。
        """
        from sqlalchemy import select

        from app.monitoring.escalation import apply_escalation

        # 固定基准时刻（确定性，见模块 docstring）。
        # created_at 取 75 分钟前：同时越过 10min / 30min / 60min 三个阈值，
        # 且距最近的边界（60min）有 15 分钟余量 —— 初版用 61min 只剩 1 分钟余量，
        # created_at 经 DB 往返后若被截断就会跌破 1h 阈值 → 随机 flake。
        alert = OperationLog(
            operator_id=None,
            operator_role="system",
            action_type="alert_fired",
            target_type="alert",
            detail=json.dumps(self._make_detail("P1"), ensure_ascii=False),
            created_at=_T0 - timedelta(minutes=75),
        )
        db_session.add(alert)
        await db_session.flush()

        # 第一轮: P1 → P0 (level=1)
        d1 = compute_escalation(alert, _T0)
        assert d1.should_escalate and d1.detail["escalation_level"] == 1

        from unittest.mock import AsyncMock, patch

        with patch("app.monitoring.escalation.CompositeNotifier") as mock_notifier:
            mock_notifier.return_value.send = AsyncMock(return_value={"webhook": True})
            await apply_escalation(db_session, [d1])
        await db_session.commit()

        # 从 DB 重读（模拟下一轮 Celery beat 扫描）
        reloaded = (
            await db_session.execute(select(OperationLog).where(OperationLog.id == alert.id))
        ).scalar_one()
        reloaded_detail = json.loads(reloaded.detail)
        assert reloaded_detail["severity"] == "P0", (
            f"重读时 severity 应为 P0，实际 {reloaded_detail.get('severity')!r}"
        )

        # 第二轮: 应继续升级（而不是永久停滞）
        # level=1 时先命中 30min repeat 分支 → level=2（既有正确行为：
        # 单次判定只走一个分支，P0_repeat 在 P0_final 之前）
        d2 = compute_escalation(reloaded, _T0)
        assert d2.should_escalate is True, (
            "P1 升级落库后，下一轮必须能继续升级 —— 旧代码在此永久卡死"
        )
        assert d2.detail["escalation_level"] == 2

        # 第三轮: level=2 后 1 小时 → level=3 (P0-1h 合规追踪)
        reloaded.detail = json.dumps(dict(d2.detail), ensure_ascii=False)
        await db_session.commit()
        reloaded2 = (
            await db_session.execute(select(OperationLog).where(OperationLog.id == alert.id))
        ).scalar_one()
        d3 = compute_escalation(reloaded2, _T0)
        assert d3.should_escalate is True, "level=2 后应能升到 level=3"
        assert d3.detail["escalation_level"] == 3, (
            f"level=3 (P0-1h 合规追踪) 未触发，实际 {d3.detail.get('escalation_level')}"
        )

        # 第四轮: 已达最高级，停止
        reloaded2.detail = json.dumps(dict(d3.detail), ensure_ascii=False)
        await db_session.commit()
        reloaded3 = (
            await db_session.execute(select(OperationLog).where(OperationLog.id == alert.id))
        ).scalar_one()
        d4 = compute_escalation(reloaded3, _T0)
        assert d4.should_escalate is False, "已达最高级后不应继续升级"


class TestNativeP0Unaffected:
    """原生 P0 告警的行为不得被本次修复改变."""

    def test_native_p0_level0_at_61m_hits_repeat_first(self) -> None:
        """原生 P0 + level=0 在 61 分钟: 先命中 30min 分支 → level=2.

        注意这是**既有正确行为**（单次判定只走一个分支，按代码顺序
        P0_repeat 在 P0_final 之前），本次修复没有改动它。早期版本我误断言
        为 level=3，实测得到 2 才确认 —— 记录在此以免后人重复踩。

        65min 而非 61min：为留出距 30min 阈值的余量，避免边界 flake。
        """
        detail = _p1_detail() | {"severity": "P0"}
        a = _alert(65, detail, at=_at(65))
        d = compute_escalation(a, _at(65))
        assert d.should_escalate is True
        assert d.detail["escalation_level"] == 2
        assert "repeat" in d.reason

    def test_native_p0_level2_reaches_level3(self) -> None:
        """原生 P0 已到 level=2 后, 1 小时应升到 level=3 (P0-1h)."""
        detail = _p1_detail() | {"severity": "P0", "escalation_level": 2}
        a = _alert(65, detail, at=_at(65))
        d = compute_escalation(a, _at(65))
        assert d.should_escalate is True
        assert d.detail["escalation_level"] == 3
        assert d.detail["severity"] == "P0"
        assert "P0-1h" in d.reason

    def test_native_p0_full_chain_terminates(self) -> None:
        """原生 P0 完整链路: 0 → 2 → 3 → 停止."""
        detail = _p1_detail() | {"severity": "P0"}
        levels = []
        for age in (35, 65, 125, 245):
            d = compute_escalation(_alert(age, detail, at=_at(age)), _at(age))
            if d.should_escalate and d.detail:
                levels.append(d.detail["escalation_level"])
                detail = dict(d.detail)
        assert levels == [2, 3], f"原生 P0 链路异常: {levels}"

    def test_acknowledged_still_stops(self) -> None:
        detail = _p1_detail() | {"acknowledged": True}
        a = _alert(125, detail, at=_at(125))
        d = compute_escalation(a, _at(125))
        assert d.should_escalate is False

    def test_p2_never_escalates(self) -> None:
        detail = _p1_detail() | {"severity": "P2"}
        a = _alert(125, detail, at=_at(125))
        d = compute_escalation(a, _at(125))
        assert d.should_escalate is False
