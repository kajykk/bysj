"""Phase 5 多租户模型.

按 ADR-001 决策：共享数据库，共享 Schema（多租户字段）。

表结构：
- tenants: 租户主表（名称、编码、状态、配置）
- 在 users / operation_logs 等租户敏感表添加 tenant_id 字段（见对应模型）

向后兼容：
- 现有单租户数据 tenant_id 默认为 DEFAULT_TENANT_ID (1)
- 未解析到租户的请求路由到默认租户
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.contracts import (
    DEFAULT_TENANT_ID,
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_INACTIVE,
    TENANT_STATUS_SUSPENDED,
)
from app.models.base import Base


class Tenant(Base):
    """租户表 — 每个 Tenant 对应一个独立部署客户（如一所大学）.

    字段说明:
    - code: 租户唯一编码（如 "xx_univ"），用于请求头/子域名解析
    - status: active/inactive/suspended；suspended 时该租户所有请求被拒
    - config: 租户级配置（品牌、功能开关、阈值覆盖等），JSON 结构
    """

    __tablename__ = "tenants"

    __table_args__ = (
        CheckConstraint("LENGTH(name) >= 2 AND LENGTH(name) <= 100", name="ck_tenants_name_length"),
        CheckConstraint("LENGTH(code) >= 2 AND LENGTH(code) <= 50", name="ck_tenants_code_length"),
        CheckConstraint("LENGTH(status) <= 20", name="ck_tenants_status_length"),
        CheckConstraint(
            f"status IN ('{TENANT_STATUS_ACTIVE}', '{TENANT_STATUS_INACTIVE}', '{TENANT_STATUS_SUSPENDED}')",
            name="ck_tenants_status_values",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="租户名称（如 XX大学）")
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True, comment="租户编码（如 xx_univ）")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TENANT_STATUS_ACTIVE, index=True
    )
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="租户级配置（品牌/功能开关/阈值覆盖）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} code={self.code!r} status={self.status!r}>"


def default_tenant_id() -> int:
    """返回默认租户 ID（用于向后兼容单租户场景）."""
    return DEFAULT_TENANT_ID
