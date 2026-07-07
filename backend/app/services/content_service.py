from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import (
    ContentViewHistory,
    EducationContent,
    MeditationLog,
    UserFavorite,
)
from app.models.risk import RiskAssessment


class ContentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_contents(
        self,
        user_id: int,
        category: str | None,
        content_type: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        offset = (page - 1) * page_size
        stmt = select(EducationContent).where(EducationContent.status == "active")
        count_stmt = (
            select(func.count())
            .select_from(EducationContent)
            .where(EducationContent.status == "active")
        )

        if category:
            stmt = stmt.where(EducationContent.category == category)
            count_stmt = count_stmt.where(EducationContent.category == category)
        if content_type:
            stmt = stmt.where(EducationContent.content_type == content_type)
            count_stmt = count_stmt.where(EducationContent.content_type == content_type)
        if keyword:
            keyword = keyword.strip()[:50]
            if keyword:
                like_kw = f"%{keyword}%"
                keyword_filter = (
                    EducationContent.title.ilike(like_kw)
                    | EducationContent.summary.ilike(like_kw)
                    | EducationContent.content.ilike(like_kw)
                )
                stmt = stmt.where(keyword_filter)
                count_stmt = count_stmt.where(keyword_filter)

        stmt = (
            stmt.order_by(
                EducationContent.sort_order.asc(), EducationContent.created_at.desc()
            )
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()

        favor_stmt = select(UserFavorite.content_id).where(
            UserFavorite.user_id == user_id
        )
        favorite_ids = set((await self.db.execute(favor_stmt)).scalars().all())

        items = [
            {
                "id": row.id,
                "title": row.title,
                "content_type": row.content_type,
                "category": row.category,
                "summary": row.summary,
                "cover_image_url": row.cover_image_url,
                "duration_minutes": row.duration_minutes,
                "difficulty": row.difficulty,
                "view_count": row.view_count,
                "is_favorited": row.id in favorite_ids,
            }
            for row in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_content_detail(self, user_id: int, content_id: int) -> dict | None:
        content = await self.db.get(EducationContent, content_id)
        if content is None or content.status != "active":
            return None

        # M12 修复：使用原子更新避免高并发下 view_count 读-改-写丢失更新
        await self.db.execute(
            update(EducationContent)
            .where(EducationContent.id == content_id)
            .values(view_count=func.coalesce(EducationContent.view_count, 0) + 1)
        )
        # L-Svc-6 修复：原子更新后从 DB 重新读取 view_count，避免内存近似值
        # （读时旧值 +1）与 DB 实际值（可能已被并发事务再 +1）不一致而误导展示。
        await self.db.refresh(content)
        self.db.add(ContentViewHistory(user_id=user_id, content_id=content_id))

        favorite_stmt = select(UserFavorite).where(
            UserFavorite.user_id == user_id, UserFavorite.content_id == content_id
        )
        favorite = (await self.db.execute(favorite_stmt)).scalar_one_or_none()
        await self.db.commit()

        return {
            "id": content.id,
            "title": content.title,
            "content_type": content.content_type,
            "category": content.category,
            "content": content.content,
            "summary": content.summary,
            "cover_image_url": content.cover_image_url,
            "audio_url": content.audio_url,
            "duration_minutes": content.duration_minutes,
            "difficulty": content.difficulty,
            "view_count": content.view_count,
            "is_favorited": favorite is not None,
        }

    async def toggle_favorite(self, user_id: int, content_id: int) -> bool:
        content = await self.db.get(EducationContent, content_id)
        if content is None or content.status != "active":
            return False

        stmt = select(UserFavorite).where(
            UserFavorite.user_id == user_id, UserFavorite.content_id == content_id
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row:
            await self.db.delete(row)
        else:
            self.db.add(UserFavorite(user_id=user_id, content_id=content_id))
        await self.db.commit()
        return True

    async def list_favorites(self, user_id: int, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(EducationContent)
            .join(UserFavorite, UserFavorite.content_id == EducationContent.id)
            .where(UserFavorite.user_id == user_id, EducationContent.status == "active")
            .order_by(UserFavorite.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        count_stmt = (
            select(func.count())
            .select_from(UserFavorite)
            .join(EducationContent, UserFavorite.content_id == EducationContent.id)
            .where(UserFavorite.user_id == user_id, EducationContent.status == "active")
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        return {
            "items": [
                {
                    "id": row.id,
                    "title": row.title,
                    "content_type": row.content_type,
                    "category": row.category,
                    "summary": row.summary,
                    "cover_image_url": row.cover_image_url,
                    "duration_minutes": row.duration_minutes,
                    "difficulty": row.difficulty,
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def log_meditation(
        self, user_id: int, content_id: int | None, completed: bool
    ) -> int | None:
        """记录冥想日志。

        Returns:
            log_id 成功时返回日志 ID，内容不存在时返回 None。
        """
        if content_id is not None:
            content = await self.db.get(EducationContent, content_id)
            # L-16 修复：使用 None 替代 0 作为错误哨兵，避免与合法 ID 冲突
            if content is None or content.status != "active":
                return None

        log = MeditationLog(
            user_id=user_id,
            content_id=content_id,
            completed=completed,
            # ISS-043 修复：统一 naive UTC，与 DB DateTime 列保持一致
            completed_at=datetime.utcnow() if completed else None,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log.id

    async def get_recommendations(
        self, user_id: int, page: int, page_size: int
    ) -> dict:
        risk_stmt = (
            select(RiskAssessment)
            .where(RiskAssessment.user_id == user_id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(1)
        )
        latest_risk = (await self.db.execute(risk_stmt)).scalar_one_or_none()
        # H-Svc-5 修复：risk_level 字段可能为 None，需额外检查避免 _risk_default_category(None) 抛 TypeError
        risk_level = (
            latest_risk.risk_level
            if latest_risk and latest_risk.risk_level is not None
            else 1
        )

        preferred_categories_stmt = (
            select(
                EducationContent.category,
                func.count(ContentViewHistory.id).label("cnt"),
            )
            .join(
                ContentViewHistory, ContentViewHistory.content_id == EducationContent.id
            )
            .where(
                ContentViewHistory.user_id == user_id,
                EducationContent.status == "active",
            )
            .group_by(EducationContent.category)
            .order_by(func.count(ContentViewHistory.id).desc())
            .limit(3)
        )
        preferred_categories = [
            x[0]
            for x in (await self.db.execute(preferred_categories_stmt)).all()
            if x[0]
        ]
        risk_category = self._risk_default_category(risk_level)

        offset = (page - 1) * page_size
        priority_case = case(
            (EducationContent.category.in_(preferred_categories), 0),
            (EducationContent.category == risk_category, 1),
            else_=2,
        )
        base_stmt = select(EducationContent).where(EducationContent.status == "active")
        count_stmt = (
            select(func.count())
            .select_from(EducationContent)
            .where(EducationContent.status == "active")
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        ranked_stmt = (
            base_stmt.order_by(
                priority_case,
                EducationContent.view_count.desc(),
                EducationContent.created_at.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(ranked_stmt)).scalars().all()

        if not rows and page > 1 and total > 0:
            # L-11 修复：回退查询也使用 offset + limit，避免加载全部行到内存
            fallback_stmt = (
                base_stmt.order_by(
                    EducationContent.view_count.desc(),
                    EducationContent.created_at.desc(),
                )
                .offset(offset)
                .limit(page_size)
            )
            rows = (await self.db.execute(fallback_stmt)).scalars().all()

        favorite_ids = set(
            (
                await self.db.execute(
                    select(UserFavorite.content_id).where(
                        UserFavorite.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )

        return {
            "risk_level": risk_level,
            "explain": {
                "risk_level": risk_level,
                "risk_category": risk_category,
                "preferred_categories": preferred_categories,
                "strategy": "先按用户偏好分类推荐，再按风险等级匹配内容分类，最后按热度与时间排序",
            },
            "items": [
                {
                    "id": row.id,
                    "title": row.title,
                    "content_type": row.content_type,
                    "category": row.category,
                    "summary": row.summary,
                    "cover_image_url": row.cover_image_url,
                    "duration_minutes": row.duration_minutes,
                    "difficulty": row.difficulty,
                    "view_count": row.view_count,
                    "is_favorited": row.id in favorite_ids,
                    "recommend_reason": self._recommend_reason(
                        row.category or "", preferred_categories, risk_category
                    ),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_recent_views(self, user_id: int, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        latest_view_subq = (
            select(
                ContentViewHistory.content_id,
                func.max(ContentViewHistory.viewed_at).label("latest_viewed_at"),
            )
            .where(ContentViewHistory.user_id == user_id)
            .group_by(ContentViewHistory.content_id)
            .subquery()
        )

        stmt = (
            select(EducationContent, latest_view_subq.c.latest_viewed_at)
            .join(
                latest_view_subq, latest_view_subq.c.content_id == EducationContent.id
            )
            .where(EducationContent.status == "active")
            .order_by(latest_view_subq.c.latest_viewed_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).all()

        count_stmt = select(func.count()).select_from(latest_view_subq)
        total = (await self.db.execute(count_stmt)).scalar_one()

        return {
            "items": [
                {
                    "id": content.id,
                    "title": content.title,
                    "content_type": content.content_type,
                    "category": content.category,
                    "summary": content.summary,
                    "cover_image_url": content.cover_image_url,
                    "duration_minutes": content.duration_minutes,
                    "difficulty": content.difficulty,
                    "viewed_at": viewed_at.isoformat() if viewed_at else None,
                }
                for content, viewed_at in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def _risk_default_category(risk_level: int) -> str:
        if risk_level >= 4:
            return "crisis"
        if risk_level >= 3:
            return "emotion"
        if risk_level >= 2:
            return "stress"
        return "wellbeing"

    @staticmethod
    def _recommend_reason(
        category: str, preferred_categories: list[str], risk_category: str
    ) -> str:
        if category in preferred_categories:
            return "基于你的近期浏览偏好推荐"
        if category == risk_category:
            return "基于你当前风险等级匹配推荐"
        return "基于内容热度与时效性推荐"
