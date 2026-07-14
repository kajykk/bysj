from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.counselor_service_binding import BindingMixin
from app.services.counselor_service_consultation import ConsultationMixin
from app.services.counselor_service_group import GroupMixin
from app.services.counselor_service_user import UserMixin
from app.services.counselor_service_warning import WarningMixin

logger = logging.getLogger(__name__)


class CounselorService(
    WarningMixin,
    UserMixin,
    ConsultationMixin,
    GroupMixin,
    BindingMixin,
):
    """咨询师服务主入口。

    通过 Mixin 多继承组合以下功能模块:
    - WarningMixin: 风险告警列表/处理/升级 (含 H-Svc-13 幂等性、ISS-058 升级)
    - UserMixin: 咨询师绑定用户列表/详情 (含 PERF-P2-002 is_latest 优化、PII 越权防护)
    - ConsultationMixin: 咨询记录的创建/更新/列表 (含绑定校验、预警归属校验)
    - GroupMixin: 客户分组管理 (含 M13 N+1 修复、M9 IDOR 防护)
    - BindingMixin: 绑定码管理、用户绑定/解绑 (含 C-Svc-3 FOR UPDATE、H-01 用户锁、M21 placeholder 修复)

    本类仅保留 `__init__` 以及模块级工具:
    - `logger`: 模块级日志器 (WarningMixin 通过自身模块级 logger 记录)

    MAINT-P2-001: 原 894 行单文件拆分为 6 文件, 每文件 ≤500 行。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
