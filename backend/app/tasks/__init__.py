"""Celery 任务模块注册.

autodiscover_tasks(["app.tasks"]) 仅查找 tasks.py 模块,
但本项目的任务分布在 scheduler.py / alerts.py / observability.py 等子模块中.
显式导入确保 Celery Worker 启动时注册全部任务, 避免 KeyError.
"""

# noqa: F401 — 导入副作用: 向 Celery 注册任务
from app.tasks import (
    alerts,  # noqa: F401
    anomaly_detection,  # noqa: F401
    model_training,  # noqa: F401
    observability,  # noqa: F401
    pdf_report,  # noqa: F401
    scheduler,  # noqa: F401
)
