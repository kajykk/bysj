"""GDPR API endpoints (v1.27 P1 任务).

- GET  /api/v1/user/gdpr/export          → 导出所有个人数据 (JSON)
- POST /api/v1/user/gdpr/delete          → 匿名化 (被遗忘权)

ISS-074: 管理侧 GDPR 端点
- GET  /api/v1/admin/gdpr/export/{uid}   → 管理员导出任意用户数据
- POST /api/v1/admin/gdpr/delete/{uid}   → 管理员匿名化任意用户（无需密码）
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.user import User
from app.services.gdpr_service import GDPRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/gdpr", tags=["GDPR"])
# ISS-074: 管理员 GDPR 路由
admin_router = APIRouter(prefix="/admin/gdpr", tags=["GDPR-Admin"])


class DeleteAccountRequest(BaseModel):
    """删除账户请求 (二次确认)."""

    password: str = Field(..., min_length=1, description="当前密码用于二次确认")
    confirm: bool = Field(..., description="必须为 true 以确认删除")


# M-4 修复：每批从 DB 拉取的行数，避免一次性加载所有记录导致 OOM
GDPR_EXPORT_BATCH_SIZE = 200
# H-API-7 修复：每个 section 导出记录数上限，防止重度用户产生数百 MB JSON 导致带宽耗尽和前端 OOM
GDPR_EXPORT_MAX_RECORDS_PER_SECTION = 10000


async def _stream_user_data(service: GDPRService, user_id: int, export_id: str):
    """M-4 修复：真正的流式 JSON 生成器.

    按 section 顺序拉取 DB 并增量生成 JSON token，避免一次性把所有表加载到内存。
    每个 section 内部按 BATCH_SIZE 分批 fetch，每批 yield 一次以释放 GIL/让出事件循环。
    """
    # 1. 校验用户存在 + 拉取基础信息（小数据，一次性获取）
    try:
        user_dict = await service.fetch_user_account(user_id)
    except ValueError as exc:
        # 错误以 JSON 形式返回，保持响应契约
        yield json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
        return

    # 2. 流式 JSON：开括号 + metadata + account
    yield b"{\n"
    yield _dump_kv(
        "export_metadata",
        {
            "export_id": export_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "gdpr_articles": ["Article 15 (Access)", "Article 20 (Portability)"],
            "format_version": "1.0",
            "streamed": True,
        },
        indent=2,
        first=True,
    ).encode("utf-8")
    yield b",\n"
    yield _dump_kv("account", user_dict, indent=2).encode("utf-8")

    # 3. 增量拉取并流式输出各 section（大数据按批 fetch）
    # profile 是单对象（保持与原 API 一致），其他 section 是数组
    yield b",\n"
    profile_dict = await service.fetch_profile(user_id)
    yield f'  "profile": {json.dumps(profile_dict, ensure_ascii=False, default=str) if profile_dict else "null"}'.encode(
        "utf-8"
    )

    sections = [
        ("emergency_contacts", service.iter_emergency_contacts),
        ("counselor_bindings", service.iter_counselor_bindings),
        ("risk_assessments", service.iter_risk_assessments),
        ("warnings", service.iter_warnings),
        ("crisis_events", service.iter_crisis_events),
        ("intervention_plans", service.iter_intervention_plans),
        ("intervention_tasks", service.iter_intervention_tasks),
        ("operation_logs", service.iter_operation_logs),
    ]

    summary_counts: dict[str, int] = {"profile": 1 if profile_dict else 0}
    for section_name, iter_fn in sections:
        yield b",\n"
        yield f'  "{section_name}": [\n'.encode("utf-8")
        count = 0
        # H-API-7 修复：记录数达到上限后停止拉取，标记该 section 被截断
        truncated = False
        async for item_json in iter_fn(user_id, GDPR_EXPORT_BATCH_SIZE):
            if count > 0:
                yield b",\n"
            yield b"    " + item_json.encode("utf-8")
            count += 1
            if count >= GDPR_EXPORT_MAX_RECORDS_PER_SECTION:
                truncated = True
                break
        yield b"\n  ]"
        summary_counts[section_name] = count
        if truncated:
            summary_counts[f"{section_name}_truncated"] = True

    # 4. summary
    yield b",\n"
    yield _dump_kv("summary", summary_counts, indent=2).encode("utf-8")
    yield b"\n}\n"


def _dump_kv(key: str, value, indent: int = 2, first: bool = False) -> str:
    """以指定缩进序列化单个 "key": value 块."""
    prefix = "" if first else ""
    return f'{prefix}{" " * indent}"{key}": {json.dumps(value, ensure_ascii=False, default=str)}'


@router.get(
    "/export",
    summary="导出个人数据 (GDPR Article 15, 20)",
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("3/minute")
async def export_my_data(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出我的所有个人数据 (可携权).

    M-4 修复：真正流式响应，按 section 增量 fetch + yield，避免高并发下 OOM。
    包含: 账户信息、资料、紧急联系人、咨询师绑定、风险评估、预警、危机事件、干预计划、操作日志.
    """
    service = GDPRService(db)
    export_id = str(uuid.uuid4())

    logger.info(
        "GDPR export started (streaming): user_id=%s export_id=%s",
        current_user.id,
        export_id,
    )

    # SEC-P1-003 修复：记录 GDPR 自助导出审计日志 (流式响应前先提交, 避免事务在流式生成期间关闭)
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="user.gdpr.export_self",
            target_type="user",
            target_id=current_user.id,
            detail=json.dumps({"export_id": export_id}, ensure_ascii=False)[:5000],
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()

    return StreamingResponse(
        _stream_user_data(service, current_user.id, export_id),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="my_data_{current_user.id}.json"',
            "X-GDPR-Export-Id": export_id,
        },
    )


@router.post(
    "/delete", summary="匿名化账户 (GDPR Article 17)", responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("2/minute")
async def delete_my_account(
    request: Request,
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """匿名化我的账户 (被遗忘权).

    不可逆操作:
    - 用户名/邮箱/手机号/紧急联系人全部替换为占位符
    - 所有 refresh token session 撤销
    - 风险评估/危机事件**保留**用于合规审计
    - 操作写入 OperationLog 永久保留
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="必须显式确认删除操作")

    service = GDPRService(db)
    try:
        result = await service.anonymize_user(
            current_user.id,
            password_confirm=body.password,
        )
    except ValueError as exc:
        # 密码错误或用户不存在
        msg = str(exc)
        if "密码错误" in msg:
            raise HTTPException(status_code=401, detail=msg) from exc
        raise HTTPException(status_code=404, detail=msg) from exc

    logger.warning(
        "GDPR account deleted: user_id=%s original_email=%s",
        current_user.id,
        result.get("original_email_masked"),
    )
    # M-11 修复：使用 ok() 包装返回值，保持 API 响应格式一致
    return ok(result)


# ===== ISS-074: 管理员 GDPR 端点 =====


class AdminDeleteUserRequest(BaseModel):
    """ISS-074: 管理员匿名化用户请求."""

    confirm: bool = Field(..., description="必须为 true 以确认删除")
    reason: str = Field(
        ..., min_length=1, max_length=500, description="管理员操作原因（写入审计日志）"
    )


@admin_router.get(
    "/export/{user_id}", summary="管理员导出任意用户数据 (GDPR Article 15)"
)
@limiter.limit("10/minute")
async def admin_export_user_data(
    request: Request,
    user_id: int,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """ISS-074: 管理员导出指定用户的全部个人数据.

    - 仅 admin 角色可调用
    - 复用 GDPRService._stream_user_data 流式输出
    - 写入 OperationLog 审计日志（权限/安全场景需第二人复核）
    """
    service = GDPRService(db)
    export_id = str(uuid.uuid4())

    # 校验目标用户存在
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="目标用户不存在")

    # 审计日志：导出操作
    audit_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="admin.gdpr.export_user",
        target_type="user",
        target_id=user_id,
        detail=json.dumps(
            {"export_id": export_id, "target_username": target.username},
            ensure_ascii=False,
        )[:5000],
    )
    db.add(audit_log)
    await db.commit()

    logger.info(
        "Admin GDPR export: admin_id=%s target_user_id=%s export_id=%s",
        current_user.id,
        user_id,
        export_id,
    )

    return StreamingResponse(
        _stream_user_data(service, user_id, export_id),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="user_{user_id}_data_{export_id[:8]}.json"',
            "X-GDPR-Export-Id": export_id,
        },
    )


@admin_router.post("/delete/{user_id}", summary="管理员匿名化用户 (GDPR Article 17)")
@limiter.limit("5/minute")
async def admin_delete_user_account(
    request: Request,
    user_id: int,
    body: AdminDeleteUserRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """ISS-074: 管理员匿名化指定用户（无需用户密码）.

    - 仅 admin 角色可调用
    - 跳过密码验证（管理员越权路径，password_confirm=None）
    - 必须提供 reason（写入审计日志，供第二人复核）
    - 写入额外 OperationLog 记录管理员操作（区别于用户自删的 gdpr.account.deleted）
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="必须显式确认删除操作")

    # 防止管理员自删（应走用户自删路径）
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="管理员不可通过此端点删除自己，请使用用户设置页面的删除账户功能",
        )

    service = GDPRService(db)
    try:
        # password_confirm=None 触发管理员越权路径，跳过密码校验
        result = await service.anonymize_user(user_id, password_confirm=None)
    except ValueError as exc:
        msg = str(exc)
        if "不存在" in msg or "已被删除" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    # 额外审计日志：记录管理员越权操作（与用户自删的 gdpr.account.deleted 区分）
    admin_audit_log = OperationLog(
        operator_id=current_user.id,
        operator_role="admin",
        action_type="admin.gdpr.delete_user",
        target_type="user",
        target_id=user_id,
        detail=json.dumps(
            {
                "reason": body.reason,
                "anonymized_at": result.get("anonymized_at"),
                "original_email_masked": result.get("original_email_masked"),
            },
            ensure_ascii=False,
            default=str,
        )[:5000],
    )
    db.add(admin_audit_log)
    await db.commit()

    logger.warning(
        "Admin GDPR delete: admin_id=%s target_user_id=%s reason=%s",
        current_user.id,
        user_id,
        body.reason,
    )
    return ok(result)
