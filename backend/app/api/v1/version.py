from fastapi import APIRouter

from app.core.config import RELEASE_VERSION, settings
from app.core.openapi_responses import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["version"])
RELEASE_DATE = "2026-06-03"
RELEASE_STATUS = "OBSERVABILITY-ENHANCED"


@router.get("/version", responses=COMMON_ERROR_RESPONSES)
async def get_version():
    """版本端点 - 单一事实来源。

    返回项目发布版本(Release Version)与 FastAPI 应用版本(App Version),
    前者是面向用户/运维的迭代号,后者是应用自身的语义版本号。
    """
    return {
        "version": RELEASE_VERSION,
        "release_date": RELEASE_DATE,
        "status": RELEASE_STATUS,
        "app_version": settings.app_version,
        "app_name": settings.app_name,
    }
