"""S3 P4 影子模式服务: BERT (M2) vs TF-IDF 双跑对拍.

v2.0 优化计划 P4 要求: 任何文本新模型必须双跑对拍后才允许替换 fallback.
M2 BERT (F1=0.8231) 已达切换阈值 (≥0.75), 但需影子期 1 周观察一致率 + 域外不回退.

工作原理:
    1. 生产请求仍走 TF-IDF (或现有 BERT 回退路径), 不影响线上结果
    2. 后台异步触发 M2 BERT 推理 (fire-and-forget, 不阻塞主请求)
    3. 对比两者 prediction/probability, 记录差异到日志 + 内存统计
    4. 提供 get_stats() 查询一致率, 影子期 1 周后决策切换

配置 (config.py):
    shadow_mode_text_enabled: bool = False   # 影子模式开关 (默认关)
    shadow_mode_text_sample_rate: float = 1.0  # 采样率 (1.0 = 全量对拍)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from typing import Any

from app.core.text_m2_bert_predictor import get_m2_bert_predictor

logger = logging.getLogger(__name__)


class ShadowModeService:
    """影子模式服务 (单例).

    管理 M2 BERT vs 生产 TF-IDF 双跑对拍, 记录一致率统计.
    线程安全: 单例 + asyncio.create_task (单线程事件循环, 无锁).
    """

    def __init__(self) -> None:
        self._predictor = None
        self._predictor_loaded = False
        # 一致率统计
        self._total = 0
        self._agreement = 0
        self._disagreement = 0
        # 概率差异统计
        self._prob_diff_sum = 0.0
        self._prob_diff_max = 0.0
        # 采样率 (从 config 读取, 默认全量)
        self._sample_rate = 1.0
        self._random = random.Random(42)

    def _ensure_predictor(self) -> bool:
        """懒加载 M2 BERT 推理器 (首次调用时加载)."""
        if self._predictor_loaded:
            return True
        try:
            self._predictor = get_m2_bert_predictor()
            self._predictor_loaded = True
            return True
        except Exception as e:
            logger.warning("[SHADOW] M2 BERT 推理器加载失败, 影子模式停用: %s", str(e)[:150])
            return False

    def fire_shadow_predict(
        self,
        text: str,
        production_result: dict[str, Any],
        sample_rate: float | None = None,
    ) -> None:
        """Fire-and-forget: 创建后台任务对拍, 不阻塞主请求.

        Args:
            text: 原始输入文本
            production_result: 生产 TF-IDF (或 BERT) 的预测结果
            sample_rate: 采样率覆盖 (None 用默认)
        """
        rate = sample_rate if sample_rate is not None else self._sample_rate
        if rate < 1.0 and self._random.random() > rate:
            return  # 跳过采样

        if not self._ensure_predictor():
            return

        # fire-and-forget: 创建后台任务, 主请求不等待
        asyncio.create_task(self._shadow_predict(text, production_result))

    async def _shadow_predict(
        self,
        text: str,
        production_result: dict[str, Any],
    ) -> None:
        """实际对拍逻辑 (后台异步执行)."""
        try:
            m2_result = await self._predictor.predict(text)
            if m2_result is None:
                return  # M2 推理失败, 不计入统计

            prod_pred = int(production_result.get("prediction", 0))
            m2_pred = int(m2_result.get("prediction", 0))
            prod_prob = float(production_result.get("probability", 0.0))
            m2_prob = float(m2_result.get("probability", 0.0))
            prod_model = production_result.get("model_used", "unknown")

            # 一致率统计
            self._total += 1
            agree = prod_pred == m2_pred
            if agree:
                self._agreement += 1
            else:
                self._disagreement += 1

            # 概率差异统计
            prob_diff = abs(prod_prob - m2_prob)
            self._prob_diff_sum += prob_diff
            if prob_diff > self._prob_diff_max:
                self._prob_diff_max = prob_diff

            # 文本哈希 (不记录原文, 隐私保护)
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]

            # 差异日志 (JSON 友好格式, 便于 ELK 采集)
            log_method = logger.info if agree else logger.warning
            log_method(
                '[SHADOW] text_hash=%s prod_model=%s prod_pred=%d m2_pred=%d '
                'prod_prob=%.3f m2_prob=%.3f prob_diff=%.3f agree=%s',
                text_hash, prod_model, prod_pred, m2_pred,
                prod_prob, m2_prob, prob_diff, agree,
            )
        except Exception as e:
            logger.debug("[SHADOW] 对拍异常 (不影响生产): %s", str(e)[:150])

    def get_stats(self) -> dict[str, Any]:
        """获取影子模式一致率统计 (供 API / 监控查询)."""
        total = self._total
        return {
            "total_comparisons": total,
            "agreement": self._agreement,
            "disagreement": self._disagreement,
            "agreement_rate": round(self._agreement / total, 4) if total > 0 else 0.0,
            "avg_prob_diff": round(self._prob_diff_sum / total, 4) if total > 0 else 0.0,
            "max_prob_diff": round(self._prob_diff_max, 4),
            "predictor_loaded": self._predictor_loaded,
        }

    def reset_stats(self) -> None:
        """重置统计 (测试用)."""
        self._total = 0
        self._agreement = 0
        self._disagreement = 0
        self._prob_diff_sum = 0.0
        self._prob_diff_max = 0.0


# 单例实例
_shadow_mode_instance: ShadowModeService | None = None


def get_shadow_mode_service() -> ShadowModeService:
    """获取影子模式服务单例."""
    global _shadow_mode_instance
    if _shadow_mode_instance is None:
        _shadow_mode_instance = ShadowModeService()
    return _shadow_mode_instance
