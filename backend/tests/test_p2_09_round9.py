"""P2 第九轮闸门：#32余量 + #33 + #35 + #39 + #40。"""

from __future__ import annotations

import inspect
import pathlib
import re

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]


class TestP232Remainder:
    def test_misclassified_no_local_csvescape(self):
        t = (REPO / "frontend/src/views/user/components/experiment-charts/MisclassifiedTable.vue").read_text(
            encoding="utf-8"
        )
        assert "const csvEscape" not in t, "仍有本地 csvEscape 定义（应改调 SSOT）"
        assert "csvEscape" in t and "exportUtils" in t

    def test_exportutils_exports_csvescape_with_sanitize(self):
        t = (REPO / "frontend/src/utils/exportUtils.ts").read_text(encoding="utf-8")
        assert "export const csvEscape" in t
        assert "sanitizeCellForExcel" in t

    def test_review_no_bare_counselor_literal(self):
        t = (REPO / "backend/app/api/v1/review.py").read_text(encoding="utf-8")
        assert 'role == "counselor"' not in t
        assert "USER_ROLE_COUNSELOR" in t

    def test_gdpr_admin_export_uses_record_audit(self):
        t = (REPO / "backend/app/api/v1/gdpr.py").read_text(encoding="utf-8")
        assert "record_audit" in t
        assert "admin.gdpr.export_user" in t


class TestP233AuditHelper:
    def test_tenant_id_required(self):
        from app.core.audit import record_audit

        sig = inspect.signature(record_audit)
        param = sig.parameters["tenant_id"]
        assert param.default is not inspect.Parameter.empty
        # 加固：默认值不得是 None（给 None 默认值 = 把"忘记传"变成静默的平台级操作，
        # 与 P0-1 租户隔离范式同口径）。必须是不可序列化的 sentinel。
        assert param.default is not None

    async def test_missing_tenant_id_raises(self):
        from app.core.audit import record_audit

        # 必须 match 消息特征：只断言异常类型会假绿 —— 即便显式 raise 被删，
        # json.dumps(object()) 也会抛 TypeError（消息为 "Object of type object is
        # not JSON serializable"），闸门根本守不住"缺失校验"这个意图。
        with pytest.raises(TypeError, match="tenant_id"):
            await record_audit(
                None,  # type: ignore[arg-type]
                actor_id=1,
                actor_role="admin",
                action="x",
                target_type="user",
                target_id=1,
            )

    async def test_sync_write_with_real_client_ip(self, db_session):
        from starlette.requests import Request

        from app.core.audit import record_audit
        from app.models.admin import OperationLog

        scope = {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("9.9.9.9", 1234),
        }
        req = Request(scope)
        log = await record_audit(
            db_session,
            actor_id=1,
            actor_role="admin",
            action="test.p2_33",
            target_type="user",
            target_id=2,
            detail={},
            request=req,
            tenant_id=None,
        )
        assert log.ip_address == "9.9.9.9"
        await db_session.commit()
        got = await db_session.get(OperationLog, log.id)
        assert got is not None and got.action_type == "test.p2_33"


class TestP235Degradation:
    def test_counter_exposed_in_exposition(self):
        from app.core.metrics import render_exposition, silent_degradation_total

        silent_degradation_total.inc(location="test.p2_35_probe")
        out = render_exposition()
        assert "silent_degradation_total" in out
        assert "test.p2_35_probe" in out

    def test_cache_silent_path_wired(self):
        t = (REPO / "backend/app/core/cache.py").read_text(encoding="utf-8")
        assert 'silent_degradation_total.inc(location="core.cache._get_redis_url")' in t

    def test_alert_tasks_raise(self):
        t = (REPO / "backend/app/tasks/alerts.py").read_text(encoding="utf-8")
        assert "raise exc" in t


class TestP239DeadCode:
    def test_bert_disabled_intentional(self):
        # 取证结论：bertDisabled=True 是有意保留的下线说明 UX（权重已归档，
        # 按钮禁用 + 警告文案），非无用死分支，故不断言删除，只断言意图明确。
        t = (REPO / "frontend/src/views/user/components/ExperimentTab.vue").read_text(
            encoding="utf-8"
        )
        assert "const bertDisabled = true" in t
        assert "experimentAssess.bertDisabled" in t

    def test_flushed_buffer_documented(self):
        t = (REPO / "backend/app/services/observability_service.py").read_text(encoding="utf-8")
        assert "RES-P1-004" in t  # 死缓冲区保留有书面依据，非静默残留


class TestP240Contract:
    def test_exposition_parses(self):
        from app.core.metrics import render_exposition, silent_degradation_total

        silent_degradation_total.inc(location="test.p2_40_probe")
        silent_degradation_total.inc(location="test.p2_40_probe_b")
        text = render_exposition()
        try:
            from prometheus_client.parser import text_string_to_metric_families

            fams = list(text_string_to_metric_families(text))
            assert len(fams) > 0
        except ImportError:
            # prometheus_client 非项目依赖（CI 无此包）：用严格自解析器
            # 断言 exposition 良构（HELP/TYPE 成对、样本行 name{labels} value）。
            seen_help: set[str] = set()
            seen_type: set[str] = set()
            samples = 0
            for line in text.splitlines():
                if line.startswith("# HELP "):
                    _, _, rest = line.partition("# HELP ")
                    name = rest.split(" ", 1)[0]
                    seen_help.add(name)
                elif line.startswith("# TYPE "):
                    _, _, rest = line.partition("# TYPE ")
                    name, _, typ = rest.partition(" ")
                    assert typ in {"counter", "gauge", "histogram"}
                    seen_type.add(name)
                elif line and not line.startswith("#"):
                    assert re.match(r"^[a-zA-Z_:][a-zA-Z0-9_:]*(\{.*\})? (-?\S+)$", line), line
                    samples += 1
            assert seen_help and seen_help == seen_type and samples >= 2

    def test_rules_yaml_shape(self):
        from app.core.alert_rules import ALERT_RULES, render_prometheus_rules

        assert len(ALERT_RULES) > 0
        doc = yaml.safe_load(render_prometheus_rules())
        rules = doc["groups"][0]["rules"]
        assert len(rules) == len(ALERT_RULES)
        for r in rules:
            assert "alert" in r and "expr" in r
            assert re.search(r"\S+ \S+ \S+", r["expr"])
