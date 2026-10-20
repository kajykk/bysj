"""ROUND_24 / T3：分页排序确定性的**行为侧**回归（4 个代表性端点）。

效力说明（不夸大，与 p2_50 的结论一致）：
本机 SQLite 在 `created_at` 并列时恰好按 rowid 升序返回，所以"去掉次级键"
未必能让下面这些断言变红。真正的保障是结构见证
（`tests/test_p2_51_round24_pagination_order_gate.py` 读生产源码断言排序键）。
本文件的独立价值：
  1. 锁住"页 1 + 页 2 不重复、不丢行、覆盖全量"这一可观察契约
     （offset 计算、过滤条件、count 口径写错都会在这里红）；
  2. 锁住 tie-break 的**方向语义**：desc 场景并列组内 id 降序、asc 场景 id 升序。
     该断言在 SQLite 上实测具备区分力（去掉次级键会红，见
     `tests/tools/mutate_p2_51_round24_result.log` 的 T1 组）。

覆盖的六种形态：
  - `InterventionService.get_history`               链式 order_by + offset/limit
  - `ContentService.list_favorites`                  JOIN + 链式
  - `ContentService.list_contents`                   三键排序（sort_order/created_at/id）
  - `UserDataService.get_history("structured")`      **拆分**形态（order_by 与 offset 分行）
  - `CounselorService.list_consultation_records`     链式 + 二次查询
  - `AdminService.list_feedbacks`                    链式（管理端列表）
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import EducationContent, ModelFeedback, UserFavorite
from app.models.assessment import StructuredAssessment
from app.models.counselor import ConsultationRecord
from app.models.intervention import InterventionPlan
from app.services.admin_service import AdminService
from app.services.content_service import ContentService
from app.services.counselor_service import CounselorService
from app.services.intervention_service import InterventionService
from app.services.user_data_service import UserDataService

#: 六行共用同一个时间戳：制造"整组并列"，页边界必然落在并列组中间
TIED_AT = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
ROWS = 6
PAGE_SIZE = 3


def _assert_no_dup_no_gap(
    ids_page1: list[int], ids_page2: list[int], expected_ids: list[int]
) -> None:
    """页 1 + 页 2 必须无重复、无遗漏、覆盖全量。"""
    merged = ids_page1 + ids_page2
    assert len(merged) == len(set(merged)), f"跨页重复：{merged}"
    assert sorted(merged) == sorted(expected_ids), (
        f"跨页覆盖不符：拿到 {sorted(merged)}，应为 {sorted(expected_ids)}"
    )


@pytest.fixture
async def tied_intervention_plans(db_session: AsyncSession, seeded_user_id: int) -> list[int]:
    rows = [
        InterventionPlan(
            user_id=seeded_user_id,
            plan_name=f"tied-plan-{i}",
            risk_level=1,
            status="completed",  # 避开 ROUND_23a 的 active 部分唯一索引
            start_date=date(2026, 10, 1),
            created_at=TIED_AT,
        )
        for i in range(ROWS)
    ]
    db_session.add_all(rows)
    await db_session.flush()
    return [r.id for r in rows]


@pytest.fixture
async def tied_favorites(db_session: AsyncSession, seeded_user_id: int) -> list[int]:
    contents = [
        EducationContent(
            title=f"tied-content-{i}",
            content_type="article",
            category="emotion",
            content=f"body-{i}",
            summary=f"sum-{i}",
            sort_order=i,
            view_count=0,
            status="active",
        )
        for i in range(ROWS)
    ]
    db_session.add_all(contents)
    await db_session.flush()
    db_session.add_all(
        UserFavorite(user_id=seeded_user_id, content_id=c.id, created_at=TIED_AT)
        for c in contents
    )
    await db_session.flush()
    return [c.id for c in contents]


@pytest.fixture
async def tied_assessments(db_session: AsyncSession, seeded_user_id: int) -> list[int]:
    rows = [
        StructuredAssessment(
            user_id=seeded_user_id,
            assessment_type="PHQ-9",
            score=float(10 + i),
            severity="mild",
            data_payload={"i": i},
            created_at=TIED_AT,
        )
        for i in range(ROWS)
    ]
    db_session.add_all(rows)
    await db_session.flush()
    return [r.id for r in rows]


@pytest.fixture
async def tied_consultations(db_session: AsyncSession, seeded_user_id: int) -> list[int]:
    rows = [
        ConsultationRecord(
            counselor_id=seeded_user_id,
            user_id=seeded_user_id,
            main_topics=f"topic-{i}",
            created_at=TIED_AT,
        )
        for i in range(ROWS)
    ]
    db_session.add_all(rows)
    await db_session.flush()
    return [r.id for r in rows]


async def test_intervention_history_pages_are_disjoint(
    db_session: AsyncSession, seeded_user_id: int, tied_intervention_plans: list[int]
) -> None:
    """链式形态：并列组内按 id 降序（"最新在前"），跨页不重复不丢行。"""
    service = InterventionService(db_session)
    page1 = await service.get_history(seeded_user_id, page=1, page_size=PAGE_SIZE)
    page2 = await service.get_history(seeded_user_id, page=2, page_size=PAGE_SIZE)

    ids1 = [item["plan_id"] for item in page1["items"]]
    ids2 = [item["plan_id"] for item in page2["items"]]
    assert page1["total"] == ROWS
    _assert_no_dup_no_gap(ids1, ids2, tied_intervention_plans)
    assert ids1 + ids2 == sorted(tied_intervention_plans, reverse=True), (
        "并列组内未按 id 降序：tie-break 方向语义被改坏"
    )


async def test_content_favorites_pages_are_disjoint(
    db_session: AsyncSession, seeded_user_id: int, tied_favorites: list[int]
) -> None:
    """JOIN + 链式形态：收藏时间并列时按 UserFavorite.id 降序。"""
    service = ContentService(db_session)
    page1 = await service.list_favorites(seeded_user_id, page=1, page_size=PAGE_SIZE)
    page2 = await service.list_favorites(seeded_user_id, page=2, page_size=PAGE_SIZE)

    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    assert page1["total"] == ROWS
    _assert_no_dup_no_gap(ids1, ids2, tied_favorites)
    assert ids1 + ids2 == sorted(tied_favorites, reverse=True)


async def test_user_data_history_pages_are_disjoint(
    db_session: AsyncSession, seeded_user_id: int, tied_assessments: list[int]
) -> None:
    """拆分形态（order_by 与 offset 分两行）：并列组内按 id 降序。"""
    service = UserDataService(db_session)
    page1 = await service.get_history(
        seeded_user_id, data_type="structured", page=1, page_size=PAGE_SIZE
    )
    page2 = await service.get_history(
        seeded_user_id, data_type="structured", page=2, page_size=PAGE_SIZE
    )

    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    assert page1["total"] == ROWS
    _assert_no_dup_no_gap(ids1, ids2, tied_assessments)
    assert ids1 + ids2 == sorted(tied_assessments, reverse=True)


async def test_consultation_records_pages_are_disjoint(
    db_session: AsyncSession, seeded_user_id: int, tied_consultations: list[int]
) -> None:
    """咨询记录：并列组内按 id 降序，且二次查询（告警映射）不影响分页。"""
    service = CounselorService(db_session)
    page1 = await service.list_consultation_records(
        counselor_id=seeded_user_id, user_id=seeded_user_id, page=1, page_size=PAGE_SIZE
    )
    page2 = await service.list_consultation_records(
        counselor_id=seeded_user_id, user_id=seeded_user_id, page=2, page_size=PAGE_SIZE
    )

    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    assert page1["total"] == ROWS
    _assert_no_dup_no_gap(ids1, ids2, tied_consultations)
    assert ids1 + ids2 == sorted(tied_consultations, reverse=True)


async def test_content_list_pages_are_disjoint(
    db_session: AsyncSession, seeded_user_id: int
) -> None:
    """内容列表：三键排序（sort_order asc / created_at desc / id desc）。

    并列组 = 同 sort_order 且同 created_at，此时唯一能定序的是 id。
    """
    contents = [
        EducationContent(
            title=f"list-content-{i}",
            content_type="article",
            category="emotion",
            content=f"body-{i}",
            summary=f"sum-{i}",
            sort_order=1,  # 与 created_at 一起构成整组并列
            view_count=0,
            status="active",
            created_at=TIED_AT,
        )
        for i in range(ROWS)
    ]
    db_session.add_all(contents)
    await db_session.flush()
    expected = [c.id for c in contents]

    service = ContentService(db_session)
    page1 = await service.list_contents(
        seeded_user_id, None, None, None, page=1, page_size=PAGE_SIZE
    )
    page2 = await service.list_contents(
        seeded_user_id, None, None, None, page=2, page_size=PAGE_SIZE
    )

    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    assert page1["total"] == ROWS
    _assert_no_dup_no_gap(ids1, ids2, expected)
    assert ids1 + ids2 == sorted(expected, reverse=True)


async def test_model_feedback_pages_are_disjoint(
    db_session: AsyncSession, seeded_user_id: int
) -> None:
    """模型反馈列表：并列组内按 id 降序，跨页不重复不丢行。"""
    rows = [
        ModelFeedback(
            user_id=seeded_user_id,
            agreed=True,
            reason=f"reason-{i}",
            created_at=TIED_AT,
        )
        for i in range(ROWS)
    ]
    db_session.add_all(rows)
    await db_session.flush()
    expected = [r.id for r in rows]

    service = AdminService(db_session)
    page1 = await service.list_feedbacks(page=1, page_size=PAGE_SIZE)
    page2 = await service.list_feedbacks(page=2, page_size=PAGE_SIZE)

    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    assert page1["total"] == ROWS
    _assert_no_dup_no_gap(ids1, ids2, expected)
    assert ids1 + ids2 == sorted(expected, reverse=True)
