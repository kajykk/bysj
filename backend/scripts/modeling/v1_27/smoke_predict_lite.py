"""v1.27 冒烟: 真实 calibrator 产物 + 真实 predict_lite 端到端验证."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.model_engine import model_engine  # noqa: E402


async def main() -> None:
    text = (
        "我最近完全睡不着，不想活了，对什么都提不起兴趣，"
        "学习压力大到崩溃，已经持续很久了。"
    )
    r = await model_engine.predict_lite(gad7_score=16, audio_transcript=text)
    print(
        json.dumps(
            {
                k: r[k]
                for k in (
                    "prediction",
                    "probability",
                    "probability_calibrated",
                    "risk_score",
                    "risk_level",
                    "model_used",
                )
            },
            ensure_ascii=False,
        )
    )
    used = (
        settings.lite_calibrated_decision_threshold
        if r["probability_calibrated"]
        else settings.lite_decision_threshold
    )
    print("threshold_used:", used)


asyncio.run(main())
