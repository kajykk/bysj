"""model_predict 包 - 聚合所有 model 相关路由.

向后兼容: 所有原 model_predict.py 的符号仍可通过
``from app.api.v1.model_predict import xxx`` 导入.

被测试直接 patch 的符号 (必须存在于本包命名空间):
- ``logger``            : 测试 patch("app.api.v1.model_predict.logger")
- ``AsyncSessionLocal`` : 测试 patch("app.api.v1.model_predict.AsyncSessionLocal")
- ``_assessment_save_tasks`` / ``_log_task_exception`` / ``_save_assessment_sync``
  / ``_create_review_task`` / ``_create_review_task_sync``
  / ``predict_tabular`` / ``predict_text`` / ``predict_physiological`` / ``predict_fusion``
  : 测试直接 import 使用
"""

from fastapi import APIRouter

# 聚合 router (统一 prefix/tag, 与原 model_predict.py 保持一致)
router = APIRouter(prefix="/model", tags=["model"])

# 导入子模块 router 并 include (路由路径在子模块内定义, prefix 在此统一加)
from .experiment import router as experiment_router
from .predict import router as predict_router
from .status import router as status_router

router.include_router(predict_router)
router.include_router(status_router)
router.include_router(experiment_router)

# re-export 被 test 直接 import 的符号 (来自 _common)
# re-export AsyncSessionLocal (test patch 路径 app.api.v1.model_predict.AsyncSessionLocal 依赖)
from app.core.database import AsyncSessionLocal

from ._common import (
    _assessment_save_tasks,
    _log_task_exception,
    _save_assessment_sync,
    logger,
    save_assessment_result,
)

# re-export 被 test 直接 import 的符号 (来自 predict)
from .predict import (
    _create_review_task,
    _create_review_task_sync,
    predict_fusion,
    predict_physiological,
    predict_tabular,
    predict_text,
)

__all__ = [
    "router",
    "_assessment_save_tasks",
    "_log_task_exception",
    "_save_assessment_sync",
    "save_assessment_result",
    "logger",
    "AsyncSessionLocal",
    "_create_review_task",
    "_create_review_task_sync",
    "predict_tabular",
    "predict_text",
    "predict_physiological",
    "predict_fusion",
]
