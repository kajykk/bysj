"""T-303: ContentService 单元测试.

覆盖 app/services/content_service.py 的所有公开方法和私有静态方法:
- list_contents: 分页/过滤(category/content_type/keyword)/收藏标记/空结果/排序/keyword 截断
- get_content_detail: 不存在/非 active/原子自增 view_count (M12)/ContentViewHistory 写入/is_favorited
- toggle_favorite: 不存在/非 active/未收藏→新增/已收藏→删除
- list_favorites: 列表/空/非 active 过滤/排序/分页
- log_meditation: content_id=None/有值/不存在/非 active/completed=True/False
- get_recommendations: 无 RiskAssessment/有 risk_level/risk_level=None 兜底 (H-Svc-5)/偏好分类/
  page>1 fallback (L-11)/recommend_reason 三种文案
- list_recent_views: 列表/空/同 content 去重/非 active 过滤/排序
- _risk_default_category: risk_level 4/3/2/1/0 各分支
- _recommend_reason: 偏好/风险匹配/其他三种
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import (
    ContentViewHistory,
    EducationContent,
    MeditationLog,
    UserFavorite,
)
from app.models.risk import RiskAssessment
from app.services.content_service import ContentService


@pytest.fixture
def content_service(db_session: AsyncSession) -> ContentService:
    return ContentService(db_session)


@pytest.fixture
async def seeded_contents(db_session: AsyncSession, seeded_user_id: int) -> list[int]:
    """插入 5 个 EducationContent (4 active + 1 inactive) 用于测试."""
    rows = [
        EducationContent(
            title="情绪调节训练",
            content_type="article",
            category="emotion",
            content="情绪调节的内容",
            summary="情绪摘要",
            sort_order=1,
            view_count=10,
            status="active",
        ),
        EducationContent(
            title="睡眠恢复指导",
            content_type="audio",
            category="stress",
            content="睡眠内容",
            summary="睡眠摘要",
            sort_order=2,
            view_count=5,
            status="active",
        ),
        EducationContent(
            title="正念冥想入门",
            content_type="video",
            category="wellbeing",
            content="冥想内容",
            summary="冥想摘要",
            sort_order=3,
            view_count=20,
            status="active",
        ),
        EducationContent(
            title="危机干预指南",
            content_type="article",
            category="crisis",
            content="危机内容",
            summary="危机摘要",
            sort_order=0,
            view_count=0,
            status="active",
        ),
        EducationContent(
            title="已下线内容",
            content_type="article",
            category="emotion",
            content="已下线",
            summary="已下线摘要",
            sort_order=10,
            view_count=0,
            status="inactive",
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return [r.id for r in rows]


# ============================================================================
# list_contents
# ============================================================================


class TestListContents:
    """list_contents 分页/过滤/排序测试."""

    async def test_list_contents_empty(self, content_service: ContentService):
        """TC-COV-CONTENT-001: 空列表返回空 items."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword=None,
            page=1,
            page_size=10,
        )
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["page_size"] == 10

    async def test_list_contents_with_data(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-002: 含数据时正确返回 (4 active, 排除 inactive)."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword=None,
            page=1,
            page_size=10,
        )
        assert len(result["items"]) == 4
        assert result["total"] == 4

    async def test_list_contents_pagination(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-003: 分页正确."""
        page1 = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword=None,
            page=1,
            page_size=2,
        )
        assert len(page1["items"]) == 2
        assert page1["total"] == 4

        page2 = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword=None,
            page=2,
            page_size=2,
        )
        assert len(page2["items"]) == 2

        page3 = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword=None,
            page=3,
            page_size=2,
        )
        assert len(page3["items"]) == 0
        assert page3["total"] == 4

    async def test_list_contents_filter_by_category(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-004: 按 category 过滤."""
        result = await content_service.list_contents(
            user_id=1,
            category="emotion",
            content_type=None,
            keyword=None,
            page=1,
            page_size=10,
        )
        assert result["total"] == 1
        assert result["items"][0]["category"] == "emotion"

    async def test_list_contents_filter_by_content_type(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-005: 按 content_type 过滤."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type="article",
            keyword=None,
            page=1,
            page_size=10,
        )
        assert result["total"] == 2
        assert all(item["content_type"] == "article" for item in result["items"])

    async def test_list_contents_filter_by_keyword_in_title(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-006: 按 keyword 过滤 (匹配 title)."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword="情绪",
            page=1,
            page_size=10,
        )
        assert result["total"] == 1
        assert "情绪" in result["items"][0]["title"]

    async def test_list_contents_filter_by_keyword_in_summary(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-007: 按 keyword 过滤 (匹配 summary)."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword="睡眠摘要",
            page=1,
            page_size=10,
        )
        assert result["total"] == 1
        assert result["items"][0]["title"] == "睡眠恢复指导"

    async def test_list_contents_filter_by_keyword_in_content(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-008: 按 keyword 过滤 (匹配 content)."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword="冥想内容",
            page=1,
            page_size=10,
        )
        assert result["total"] == 1
        assert result["items"][0]["title"] == "正念冥想入门"

    async def test_list_contents_keyword_truncated(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-009: keyword 长度 > 50 时被截断为前 50 字符."""
        title_50 = "emotional" + "a" * 41  # 9 + 41 = 50 chars
        db_session.add(
            EducationContent(
                title=title_50,
                content_type="article",
                category="emotion",
                content="x",
                summary="s",
                status="active",
            )
        )
        await db_session.commit()

        long_keyword = "emotional" + "a" * 42  # 9 + 42 = 51 chars
        result = await content_service.list_contents(
            user_id=seeded_user_id,
            category=None,
            content_type=None,
            keyword=long_keyword,
            page=1,
            page_size=10,
        )
        # 截断后 keyword = title (50 chars), 应匹配
        # 如果不截断 (51 chars), title 中只有 41 个连续 a, 不匹配
        assert result["total"] == 1

    async def test_list_contents_keyword_whitespace_only(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-010: keyword 仅含空白时 strip 后为空, 不过滤."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword="   ",
            page=1,
            page_size=10,
        )
        assert result["total"] == 4

    async def test_list_contents_is_favorited_flag(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-011: is_favorited 标记正确."""
        db_session.add(
            UserFavorite(user_id=seeded_user_id, content_id=seeded_contents[0])
        )
        await db_session.commit()

        result = await content_service.list_contents(
            user_id=seeded_user_id,
            category=None,
            content_type=None,
            keyword=None,
            page=1,
            page_size=10,
        )
        favorited_items = [item for item in result["items"] if item["is_favorited"]]
        assert len(favorited_items) == 1
        assert favorited_items[0]["id"] == seeded_contents[0]

    async def test_list_contents_sort_order(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-012: 排序: sort_order asc, created_at desc."""
        result = await content_service.list_contents(
            user_id=1,
            category=None,
            content_type=None,
            keyword=None,
            page=1,
            page_size=10,
        )
        titles = [item["title"] for item in result["items"]]
        assert titles == [
            "危机干预指南",
            "情绪调节训练",
            "睡眠恢复指导",
            "正念冥想入门",
        ]


# ============================================================================
# get_content_detail
# ============================================================================


class TestGetContentDetail:
    """get_content_detail 测试."""

    async def test_get_content_detail_not_found(self, content_service: ContentService):
        """TC-COV-CONTENT-013: 不存在的 content_id 返回 None."""
        result = await content_service.get_content_detail(user_id=1, content_id=99999)
        assert result is None

    async def test_get_content_detail_inactive(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-014: 非 active 状态返回 None."""
        result = await content_service.get_content_detail(
            user_id=1, content_id=seeded_contents[4]
        )
        assert result is None

    async def test_get_content_detail_view_count_atomic_increment(
        self, content_service: ContentService, db_session: AsyncSession, seeded_contents
    ):
        """TC-COV-CONTENT-015: M12 修复 - view_count 原子自增 (查 DB 验证, 非内存值)."""
        cid = seeded_contents[0]

        before = (
            await db_session.execute(
                select(EducationContent.view_count).where(EducationContent.id == cid)
            )
        ).scalar_one()

        result = await content_service.get_content_detail(user_id=1, content_id=cid)

        after = (
            await db_session.execute(
                select(EducationContent.view_count).where(EducationContent.id == cid)
            )
        ).scalar_one()

        assert after == before + 1
        assert result["view_count"] == after  # L-Svc-6: 返回值与 DB 实际值一致

    async def test_get_content_detail_writes_view_history(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-016: 调用后写入 ContentViewHistory."""
        cid = seeded_contents[0]
        before_count = (
            await db_session.execute(
                select(func.count())
                .select_from(ContentViewHistory)
                .where(ContentViewHistory.content_id == cid)
            )
        ).scalar_one()

        await content_service.get_content_detail(user_id=seeded_user_id, content_id=cid)

        after_count = (
            await db_session.execute(
                select(func.count())
                .select_from(ContentViewHistory)
                .where(ContentViewHistory.content_id == cid)
            )
        ).scalar_one()

        assert after_count == before_count + 1

    async def test_get_content_detail_is_favorited(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-017: is_favorited 标记正确."""
        cid = seeded_contents[0]

        result1 = await content_service.get_content_detail(
            user_id=seeded_user_id, content_id=cid
        )
        assert result1["is_favorited"] is False

        db_session.add(UserFavorite(user_id=seeded_user_id, content_id=cid))
        await db_session.commit()

        result2 = await content_service.get_content_detail(
            user_id=seeded_user_id, content_id=cid
        )
        assert result2["is_favorited"] is True

    async def test_get_content_detail_returns_full_fields(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-018: 返回完整字段 (含 content/audio_url 等列表不返回的字段)."""
        cid = seeded_contents[0]
        result = await content_service.get_content_detail(user_id=1, content_id=cid)

        assert result is not None
        assert result["id"] == cid
        assert result["title"] == "情绪调节训练"
        assert result["content"] == "情绪调节的内容"
        assert result["summary"] == "情绪摘要"
        assert result["content_type"] == "article"
        assert result["category"] == "emotion"
        assert "audio_url" in result
        assert "cover_image_url" in result
        assert "duration_minutes" in result
        assert "difficulty" in result
        assert "view_count" in result
        assert "is_favorited" in result


# ============================================================================
# toggle_favorite
# ============================================================================


class TestToggleFavorite:
    """toggle_favorite 测试."""

    async def test_toggle_favorite_not_found(self, content_service: ContentService):
        """TC-COV-CONTENT-019: 不存在的 content_id 返回 False."""
        result = await content_service.toggle_favorite(user_id=1, content_id=99999)
        assert result is False

    async def test_toggle_favorite_inactive(
        self, content_service: ContentService, seeded_contents
    ):
        """TC-COV-CONTENT-020: 非 active 状态返回 False."""
        result = await content_service.toggle_favorite(
            user_id=1, content_id=seeded_contents[4]
        )
        assert result is False

    async def test_toggle_favorite_add_new(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-021: 未收藏 → 新增 UserFavorite."""
        cid = seeded_contents[0]
        result = await content_service.toggle_favorite(
            user_id=seeded_user_id, content_id=cid
        )
        assert result is True

        fav = (
            await db_session.execute(
                select(UserFavorite).where(
                    UserFavorite.user_id == seeded_user_id,
                    UserFavorite.content_id == cid,
                )
            )
        ).scalar_one_or_none()
        assert fav is not None

    async def test_toggle_favorite_remove_existing(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-022: 已收藏 → 删除 UserFavorite."""
        cid = seeded_contents[0]
        db_session.add(UserFavorite(user_id=seeded_user_id, content_id=cid))
        await db_session.commit()

        result = await content_service.toggle_favorite(
            user_id=seeded_user_id, content_id=cid
        )
        assert result is True

        fav = (
            await db_session.execute(
                select(UserFavorite).where(
                    UserFavorite.user_id == seeded_user_id,
                    UserFavorite.content_id == cid,
                )
            )
        ).scalar_one_or_none()
        assert fav is None


# ============================================================================
# list_favorites
# ============================================================================


class TestListFavorites:
    """list_favorites 测试."""

    async def test_list_favorites_empty(
        self, content_service: ContentService, seeded_user_id: int
    ):
        """TC-COV-CONTENT-023: 空收藏列表."""
        result = await content_service.list_favorites(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["page_size"] == 10

    async def test_list_favorites_with_data(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-024: 含数据时正确返回."""
        db_session.add(
            UserFavorite(user_id=seeded_user_id, content_id=seeded_contents[0])
        )
        db_session.add(
            UserFavorite(user_id=seeded_user_id, content_id=seeded_contents[1])
        )
        await db_session.commit()

        result = await content_service.list_favorites(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert len(result["items"]) == 2
        assert result["total"] == 2

    async def test_list_favorites_excludes_inactive_content(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-025: 非 active content 不在列表中."""
        db_session.add(
            UserFavorite(user_id=seeded_user_id, content_id=seeded_contents[0])
        )  # active
        db_session.add(
            UserFavorite(user_id=seeded_user_id, content_id=seeded_contents[4])
        )  # inactive
        await db_session.commit()

        result = await content_service.list_favorites(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == seeded_contents[0]
        assert result["total"] == 1

    async def test_list_favorites_pagination(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-026: 分页正确."""
        for cid in seeded_contents[:3]:
            db_session.add(UserFavorite(user_id=seeded_user_id, content_id=cid))
        await db_session.commit()

        page1 = await content_service.list_favorites(
            user_id=seeded_user_id, page=1, page_size=2
        )
        assert len(page1["items"]) == 2
        assert page1["total"] == 3

        page2 = await content_service.list_favorites(
            user_id=seeded_user_id, page=2, page_size=2
        )
        assert len(page2["items"]) == 1
        assert page2["total"] == 3

    async def test_list_favorites_sort_by_created_at_desc(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-027: 按 UserFavorite.created_at 倒序."""
        now = datetime.now(UTC).replace(tzinfo=None)
        fav1 = UserFavorite(
            user_id=seeded_user_id,
            content_id=seeded_contents[0],
            created_at=now - timedelta(hours=2),
        )
        fav2 = UserFavorite(
            user_id=seeded_user_id,
            content_id=seeded_contents[1],
            created_at=now - timedelta(hours=1),
        )
        fav3 = UserFavorite(
            user_id=seeded_user_id, content_id=seeded_contents[2], created_at=now
        )
        db_session.add_all([fav1, fav2, fav3])
        await db_session.commit()

        result = await content_service.list_favorites(
            user_id=seeded_user_id, page=1, page_size=10
        )
        # 倒序: fav3 (latest) first
        assert result["items"][0]["id"] == seeded_contents[2]
        assert result["items"][1]["id"] == seeded_contents[1]
        assert result["items"][2]["id"] == seeded_contents[0]


# ============================================================================
# log_meditation
# ============================================================================


class TestLogMeditation:
    """log_meditation 测试."""

    async def test_log_meditation_content_id_none(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-028: content_id=None 时仍记录 (未关联内容)."""
        log_id = await content_service.log_meditation(
            user_id=seeded_user_id,
            content_id=None,
            completed=False,
        )
        assert log_id is not None

        log = (
            await db_session.execute(
                select(MeditationLog).where(MeditationLog.id == log_id)
            )
        ).scalar_one()
        assert log.content_id is None
        assert log.completed is False
        assert log.completed_at is None

    async def test_log_meditation_with_valid_content_id(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-029: content_id 有效时记录并关联."""
        log_id = await content_service.log_meditation(
            user_id=seeded_user_id,
            content_id=seeded_contents[0],
            completed=True,
        )
        assert log_id is not None

        log = (
            await db_session.execute(
                select(MeditationLog).where(MeditationLog.id == log_id)
            )
        ).scalar_one()
        assert log.content_id == seeded_contents[0]
        assert log.completed is True
        assert log.completed_at is not None

    async def test_log_meditation_content_not_found(
        self, content_service: ContentService, seeded_user_id: int
    ):
        """TC-COV-CONTENT-030: content_id 不存在时返回 None (L-16 修复: None 而非 0)."""
        result = await content_service.log_meditation(
            user_id=seeded_user_id,
            content_id=99999,
            completed=False,
        )
        assert result is None

    async def test_log_meditation_content_inactive(
        self, content_service: ContentService, seeded_contents, seeded_user_id: int
    ):
        """TC-COV-CONTENT-031: content_id 非 active 时返回 None."""
        result = await content_service.log_meditation(
            user_id=seeded_user_id,
            content_id=seeded_contents[4],
            completed=False,
        )
        assert result is None

    async def test_log_meditation_completed_false(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-032: completed=False 时 completed_at=None."""
        log_id = await content_service.log_meditation(
            user_id=seeded_user_id,
            content_id=None,
            completed=False,
        )
        log = (
            await db_session.execute(
                select(MeditationLog).where(MeditationLog.id == log_id)
            )
        ).scalar_one()
        assert log.completed is False
        assert log.completed_at is None

    async def test_log_meditation_completed_true(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-033: completed=True 时 completed_at 不为 None."""
        log_id = await content_service.log_meditation(
            user_id=seeded_user_id,
            content_id=None,
            completed=True,
        )
        log = (
            await db_session.execute(
                select(MeditationLog).where(MeditationLog.id == log_id)
            )
        ).scalar_one()
        assert log.completed is True
        assert log.completed_at is not None


# ============================================================================
# get_recommendations
# ============================================================================


class TestGetRecommendations:
    """get_recommendations 测试."""

    async def test_get_recommendations_no_risk_assessment(
        self, content_service: ContentService, seeded_contents, seeded_user_id: int
    ):
        """TC-COV-CONTENT-034: 无 RiskAssessment 时 risk_level 默认 1."""
        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert result["risk_level"] == 1
        assert result["explain"]["risk_category"] == "wellbeing"
        assert result["explain"]["preferred_categories"] == []
        assert len(result["items"]) == 4

    async def test_get_recommendations_with_risk_level(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-035: 有 risk_level=3 时 risk_category=emotion."""
        db_session.add(
            RiskAssessment(
                user_id=seeded_user_id,
                risk_score=70,
                risk_level=3,
                structured_score=70,
                models_used=["m"],
                risk_factors=[],
                assessment_type="structured",
            )
        )
        await db_session.commit()

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert result["risk_level"] == 3
        assert result["explain"]["risk_category"] == "emotion"

    async def test_get_recommendations_risk_level_none_fallback(
        self,
        content_service: ContentService,
        seeded_contents,
        seeded_user_id: int,
        monkeypatch,
    ):
        """TC-COV-CONTENT-036: H-Svc-5 修复 - latest_risk.risk_level=None 时兜底为 1.

        由于 RiskAssessment.risk_level 字段在模型上是 nullable=False,
        通过 mock 拦截 db.execute 的第一次调用 (risk_stmt) 返回 risk_level=None 的实例.
        """
        mock_risk = MagicMock()
        mock_risk.risk_level = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_risk

        original_execute = content_service.db.execute
        call_count = [0]

        async def patched_execute(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result
            return await original_execute(*args, **kwargs)

        monkeypatch.setattr(content_service.db, "execute", patched_execute)

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert result["risk_level"] == 1
        assert result["explain"]["risk_category"] == "wellbeing"

    async def test_get_recommendations_with_preferred_categories(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-037: 基于浏览历史生成 preferred_categories."""
        for _ in range(3):
            db_session.add(
                ContentViewHistory(
                    user_id=seeded_user_id, content_id=seeded_contents[0]
                )
            )
        for _ in range(2):
            db_session.add(
                ContentViewHistory(
                    user_id=seeded_user_id, content_id=seeded_contents[1]
                )
            )
        await db_session.commit()

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert "emotion" in result["explain"]["preferred_categories"]
        assert result["explain"]["preferred_categories"][0] == "emotion"

    async def test_get_recommendations_page_out_of_range_fallback(
        self,
        content_service: ContentService,
        seeded_contents,
        seeded_user_id: int,
        monkeypatch,
    ):
        """TC-COV-CONTENT-038: L-11 修复 - page>1 且 offset 超出范围时触发 fallback 查询.

        构造 total=4, page=3, page_size=2 → offset=4, ranked_stmt 返回空,
        触发 fallback. 通过计数 execute 调用次数验证.
        """
        original_execute = content_service.db.execute
        call_count = [0]

        async def counting_execute(*args, **kwargs):
            call_count[0] += 1
            return await original_execute(*args, **kwargs)

        monkeypatch.setattr(content_service.db, "execute", counting_execute)

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=3, page_size=2
        )
        # 正常路径 5 次 (risk/preferred/count/ranked/favorites) + fallback 1 次 = 6 次
        assert call_count[0] == 6
        assert result["total"] == 4
        assert result["page"] == 3
        assert result["items"] == []

    async def test_get_recommendations_recommend_reason_preference(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-039: recommend_reason - 偏好分类."""
        db_session.add(
            ContentViewHistory(user_id=seeded_user_id, content_id=seeded_contents[0])
        )
        await db_session.commit()

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        emotion_item = next(
            item for item in result["items"] if item["category"] == "emotion"
        )
        assert emotion_item["recommend_reason"] == "基于你的近期浏览偏好推荐"

    async def test_get_recommendations_recommend_reason_risk_match(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-040: recommend_reason - 风险等级匹配 (非偏好)."""
        db_session.add(
            RiskAssessment(
                user_id=seeded_user_id,
                risk_score=70,
                risk_level=3,
                structured_score=70,
                models_used=["m"],
                risk_factors=[],
                assessment_type="structured",
            )
        )
        await db_session.commit()

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        emotion_item = next(
            item for item in result["items"] if item["category"] == "emotion"
        )
        assert emotion_item["recommend_reason"] == "基于你当前风险等级匹配推荐"

    async def test_get_recommendations_recommend_reason_other(
        self, content_service: ContentService, seeded_contents, seeded_user_id: int
    ):
        """TC-COV-CONTENT-041: recommend_reason - 其他 (非偏好非风险匹配)."""
        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        stress_item = next(
            item for item in result["items"] if item["category"] == "stress"
        )
        assert stress_item["recommend_reason"] == "基于内容热度与时效性推荐"

    async def test_get_recommendations_pagination(
        self, content_service: ContentService, seeded_contents, seeded_user_id: int
    ):
        """TC-COV-CONTENT-042: 分页正确."""
        page1 = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=2
        )
        assert len(page1["items"]) == 2
        assert page1["total"] == 4

        page2 = await content_service.get_recommendations(
            user_id=seeded_user_id, page=2, page_size=2
        )
        assert len(page2["items"]) == 2

    async def test_get_recommendations_includes_is_favorited(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-043: is_favorited 标记正确."""
        db_session.add(
            UserFavorite(user_id=seeded_user_id, content_id=seeded_contents[0])
        )
        await db_session.commit()

        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        favorited_items = [item for item in result["items"] if item["is_favorited"]]
        assert len(favorited_items) == 1
        assert favorited_items[0]["id"] == seeded_contents[0]

    async def test_get_recommendations_explain_structure(
        self, content_service: ContentService, seeded_contents, seeded_user_id: int
    ):
        """TC-COV-CONTENT-044: explain 结构完整."""
        result = await content_service.get_recommendations(
            user_id=seeded_user_id, page=1, page_size=10
        )
        explain = result["explain"]
        assert "risk_level" in explain
        assert "risk_category" in explain
        assert "preferred_categories" in explain
        assert "strategy" in explain
        assert "偏好" in explain["strategy"]


# ============================================================================
# list_recent_views
# ============================================================================


class TestListRecentViews:
    """list_recent_views 测试."""

    async def test_list_recent_views_empty(
        self, content_service: ContentService, seeded_user_id: int
    ):
        """TC-COV-CONTENT-045: 空列表."""
        result = await content_service.list_recent_views(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert result["items"] == []
        assert result["total"] == 0

    async def test_list_recent_views_with_data(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-046: 含数据时正确返回."""
        db_session.add(
            ContentViewHistory(user_id=seeded_user_id, content_id=seeded_contents[0])
        )
        db_session.add(
            ContentViewHistory(user_id=seeded_user_id, content_id=seeded_contents[1])
        )
        await db_session.commit()

        result = await content_service.list_recent_views(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert len(result["items"]) == 2
        assert result["total"] == 2
        assert "viewed_at" in result["items"][0]

    async def test_list_recent_views_dedup_same_content(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-047: 同 content 多次浏览只返回最新一次 (去重)."""
        now = datetime.now(UTC).replace(tzinfo=None)
        db_session.add(
            ContentViewHistory(
                user_id=seeded_user_id,
                content_id=seeded_contents[0],
                viewed_at=now - timedelta(hours=3),
            )
        )
        db_session.add(
            ContentViewHistory(
                user_id=seeded_user_id,
                content_id=seeded_contents[0],
                viewed_at=now - timedelta(hours=2),
            )
        )
        latest = ContentViewHistory(
            user_id=seeded_user_id,
            content_id=seeded_contents[0],
            viewed_at=now - timedelta(hours=1),
        )
        db_session.add(latest)
        await db_session.commit()

        result = await content_service.list_recent_views(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert len(result["items"]) == 1
        assert result["total"] == 1
        assert result["items"][0]["viewed_at"] == latest.viewed_at.isoformat()

    async def test_list_recent_views_excludes_inactive_content(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-048: 非 active content 不在 items 中 (即使有浏览历史).

        注: total 来自子查询 (按 user_id 过滤), 仍包含浏览历史计数;
        但 items 通过 JOIN EducationContent 且 status='active' 过滤, 不返回非 active content.
        """
        db_session.add(
            ContentViewHistory(user_id=seeded_user_id, content_id=seeded_contents[4])
        )
        await db_session.commit()

        result = await content_service.list_recent_views(
            user_id=seeded_user_id, page=1, page_size=10
        )
        # items 中不包含 inactive content
        assert result["items"] == []
        # total 来自子查询, 仍统计了浏览历史
        assert result["total"] == 1

    async def test_list_recent_views_sort_by_viewed_at_desc(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-049: 按 viewed_at 倒序."""
        now = datetime.now(UTC).replace(tzinfo=None)
        db_session.add(
            ContentViewHistory(
                user_id=seeded_user_id,
                content_id=seeded_contents[0],
                viewed_at=now - timedelta(hours=3),
            )
        )
        db_session.add(
            ContentViewHistory(
                user_id=seeded_user_id,
                content_id=seeded_contents[1],
                viewed_at=now - timedelta(hours=2),
            )
        )
        db_session.add(
            ContentViewHistory(
                user_id=seeded_user_id,
                content_id=seeded_contents[2],
                viewed_at=now - timedelta(hours=1),
            )
        )
        await db_session.commit()

        result = await content_service.list_recent_views(
            user_id=seeded_user_id, page=1, page_size=10
        )
        assert result["items"][0]["id"] == seeded_contents[2]
        assert result["items"][1]["id"] == seeded_contents[1]
        assert result["items"][2]["id"] == seeded_contents[0]

    async def test_list_recent_views_pagination(
        self,
        content_service: ContentService,
        db_session: AsyncSession,
        seeded_contents,
        seeded_user_id: int,
    ):
        """TC-COV-CONTENT-050: 分页正确."""
        for cid in seeded_contents[:3]:
            db_session.add(ContentViewHistory(user_id=seeded_user_id, content_id=cid))
        await db_session.commit()

        page1 = await content_service.list_recent_views(
            user_id=seeded_user_id, page=1, page_size=2
        )
        assert len(page1["items"]) == 2
        assert page1["total"] == 3

        page2 = await content_service.list_recent_views(
            user_id=seeded_user_id, page=2, page_size=2
        )
        assert len(page2["items"]) == 1


# ============================================================================
# _risk_default_category (静态方法)
# ============================================================================


class TestRiskDefaultCategory:
    """_risk_default_category 静态方法测试."""

    def test_risk_default_category_crisis(self):
        """TC-COV-CONTENT-051: risk_level >= 4 返回 crisis."""
        assert ContentService._risk_default_category(4) == "crisis"
        assert ContentService._risk_default_category(5) == "crisis"

    def test_risk_default_category_emotion(self):
        """TC-COV-CONTENT-052: risk_level = 3 返回 emotion."""
        assert ContentService._risk_default_category(3) == "emotion"

    def test_risk_default_category_stress(self):
        """TC-COV-CONTENT-053: risk_level = 2 返回 stress."""
        assert ContentService._risk_default_category(2) == "stress"

    def test_risk_default_category_wellbeing_for_level_1(self):
        """TC-COV-CONTENT-054: risk_level = 1 返回 wellbeing."""
        assert ContentService._risk_default_category(1) == "wellbeing"

    def test_risk_default_category_wellbeing_for_level_0(self):
        """TC-COV-CONTENT-055: risk_level = 0 返回 wellbeing."""
        assert ContentService._risk_default_category(0) == "wellbeing"


# ============================================================================
# _recommend_reason (静态方法)
# ============================================================================


class TestRecommendReason:
    """_recommend_reason 静态方法测试."""

    def test_recommend_reason_preference(self):
        """TC-COV-CONTENT-056: 偏好分类匹配."""
        result = ContentService._recommend_reason(
            "emotion", ["emotion", "stress"], "stress"
        )
        assert result == "基于你的近期浏览偏好推荐"

    def test_recommend_reason_risk_match(self):
        """TC-COV-CONTENT-057: 风险等级匹配 (非偏好)."""
        result = ContentService._recommend_reason("stress", ["emotion"], "stress")
        assert result == "基于你当前风险等级匹配推荐"

    def test_recommend_reason_other(self):
        """TC-COV-CONTENT-058: 其他情况."""
        result = ContentService._recommend_reason("wellbeing", [], "stress")
        assert result == "基于内容热度与时效性推荐"
