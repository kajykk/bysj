from pydantic import BaseModel, Field


class MeditationLogRequest(BaseModel):
    content_id: int | None = Field(default=None, ge=1)
    completed: bool = False


class RecentViewRequest(BaseModel):
    content_id: int = Field(ge=1)


class ContentItem(BaseModel):
    """内容列表项."""

    id: int | None = None
    title: str | None = None
    content_type: str | None = None
    category: str | None = None
    summary: str | None = None
    cover_image_url: str | None = None
    duration_minutes: int | None = None
    difficulty: str | None = None
    view_count: int | None = None
    is_favorited: bool | None = None


class ContentDetail(ContentItem):
    content: str | None = None
    audio_url: str | None = None


class ContentListResponse(BaseModel):
    items: list[ContentItem] | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


class RecommendationExplain(BaseModel):
    """推荐策略解释（recommendations 端点顶层 explain 字段）."""

    risk_level: int | None = None
    risk_category: str | None = None
    preferred_categories: list[str] | None = None
    strategy: str | None = None


class RecommendationItem(ContentItem):
    recommend_reason: str | None = None


class RecommendationListResponse(BaseModel):
    explain: RecommendationExplain | None = None
    items: list[RecommendationItem] | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


class RecentViewItem(ContentItem):
    viewed_at: str | None = None


class RecentViewListResponse(BaseModel):
    items: list[RecentViewItem] | None = None
    total: int | None = None
    page: int | None = None
    page_size: int | None = None


class MeditationLogResult(BaseModel):
    log_id: int | None = None


class ToggleFavoriteResult(BaseModel):
    message: str | None = None
