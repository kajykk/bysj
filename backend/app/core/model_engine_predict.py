"""核心预测层薄壳转发模块 (向后兼容壳).

model_engine 包结构化拆分后, 本模块的全部实现已迁入
`app.core.model_engine.predict` (PredictMixin) 与 `app.core.model_engine.fusion`
(FusionMixin, 承接原 predict_fusion)。

保留本模块仅为兼容既有外部引用:

    from app.core.model_engine_predict import PredictMixin

新代码请直接使用包入口:

    from app.core.model_engine import ModelEngine, model_engine
"""

from __future__ import annotations

from app.core.model_engine.fusion import FusionMixin  # noqa: F401 — re-export for backward compat
from app.core.model_engine.predict import PredictMixin  # noqa: F401 — re-export for backward compat

__all__ = ["PredictMixin", "FusionMixin"]
