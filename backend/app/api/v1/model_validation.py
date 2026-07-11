"""Phase 3 临床模型验证 API.

提供模型验证指标计算端点，支持：
- 二分类/多类指标（sensitivity/specificity/PPV/NPV/AUROC/Brier Score）
- 置信区间（Wilson score + Bootstrap AUC）
- 公平性/偏差检查（按群体分组，小样本保护）
- 校准度评估

仅管理员可访问。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import get_current_user
from app.core.response import ok
from app.ml.model_validation import generate_clinical_validation_report
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/validation", tags=["model-validation"])


class ClinicalValidationRequest(BaseModel):
    """临床验证请求负载."""

    y_true: list[int] = Field(..., description="真实标签列表", min_length=2)
    y_pred: list[int] = Field(..., description="预测标签列表", min_length=2)
    y_score: list[float] = Field(
        ...,
        description="预测概率列表（二分类为一维，多类为二维 [[p0,p1,...], ...]）",
        min_length=2,
    )
    groups: list[str] | None = Field(
        default=None, description="群体标签列表（如性别/年级），用于公平性检查"
    )
    group_name: str = Field(default="unknown", description="群体名称（如 'gender'、'grade'）")
    class_labels: list[int] | None = Field(default=None, description="类别标签列表")
    confidence: float = Field(default=0.95, ge=0.5, le=0.999, description="置信水平")
    min_group_size: int = Field(
        default=30, ge=5, le=500, description="公平性检查最小群体大小"
    )

    def to_arrays(self) -> dict[str, Any]:
        """转换为 numpy 数组."""
        y_true = np.array(self.y_true)
        y_pred = np.array(self.y_pred)
        # y_score 可能是一维或二维
        y_score_data = np.array(self.y_score, dtype=float)
        if y_score_data.ndim == 1:
            y_score = y_score_data
        else:
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
async def run_clinical_validation(
    payload: ClinicalValidationRequest,
    current_user: User = Depends(get_current_user),
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
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可运行临床模型验证")

    if len(payload.y_true) != len(payload.y_pred) or len(payload.y_true) != len(payload.y_score):
        raise HTTPException(status_code=422, detail="y_true、y_pred、y_score 长度必须一致")

    if payload.groups is not None and len(payload.groups) != len(payload.y_true):
        raise HTTPException(status_code=422, detail="groups 长度必须与 y_true 一致")

    try:
        arrays = payload.to_arrays()
        report = generate_clinical_validation_report(
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
        raise HTTPException(status_code=500, detail=f"验证失败: {exc}") from exc
