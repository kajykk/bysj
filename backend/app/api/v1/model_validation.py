"""Phase 3 临床模型验证 API.

提供模型验证指标计算端点，支持：
- 二分类/多类指标（sensitivity/specificity/PPV/NPV/AUROC/Brier Score）
- 置信区间（Wilson score + Bootstrap AUC）
- 公平性/偏差检查（按群体分组，小样本保护）
- 校准度评估

仅管理员可访问。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.core.deps import require_role
from app.core.rate_limit import limiter
from app.core.response import ok
from app.ml.model_validation import generate_clinical_validation_report
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/validation", tags=["model-validation"])

# SEC-FIX (M7): 输入长度上限——bootstrap AUC 是 O(n) 内存+CPU 密集计算,
# 无上限的数组可被用于耗尽 worker 内存/阻塞事件循环
_MAX_ARRAY_LEN = 5000
_MAX_GROUPS_LEN = 5000
_MAX_CLASS_LABELS = 100
# SEC-FIX (M7 补强): 多分类场景下 y_score 内层 (每个样本的类别概率数组)
# 也必须有界, 否则外层 × 内层总元素数无界, 原内存防护可被绕过
_MAX_INNER_SCORE_LEN = 100


class ClinicalValidationRequest(BaseModel):
    """临床验证请求负载."""

    y_true: list[int] = Field(..., description="真实标签列表", min_length=2, max_length=_MAX_ARRAY_LEN)
    y_pred: list[int] = Field(..., description="预测标签列表", min_length=2, max_length=_MAX_ARRAY_LEN)
    y_score: list[float | list[float]] = Field(
        ...,
        description="预测概率列表（二分类为一维，多类为二维 [[p0,p1,...], ...]）",
        min_length=2,
        max_length=_MAX_ARRAY_LEN,
    )
    groups: list[str] | None = Field(
        default=None, description="群体标签列表（如性别/年级），用于公平性检查", max_length=_MAX_GROUPS_LEN
    )
    group_name: str = Field(default="unknown", description="群体名称（如 'gender'、'grade'）", max_length=64)
    class_labels: list[int] | None = Field(default=None, description="类别标签列表", max_length=_MAX_CLASS_LABELS)
    confidence: float = Field(default=0.95, ge=0.5, le=0.999, description="置信水平")
    min_group_size: int = Field(
        default=30, ge=5, le=500, description="公平性检查最小群体大小"
    )

    @model_validator(mode="after")
    def _validate_y_score_shape(self) -> "ClinicalValidationRequest":
        """SEC-FIX (M7 补强): 校验 y_score 内层结构.

        二维场景下:
        - 每行长度必须一致 (np.array 转换 ragged 数组会抛 ValueError 落 500)
        - 每行长度必须有界 (<= _MAX_INNER_SCORE_LEN)
        """
        if not self.y_score:
            return self
        first = self.y_score[0]
        if isinstance(first, list):
            first_len = len(first)
            if first_len == 0:
                raise ValueError("y_score 内层列表不能为空")
            if first_len > _MAX_INNER_SCORE_LEN:
                raise ValueError(
                    f"y_score 内层列表长度超出上限 {_MAX_INNER_SCORE_LEN}"
                )
            for row in self.y_score[1:]:
                if not isinstance(row, list) or len(row) != first_len:
                    raise ValueError("y_score 二维数组必须为规则矩阵（各行等长）")
        else:
            # 一维场景: 不允许混入 list (ragged 数组会在 np.array 转换时失败)
            for item in self.y_score[1:]:
                if isinstance(item, list):
                    raise ValueError("y_score 不能混合标量与列表")
        return self

    def to_arrays(self) -> dict[str, Any]:
        """转换为 numpy 数组."""
        y_true = np.array(self.y_true)
        y_pred = np.array(self.y_pred)
        # y_score 可能是一维或二维
        y_score_data = np.array(self.y_score, dtype=float)
        # SEC-FIX (M7): 消除原 if/else 两个相同分支的死代码
        y_score = y_score_data

        result: dict[str, Any] = {
            "y_true": y_true,
            "y_pred": y_pred,
            "y_score": y_score,
        }
        if self.groups is not None:
            result["groups"] = np.array(self.groups)
        return result


@router.post("/clinical", summary="运行临床模型验证（管理员）")
@limiter.limit("10/minute")
async def run_clinical_validation(
    request: Request,
    payload: ClinicalValidationRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> dict[str, Any]:
    """运行完整的临床模型验证.

    返回包含以下内容的验证报告：
    - 二分类或多类指标（sensitivity/specificity/PPV/NPV/AUROC）
    - 各指标的置信区间
    - Brier Score（校准度）
    - 校准曲线
    - 公平性检查（如提供 groups）

    仅管理员可访问。
    """
    if len(payload.y_true) != len(payload.y_pred) or len(payload.y_true) != len(payload.y_score):
        raise HTTPException(status_code=422, detail="y_true、y_pred、y_score 长度必须一致")

    if payload.groups is not None and len(payload.groups) != len(payload.y_true):
        raise HTTPException(status_code=422, detail="groups 长度必须与 y_true 一致")

    try:
        arrays = payload.to_arrays()
        # SEC-FIX (M7): numpy/scipy (bootstrap AUC) 是 CPU 密集同步计算,
        # 移出事件循环线程, 避免阻塞其他请求
        report = await asyncio.to_thread(
            generate_clinical_validation_report,
            y_true=arrays["y_true"],
            y_pred=arrays["y_pred"],
            y_score=arrays["y_score"],
            groups=arrays.get("groups"),
            group_name=payload.group_name,
            class_labels=payload.class_labels,
            confidence=payload.confidence,
            min_group_size=payload.min_group_size,
        )
        return ok(report)
    except Exception as exc:
        logger.exception("Clinical validation failed")
        # SEC-FIX (M7): 不向客户端泄漏内部异常字符串
        raise HTTPException(status_code=500, detail="模型验证失败，请检查输入数据后重试") from exc
