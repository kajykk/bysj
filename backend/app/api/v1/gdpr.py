"""GDPR API endpoints (v1.27 P1 任务).

- GET  /api/v1/user/gdpr/export     → 导出所有个人数据 (JSON)
- POST /api/v1/user/gdpr/delete     → 匿名化 (被遗忘权)
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.gdpr_service import GDPRService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/gdpr", tags=["GDPR"])


class DeleteAccountRequest(BaseModel):
    """删除账户请求 (二次确认)."""

    password: str = Field(..., min_length=1, description="当前密码用于二次确认")
    confirm: bool = Field(..., description="必须为 true 以确认删除")


@router.get("/export", summary="导出个人数据 (GDPR Article 15, 20)")
async def export_my_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出我的所有个人数据 (可携权).

    包含: 账户信息、资料、紧急联系人、咨询师绑定、风险评估、预警、危机事件、干预计划、操作日志.
    """
    service = GDPRService(db)
    try:
        data = await service.export_user_data(current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # P1-SEC-019 修复：改为内存流式响应，避免 PII 明文写入磁盘临时文件
    # 旧实现写入 /tmp/gdpr_exports/ 无权限限制且无清理任务，存在 PII 泄露风险
    export_content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    export_bytes = export_content.encode("utf-8")
    export_id = data["export_metadata"]["export_id"]

    logger.info(
        "GDPR export created: user_id=%s export_id=%s (streamed, no disk write)",
        current_user.id, export_id,
    )

    return StreamingResponse(
        iter([export_bytes]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="my_data_{current_user.id}.json"',
            "X-GDPR-Export-Id": export_id,
            "Content-Length": str(len(export_bytes)),
        },
    )


@router.post("/delete", summary="匿名化账户 (GDPR Article 17)")
async def delete_my_account(
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
        current_user.id, result.get("original_email_masked"),
    )
    return result
