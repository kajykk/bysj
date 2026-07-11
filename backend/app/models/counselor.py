from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CounselorProfile(Base):
    __tablename__ = "counselor_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_clients: Mapped[int] = mapped_column(Integer, default=30)
    certificate_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ConsultationAppointment(Base):
    __tablename__ = "consultation_appointments"

    __table_args__ = (
        # P1-D-5 修复：复合索引 - 咨询师/用户预约按日期查询
        Index("ix_consultation_appointments_counselor_date", "counselor_id", "appointment_date"),
        Index("ix_consultation_appointments_user_date", "user_id", "appointment_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，咨询师账号删除时保留预约记录
    # P0-D2 修复：ondelete="SET NULL" 要求列可空，否则删除咨询师时会抛 IntegrityError
    counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    appointment_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    consultation_type: Mapped[str] = mapped_column(String(20), default="regular")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ConsultationRecord(Base):
    __tablename__ = "consultation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，预约删除时保留咨询记录
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("consultation_appointments.id", ondelete="SET NULL"), nullable=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，告警删除时保留咨询记录
    warning_id: Mapped[int | None] = mapped_column(ForeignKey("warning_notifications.id", ondelete="SET NULL"), nullable=True, index=True)
    # P1-D-2 修复：外键添加 ondelete="SET NULL"，咨询师账号删除时保留咨询记录
    # P0-D2 修复：ondelete="SET NULL" 要求列可空，否则删除咨询师时会抛 IntegrityError
    counselor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    main_topics: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    interventions: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClientGroup(Base):
    __tablename__ = "client_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counselor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    group_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_tag: Mapped[str] = mapped_column(String(20), default="#409EFF")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClientGroupMember(Base):
    __tablename__ = "client_group_members"

    group_id: Mapped[int] = mapped_column(ForeignKey("client_groups.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
