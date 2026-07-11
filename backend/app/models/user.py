from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.contracts import (
    USER_ROLE_ADMIN,
    USER_ROLE_COUNSELOR,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_DELETED,
    USER_STATUS_INACTIVE,
)
from app.core.pii_crypto import EncryptedString, compute_blind_index
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    # MAINT-P1-003: 枚举约束的 SQL 字面量通过 f-string 引用 contracts.py 常量,
    # 保证 DB 层与应用层契约同源 (运行时求值后字符串仍为 'user'/'admin'/...)
    __table_args__ = (
        CheckConstraint("LENGTH(username) >= 3 AND LENGTH(username) <= 50", name="ck_users_username_length"),
        # email 加密后长度远超明文，仅校验非空（加密在应用层完成）
        CheckConstraint("LENGTH(email) >= 3", name="ck_users_email_length"),
        CheckConstraint("phone IS NULL OR LENGTH(phone) >= 3", name="ck_users_phone_length"),
        CheckConstraint("LENGTH(password_hash) <= 255", name="ck_users_password_hash_length"),
        CheckConstraint("LENGTH(role) <= 20", name="ck_users_role_length"),
        CheckConstraint("LENGTH(status) <= 20", name="ck_users_status_length"),
        CheckConstraint("avatar_url IS NULL OR LENGTH(avatar_url) <= 500", name="ck_users_avatar_url_length"),
        # P1-D-8: 枚举约束 - 防止权限提升 (role 只允许 user/admin/counselor)
        CheckConstraint(
            f"role IN ('{USER_ROLE_USER}', '{USER_ROLE_ADMIN}', '{USER_ROLE_COUNSELOR}')",
            name="ck_users_role_values",
        ),
        # P1-D-8: 枚举约束 - status 只允许 active/inactive/deleted
        CheckConstraint(
            f"status IN ('{USER_STATUS_ACTIVE}', '{USER_STATUS_INACTIVE}', '{USER_STATUS_DELETED}')",
            name="ck_users_status_values",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    # PII 加密：email 使用 EncryptedString 透明加密存储，email_hash 用于唯一约束和等值查询
    email: Mapped[str] = mapped_column(EncryptedString(100, field="email"), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(EncryptedString(20, field="phone"), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=USER_STATUS_ACTIVE, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    review_tasks: Mapped[list["ReviewTask"]] = relationship(
        "ReviewTask",
        foreign_keys="ReviewTask.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    __table_args__ = (
        CheckConstraint("age IS NULL OR (age >= 0 AND age <= 120)", name="ck_user_profiles_age"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="zh")
    theme: Mapped[str] = mapped_column(String(10), default="light")
    reminder_freq: Mapped[str] = mapped_column(String(20), default="daily")
    # P1-5 埋点与隐私闭环：用户分析同意状态（默认不同意，需用户明确授权）
    analytics_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    __table_args__ = (
        # P0-S3 修复：name 和 phone 加密后长度远超明文，仅校验非空（加密在应用层完成）
        CheckConstraint("LENGTH(name) >= 3", name="ck_emergency_contacts_name_length"),
        CheckConstraint("LENGTH(relationship) >= 1 AND LENGTH(relationship) <= 20", name="ck_emergency_contacts_relationship_length"),
        CheckConstraint("LENGTH(phone) >= 3", name="ck_emergency_contacts_phone_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # P0-S3 修复：紧急联系人姓名和电话是 PII 数据，必须加密存储
    # pii_crypto.py 已定义 emergency_name 和 emergency_phone 的 salt，但模型未使用
    name: Mapped[str] = mapped_column(EncryptedString(50, field="emergency_name"), nullable=False)
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)
    phone: Mapped[str] = mapped_column(EncryptedString(20, field="emergency_phone"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class UserCounselorBinding(Base):
    __tablename__ = "user_counselor_bindings"

    __table_args__ = (
        UniqueConstraint("user_id", "counselor_id", name="uq_user_counselor_binding"),
        UniqueConstraint("bind_code", name="uq_bind_code"),
        CheckConstraint("LENGTH(bind_code) >= 4 AND LENGTH(bind_code) <= 10", name="ck_user_counselor_bindings_bind_code_length"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    counselor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    bind_code: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    bound_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
