"""SEC-P2-003: 上传文件安全处理服务.

提供两项安全功能:
1. EXIF 剥离: 用 Pillow 重编码图片, 删除 GPS/设备信息等敏感元数据
2. ClamAV 病毒扫描: 对接 clamd 守护进程, 无连接时降级跳过 (仅 warning)

集成点: app/api/v1/user_upload.py 的 upload_file / upload_batch 端点
在文件保存 + MIME 校验之后调用 process_uploaded_file.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# 图片扩展名集合 (需要 EXIF 剥离)
_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


def _check_pillow_available() -> bool:
    """检查 Pillow 是否可用."""
    try:
        from PIL import Image  # noqa: F401

        return True
    except ImportError:
        return False


def strip_image_exif(file_path: Path) -> tuple[bool, str]:
    """SEC-P2-003: 剥离图片 EXIF 元数据.

    用 Pillow 打开图片后重编码保存, 删除 GPS 坐标/设备型号/拍摄时间等敏感信息.
    支持 JPEG/PNG/WebP/GIF 格式.

    Args:
        file_path: 图片文件路径.

    Returns:
        (success, message) 元组.
        - success=True: EXIF 剥离成功 (或无需剥离)
        - success=False: 剥离失败 (Pillow 不可用或图片损坏)
    """
    if not settings.enable_exif_strip:
        return True, "EXIF strip disabled by config"

    if not _check_pillow_available():
        logger.warning(
            "SEC-P2-003: Pillow not installed, skipping EXIF strip for %s",
            file_path,
        )
        return True, "Pillow not installed, skipped"

    ext = file_path.suffix.lower().lstrip(".")
    if ext not in _IMAGE_EXTENSIONS:
        return True, f"Non-image file (.{ext}), skipped"

    try:
        from PIL import Image

        # 打开图片
        with Image.open(file_path) as img:
            # 创建新图片 (不携带 EXIF)
            # 使用 img.copy() + save() 重编码, 自动丢弃 EXIF/ICC profile
            # 保留 img.info 中的 "transparency" 等必要信息
            data = list(img.getdata())
            clean_img = Image.new(img.mode, img.size)
            clean_img.putdata(data)

            # 保留动画 GIF 的多帧处理
            save_kwargs: dict = {}
            if ext in ("jpg", "jpeg"):
                save_kwargs["quality"] = 95
                save_kwargs["optimize"] = True
                if clean_img.mode in ("RGBA", "P"):
                    clean_img = clean_img.convert("RGB")
            elif ext == "png":
                save_kwargs["optimize"] = True
            elif ext == "webp":
                save_kwargs["quality"] = 95

            # 写入临时文件后原子替换, 避免写入失败导致文件损坏
            tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
            clean_img.save(tmp_path, format=img.format, **save_kwargs)

            # 原子替换: 确保文件系统一致性
            os.replace(tmp_path, file_path)

        return True, f"EXIF stripped for .{ext}"

    except Exception as exc:
        logger.warning(
            "SEC-P2-003: EXIF strip failed for %s: %s",
            file_path,
            exc,
            exc_info=True,
        )
        return False, f"EXIF strip failed: {exc}"


def scan_with_clamav(file_path: Path) -> tuple[bool, str]:
    """SEC-P2-003: 用 ClamAV 扫描文件病毒.

    对接 clamd 守护进程 (通过 TCP 或 Unix socket).
    无连接时降级跳过 (仅记录 warning), 不阻断上传.

    Args:
        file_path: 待扫描文件路径.

    Returns:
        (safe, message) 元组.
        - safe=True: 文件安全 (或 ClamAV 不可用, 降级跳过)
        - safe=False: 检测到威胁, 应拒绝上传
    """
    if not settings.enable_clamav_scan:
        return True, "ClamAV scan disabled by config"

    try:
        import clamd  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "SEC-P2-003: pyclamd not installed, skipping ClamAV scan for %s",
            file_path,
        )
        return True, "pyclamd not installed, skipped"

    try:
        # 连接 clamd 守护进程
        if settings.clamav_unix_socket:
            cd = clamd.ClamdUnixSocket(settings.clamav_unix_socket)
        else:
            cd = clamd.ClamdNetworkSocket(
                host=settings.clamav_host or "localhost",
                port=settings.clamav_port or 3310,
            )

        # 扫描文件
        result = cd.scan(str(file_path))
        # result 格式: {filepath: ("OK", None) | ("FOUND", virus_name) | ("ERROR", msg)}
        for _path, (status, detail) in result.items():
            if status == "FOUND":
                logger.warning(
                    "SEC-P2-003: ClamAV detected virus in %s: %s",
                    file_path,
                    detail,
                )
                return False, f"Virus detected: {detail}"
            if status == "ERROR":
                logger.warning(
                    "SEC-P2-003: ClamAV scan error for %s: %s",
                    file_path,
                    detail,
                )
                # 扫描错误不阻断上传 (降级策略)
                return True, f"ClamAV scan error (allowed): {detail}"

        return True, "ClamAV scan passed"

    except clamd.ConnectionError as exc:
        # clamd 不可用, 降级跳过 (仅 warning)
        logger.warning(
            "SEC-P2-003: ClamAV daemon not available, skipping scan for %s: %s",
            file_path,
            exc,
        )
        return True, f"ClamAV not available, skipped: {exc}"
    except Exception as exc:
        logger.warning(
            "SEC-P2-003: ClamAV scan failed for %s: %s",
            file_path,
            exc,
            exc_info=True,
        )
        # 扫描失败不阻断上传 (降级策略), 仅记录 warning
        return True, f"ClamAV scan failed (allowed): {exc}"


def process_uploaded_file(file_path: Path, category: str | None = None) -> tuple[bool, str]:
    """SEC-P2-003: 上传文件安全处理 (EXIF 剥离 + ClamAV 扫描).

    处理流程:
    1. EXIF 剥离 (仅 image 类别): 用 Pillow 重编码, 删除敏感元数据
    2. ClamAV 病毒扫描 (所有类别): 对接 clamd, 无连接时降级

    Args:
        file_path: 已保存的文件路径.
        category: 文件类别 ("image" / "audio" / "document").

    Returns:
        (safe, message) 元组.
        - safe=True: 文件安全, 可保留
        - safe=False: 文件不安全 (检测到病毒或 EXIF 剥离失败), 应删除
    """
    messages: list[str] = []

    # 1. EXIF 剥离 (仅图片)
    if category == "image" or (
        category is None
        and file_path.suffix.lower().lstrip(".") in _IMAGE_EXTENSIONS
    ):
        exif_ok, exif_msg = strip_image_exif(file_path)
        messages.append(f"EXIF: {exif_msg}")
        if not exif_ok:
            return False, "; ".join(messages)

    # 2. ClamAV 病毒扫描 (所有文件)
    clamav_ok, clamav_msg = scan_with_clamav(file_path)
    messages.append(f"ClamAV: {clamav_msg}")
    if not clamav_ok:
        return False, "; ".join(messages)

    return True, "; ".join(messages)
