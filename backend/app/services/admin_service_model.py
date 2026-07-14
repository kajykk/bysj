from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.admin import ModelRegistry

if TYPE_CHECKING:
    pass


class ModelMixin:
    """模型注册表管理相关方法 Mixin。

    包含 ML 模型注册表的列表查询、注册、更新、激活逻辑。
    处理 model_id 重复时的 IntegrityError (H-Svc-17 修复)。

    依赖主类 AdminService 提供 `self.db`。
    """

    async def list_models(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ModelRegistry)
            .order_by(ModelRegistry.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(select(func.count()).select_from(ModelRegistry))
        ).scalar_one()
        return {
            "items": [
                {
                    "id": r.id,
                    "model_id": r.model_id,
                    "model_name": r.model_name,
                    "model_type": r.model_type,
                    "file_name": os.path.basename(r.file_path) if r.file_path else None,
                    "version": r.version,
                    "status": r.status,
                    "accuracy": r.accuracy,
                    "f1_score": r.f1_score,
                    "latency_ms": r.latency_ms,
                    "loaded_at": r.loaded_at.isoformat() if r.loaded_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def register_model(self, payload: dict) -> int:
        # 使用显式字段构造而非 **payload 直接解包
        model = ModelRegistry(
            model_id=payload["model_id"],
            model_name=payload.get("model_name", payload["model_id"]),
            model_type=payload.get("model_type", "unknown"),
            file_path=payload.get("file_path", ""),
            version=payload.get("version", "1.0.0"),
            status=payload.get("status", "inactive"),
            accuracy=payload.get("accuracy"),
            f1_score=payload.get("f1_score"),
            latency_ms=payload.get("latency_ms"),
        )
        self.db.add(model)
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        try:
            await self.db.flush()
        except SAIntegrityError:
            # H-Svc-17 修复：model_id 重复时 flush 抛 IntegrityError，回滚后抛业务异常。
            # 避免 commit() 在 PendingRollback 状态下抛 PendingRollbackError 掩盖原始错误。
            await self.db.rollback()
            raise ValueError("Model ID already exists")
        await self.db.commit()
        return model.id

    async def update_model(self, model_id_int: int, payload: dict) -> None:
        model = await self.db.get(ModelRegistry, model_id_int)
        if model is None:
            raise ValueError("模型不存在")
        for key in [
            "model_name",
            "model_type",
            "file_path",
            "version",
            "status",
            "accuracy",
            "f1_score",
            "latency_ms",
        ]:
            if key in payload:
                setattr(model, key, payload[key])
        await self.db.commit()

    async def activate_model(self, model_id_int: int) -> None:
        model = await self.db.get(ModelRegistry, model_id_int)
        if model is None:
            raise ValueError("模型不存在")
        model.status = "active"
        from datetime import UTC, datetime

        model.loaded_at = datetime.now(UTC).replace(tzinfo=None)
        await self.db.commit()
