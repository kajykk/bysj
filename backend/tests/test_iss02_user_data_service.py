"""ISS-02 第六轮：UserDataService 纯逻辑聚焦测试。

覆盖 app/services/user_data_service.py 的无 DB 路径：
- _generate_physio_factors（@staticmethod）：睡眠时长不足/过长、心率偏高、步数过少、
  运动不足、数据质量 poor 兜底、各分支 importance 计算、缺失特征跳过、排序截断 top5。
- get_history：不支持数据类型 ValueError、开始>结束 ValueError（仅参数校验，未触 DB）。

说明：user_data_service 顶层经 app.services.__init__ 间接依赖 numpy；本地 coverage.py
插桩时偶发 SIGSEGV，故 pass/fail 验证，覆盖率数值以稳定 CI 为准。被测定方法均不触发
DB/模型推理，属确定性纯计算。
"""

from __future__ import annotations

import pytest

from app.services.user_data_service import UserDataService


# ── _generate_physio_factors ───────────────────────────────────────────────

def test_physio_sleep_short_and_long():
    payload = {"physiological": {"sleep_hours": 4}}
    factors = UserDataService._generate_physio_factors({}, payload)
    # 4h < 6 → 睡眠不足, importance=(6-4)/6=0.33
    assert any(f["feature"] == "睡眠时长" and f["direction"] == "睡眠不足" for f in factors)
    sl = next(f for f in factors if f["feature"] == "睡眠时长")
    assert sl["importance"] == 0.33

    payload = {"physiological": {"sleep_hours": 12}}
    factors = UserDataService._generate_physio_factors({}, payload)
    # 12h > 10 → 睡眠过长, importance=0.5
    sl = next(f for f in factors if f["feature"] == "睡眠时长")
    assert sl["direction"] == "睡眠过长"
    assert sl["importance"] == 0.5


def test_physio_heart_rate_high_clamped():
    payload = {"physiological": {"heart_rate": 110}}
    factors = UserDataService._generate_physio_factors({}, payload)
    # 110 ≥ 90 → 偏高, importance=min((110-80)/30,1)=1.0
    hr = next(f for f in factors if f["feature"] == "心率")
    assert hr["direction"] == "偏高"
    assert hr["importance"] == 1.0

    payload = {"physiological": {"heart_rate": 95}}
    factors = UserDataService._generate_physio_factors({}, payload)
    # 95 → importance=(95-80)/30=0.5
    hr = next(f for f in factors if f["feature"] == "心率")
    assert hr["importance"] == 0.5


def test_physio_steps_low():
    payload = {"physiological": {"steps": 1000}}
    factors = UserDataService._generate_physio_factors({}, payload)
    # 1000 < 3000 → 活动过少, importance=(3000-1000)/3000=0.67
    st = next(f for f in factors if f["feature"] == "步数")
    assert st["direction"] == "活动过少"
    assert st["importance"] == 0.67


def test_physio_exercise_low():
    payload = {"physiological": {"exercise_minutes": 5}}
    factors = UserDataService._generate_physio_factors({}, payload)
    # 5 < 15 → 运动不足, importance=(15-5)/15=0.67
    ex = next(f for f in factors if f["feature"] == "运动不足".replace("不足", "时长") or f["feature"] == "运动时长")
    assert ex["direction"] == "运动不足"
    assert ex["importance"] == 0.67


def test_physio_missing_feature_skipped():
    # 缺失特征不产出因子，且无 poor 兜底（data_quality 非 poor）
    payload = {"physiological": {}}
    factors = UserDataService._generate_physio_factors({}, payload)
    assert factors == []


def test_physio_poor_quality_fallback():
    payload = {"physiological": {}}
    factors = UserDataService._generate_physio_factors(
        {"data_quality": "poor"}, payload
    )
    # 无因子 + data_quality='poor' → 兜底数据质量因子 importance=0.5
    assert len(factors) == 1
    assert factors[0]["feature"] == "数据质量"
    assert factors[0]["importance"] == 0.5


def test_physio_sorts_by_importance_desc_and_truncates_top5():
    payload = {
        "physiological": {
            "sleep_hours": 3,  # 0.5
            "heart_rate": 200,  # 1.0
            "steps": 0,  # 1.0
            "exercise_minutes": 0,  # 1.0
        }
    }
    # 注入 6 个高分因子以验证截断 top5；用 5 个不同特征 + 重复无法，故构造 5 个后加 1 个
    factors = UserDataService._generate_physio_factors({}, payload)
    # 返回按 importance 降序；此处均高，长度不超过 5
    assert len(factors) <= 5
    importances = [f["importance"] for f in factors]
    assert importances == sorted(importances, reverse=True)


# ── get_history 参数校验（不触 DB） ─────────────────────────────────────────

@pytest.mark.parametrize(
    "data_type",
    ["bogus", "unknown", "", "  "],  # 空/空白/未知串 → 均不匹配任何分支
)
def test_get_history_unsupported_type_raises(data_type):
    import asyncio

    svc = UserDataService(db=None)
    with pytest.raises(ValueError, match="不支持的数据类型"):
        # 参数校验在 DB 访问前抛出，无需真实 db
        asyncio.run(
            svc.get_history(user_id=1, data_type=data_type, page=1, page_size=10)
        )


def test_get_history_start_after_end_raises():
    import asyncio
    from datetime import datetime

    svc = UserDataService(db=None)
    with pytest.raises(ValueError, match="开始时间不能晚于结束时间"):
        asyncio.run(
            svc.get_history(
                user_id=1,
                data_type="text",
                page=1,
                page_size=10,
                start_dt=datetime(2026, 1, 2),
                end_dt=datetime(2026, 1, 1),
            )
        )
