import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

try:
    import magic
except ImportError as exc:  # pragma: no cover - dependency requirement enforcement
    raise RuntimeError("python-magic is required for upload MIME validation") from exc

from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user/upload", tags=["user-upload"])

ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    "image": {"jpg", "jpeg", "png", "gif", "webp"},
    "audio": {"mp3", "wav", "ogg", "m4a", "aac"},
    "document": {"pdf", "txt", "csv"},
}

# MIME类型映射（用于验证文件内容）
ALLOWED_MIME_TYPES: dict[str, set[str]] = {
    "image": {"image/jpeg", "image/png", "image/gif", "image/webp"},
    "audio": {"audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/aac", "audio/x-m4a"},
    "document": {"application/pdf", "text/plain", "text/csv", "application/csv"},
}

MAX_FILE_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def _safe_resolve_path(base: Path, user_id: str, save_name: str) -> Path:
    """防御性校验：确保解析后的路径仍在 base 目录内，防止任何形式的路径遍历。"""
    base_resolved = base.resolve()
    candidate = (base / user_id / save_name).resolve()
    if base_resolved != candidate and base_resolved not in candidate.parents:
        raise HTTPException(status_code=400, detail="非法的文件路径")
    return candidate


def _validate_extension(filename: str, category: str | None = None) -> str:
    if "/" in filename or "\\" in filename or "\x00" in filename:
        raise HTTPException(status_code=400, detail="文件名包含非法字符")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ext:
        raise HTTPException(status_code=400, detail="文件缺少扩展名")
    if category and category in ALLOWED_EXTENSIONS:
        if ext not in ALLOWED_EXTENSIONS[category]:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}，允许: {', '.join(ALLOWED_EXTENSIONS[category])}")
    else:
        all_ext = set()
        for exts in ALLOWED_EXTENSIONS.values():
            all_ext |= exts
        if ext not in all_ext:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型: .{ext}")
    return ext


async def _validate_mime_type(file_content: bytes, category: str | None = None) -> None:
    """验证文件MIME类型与扩展名匹配（使用 python-magic）。"""
    mime = magic.from_buffer(file_content, mime=True)

    # 确定允许的MIME类型
    if category and category in ALLOWED_MIME_TYPES:
        allowed = ALLOWED_MIME_TYPES[category]
    else:
        allowed = set()
        for mime_types in ALLOWED_MIME_TYPES.values():
            allowed |= mime_types
    
    if mime not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"文件内容类型({mime})与扩展名不匹配"
        )


async def _save_upload_stream(file: UploadFile, save_path: Path) -> tuple[int, bytes]:
    """保存上传文件，返回文件大小和文件头部内容（用于MIME验证）。

    修复：只读取文件头部 8KB 用于 MIME 校验，避免将整个文件读入内存。
    原实现将整个文件（最多 20MB）追加到内存，并发上传会导致 OOM。
    python-magic 的 from_buffer 只需前几 KB 即可识别 MIME 类型。
    """
    size = 0
    head_bytes = b""
    head_collected = False
    _HEAD_LIMIT = 8192  # magic 只需前几 KB 即可识别 MIME
    with save_path.open("wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_SIZE:
                # 先关闭文件句柄，再删除文件（Windows需要）
                f.close()
                save_path.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="文件大小超过20MB限制")
            f.write(chunk)
            # 只收集文件头部用于 MIME 校验，避免全量加载
            if not head_collected:
                remaining = _HEAD_LIMIT - len(head_bytes)
                if remaining > 0:
                    head_bytes += chunk[:remaining]
                if len(head_bytes) >= _HEAD_LIMIT:
                    head_collected = True
    await file.seek(0)
    return size, head_bytes


@router.post("", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("20/minute")
async def upload_file(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("user.settings.manage"))],
    file: UploadFile = File(...),
    category: str | None = None,
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    ext = _validate_extension(file.filename, category)

    upload_base = Path("uploads")
    upload_base.mkdir(parents=True, exist_ok=True)
    user_id_str = str(current_user.id)
    user_dir = upload_base / user_id_str
    user_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex[:12]
    save_name = f"{file_id}.{ext}"
    save_path = _safe_resolve_path(upload_base, user_id_str, save_name)

    try:
        size, content = await _save_upload_stream(file, save_path)
        # MIME类型验证
        await _validate_mime_type(content, category)
    except HTTPException:
        save_path.unlink(missing_ok=True)
        raise
    except Exception:
        save_path.unlink(missing_ok=True)
        raise

    logger.info("User %s uploaded %s (%d bytes)", current_user.id, save_name, size)

    url = f"/uploads/{current_user.id}/{save_name}"
    return ok({
        "url": url,
        "filename": save_name,
        "original_name": file.filename,
        "size": size,
        "content_type": file.content_type,
    })


@router.post("/batch", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("10/minute")
async def upload_batch(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("user.settings.manage"))],
    files: list[UploadFile] = File(...),
    category: str | None = None,
) -> dict:
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="最多同时上传10个文件")

    results = []
    upload_base = Path("uploads")
    upload_base.mkdir(parents=True, exist_ok=True)
    user_id_str = str(current_user.id)
    user_dir = upload_base / user_id_str
    user_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        if not file.filename:
            continue
        save_path: Path | None = None
        try:
            ext = _validate_extension(file.filename, category)

            file_id = uuid.uuid4().hex[:12]
            save_name = f"{file_id}.{ext}"
            save_path = _safe_resolve_path(upload_base, user_id_str, save_name)
            size, content = await _save_upload_stream(file, save_path)

            # MIME类型验证
            await _validate_mime_type(content, category)

            url = f"/uploads/{current_user.id}/{save_name}"
            results.append({
                "url": url,
                "filename": save_name,
                "original_name": file.filename,
                "size": size,
            })
        except HTTPException as exc:
            if save_path is not None:
                save_path.unlink(missing_ok=True)
            results.append({"filename": file.filename, "error": exc.detail})
        except Exception:
            if save_path is not None:
                save_path.unlink(missing_ok=True)
            raise

    return ok({"items": results, "count": len(results)})
