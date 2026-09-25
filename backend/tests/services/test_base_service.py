"""BaseService (app/services/base_service.py) 通用 CRUD 基类单元测试.

MAINT-P2-004 引入的 CRUD 基类此前无任何测试 (覆盖率 0%)。本文件覆盖 6 个
公共方法与 NotFoundError 的全部分支:

- get_by_id: 命中 / 未命中
- get_by_id_or_404: 命中 / 抛 NotFoundError (含异常消息格式)
- list_paginated: 默认排序 / 自定义排序 / filters / offset+limit / total
- create: 写入后 id 可用
- update: 字段更新 / 跳过模型上不存在的字段 / 记录不存在时抛错
- delete: 删除成功 / 记录不存在返回 False

用 InterventionTemplate 作为具体模型 (字段简单, 无必填外键)。
"""

from __future__ import annotations

import pytest

from app.models.intervention import InterventionTemplate
from app.services.base_service import BaseService, NotFoundError


class TemplateService(BaseService[InterventionTemplate]):
    model = InterventionTemplate


def _template(name: str, levels: list[int], weeks: int = 4) -> InterventionTemplate:
    return InterventionTemplate(
        template_name=name,
        applicable_levels=levels,
        task_list=[{"task_name": "呼吸训练", "task_type": "meditation"}],
        estimated_weeks=weeks,
        status="active",
    )


class TestNotFoundError:
    def test_message_format(self):
        err = NotFoundError("InterventionTemplate", 42)
        assert str(err) == "InterventionTemplate with id=42 not found"
        assert err.model_name == "InterventionTemplate"
        assert err.record_id == 42


class TestGetById:
    @pytest.mark.asyncio
    async def test_returns_record_when_exists(self, db_session):
        db_session.add(_template("T1", [1]))
        await db_session.flush()

        service = TemplateService(db_session)
        record = await service.get_by_id(1)

        assert record is not None
        assert record.template_name == "T1"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self, db_session):
        service = TemplateService(db_session)
        assert await service.get_by_id(999999) is None


class TestGetByIdOr404:
    @pytest.mark.asyncio
    async def test_returns_record_when_exists(self, db_session):
        db_session.add(_template("T2", [2]))
        await db_session.flush()

        service = TemplateService(db_session)
        record = await service.get_by_id_or_404(1)
        assert record.template_name == "T2"

    @pytest.mark.asyncio
    async def test_raises_not_found_error(self, db_session):
        service = TemplateService(db_session)
        with pytest.raises(NotFoundError) as exc_info:
            await service.get_by_id_or_404(999999)

        assert exc_info.value.model_name == "InterventionTemplate"
        assert exc_info.value.record_id == 999999


class TestListPaginated:
    @pytest.mark.asyncio
    async def test_returns_all_and_total(self, db_session):
        db_session.add_all([_template("A", [1]), _template("B", [2])])
        await db_session.flush()

        service = TemplateService(db_session)
        records, total = await service.list_paginated()

        assert total == 2
        assert len(records) == 2

    @pytest.mark.asyncio
    async def test_default_order_is_id_desc(self, db_session):
        db_session.add_all([_template("A", [1]), _template("B", [2])])
        await db_session.flush()

        service = TemplateService(db_session)
        records, _ = await service.list_paginated()

        assert [r.template_name for r in records] == ["B", "A"]

    @pytest.mark.asyncio
    async def test_custom_order_by(self, db_session):
        db_session.add_all([_template("A", [1]), _template("B", [2])])
        await db_session.flush()

        service = TemplateService(db_session)
        records, _ = await service.list_paginated(
            order_by=InterventionTemplate.id.asc()
        )

        assert [r.template_name for r in records] == ["A", "B"]

    @pytest.mark.asyncio
    async def test_offset_and_limit(self, db_session):
        db_session.add_all(
            [_template("A", [1]), _template("B", [2]), _template("C", [3])]
        )
        await db_session.flush()

        service = TemplateService(db_session)
        records, total = await service.list_paginated(
            offset=1, limit=1, order_by=InterventionTemplate.id.asc()
        )

        # total 是过滤后的总数, 不受 offset/limit 影响
        assert total == 3
        assert [r.template_name for r in records] == ["B"]

    @pytest.mark.asyncio
    async def test_filters_apply_to_both_rows_and_count(self, db_session):
        db_session.add_all(
            [_template("A", [1]), _template("B", [2], weeks=8)]
        )
        await db_session.flush()

        service = TemplateService(db_session)
        records, total = await service.list_paginated(
            filters=[InterventionTemplate.estimated_weeks == 8]
        )

        assert total == 1
        assert [r.template_name for r in records] == ["B"]

    @pytest.mark.asyncio
    async def test_empty_table(self, db_session):
        service = TemplateService(db_session)
        records, total = await service.list_paginated()

        assert records == []
        assert total == 0


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_and_assigns_id(self, db_session):
        service = TemplateService(db_session)
        record = await service.create(
            {
                "template_name": "新建模板",
                "applicable_levels": [3],
                "task_list": [{"task_name": "运动", "task_type": "exercise"}],
                "estimated_weeks": 2,
            }
        )

        assert record.id is not None
        assert record.template_name == "新建模板"
        # create 内部已 flush, 同 session 可查回
        assert await service.get_by_id(record.id) is not None


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_existing_fields(self, db_session):
        db_session.add(_template("旧名", [1], weeks=4))
        await db_session.flush()

        service = TemplateService(db_session)
        record = await service.update(1, {"template_name": "新名", "estimated_weeks": 6})

        assert record.template_name == "新名"
        assert record.estimated_weeks == 6

    @pytest.mark.asyncio
    async def test_skips_fields_not_on_model(self, db_session):
        """update 对模型上不存在的字段静默跳过, 不抛 AttributeError。"""
        db_session.add(_template("T", [1]))
        await db_session.flush()

        service = TemplateService(db_session)
        record = await service.update(1, {"not_a_column": "x", "template_name": "保留"})

        assert record.template_name == "保留"
        assert not hasattr(record, "not_a_column")

    @pytest.mark.asyncio
    async def test_raises_when_record_missing(self, db_session):
        service = TemplateService(db_session)
        with pytest.raises(NotFoundError):
            await service.update(999999, {"template_name": "x"})


class TestDelete:
    @pytest.mark.asyncio
    async def test_returns_true_and_removes_record(self, db_session):
        db_session.add(_template("待删除", [1]))
        await db_session.flush()

        service = TemplateService(db_session)
        assert await service.delete(1) is True
        assert await service.get_by_id(1) is None

    @pytest.mark.asyncio
    async def test_returns_false_when_missing(self, db_session):
        service = TemplateService(db_session)
        assert await service.delete(999999) is False
