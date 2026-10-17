"""P2 第十一轮闸门：#39 死代码拆分裁定 + #33/#35 第一批 + #32 矛盾裁定 + #34 分类表同步。

反假闸门设计（沿用前几轮教训）：
- **不断言"文件/函数存在"，断言"不可达函数体消失 + 保留物仍在"**（#39 是拆分裁定，
  只判存在会把"保留"和"漏删"混为一谈 —— 第十轮复核正是这么判错的）。
- **计数棘轮必须同步审计文档**：断言里写死的数与 `docs/P2_11_ROUND11_AUDIT.md`
  中的登记数逐字比对，任一侧改动必须同时改另一侧（#38 范式）。
- **异常断言带 match**：本文件无异常断言；但所有"必须不存在"的判据都给出
  可定位的 file:line，避免"找不到"与"没扫到"混淆。
- **扫描器先自证**：`TestScannerSelfProof` 用临时违规文本证明判据能命中，
  防止"报 0 型假闸门"。
"""

from __future__ import annotations

import ast
import contextlib
import pathlib
import re
from datetime import datetime, timedelta, timezone

REPO = pathlib.Path(__file__).resolve().parents[2]
BE = REPO / "backend/app"
BEPKG = REPO / "backend"
FE = REPO / "frontend/src"
DOCS = REPO / "docs"

AUDIT = DOCS / "P2_11_ROUND11_AUDIT.md"
REGISTRY = DOCS / "RETENTION_REGISTRY.md"


def _scan_operation_log_calls() -> int:
    """生产代码里 `OperationLog(` 构造点数量（排除 helper 本体与测试）。"""
    n = 0
    for p in (BEPKG / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except Exception:
            continue
        rel = p.relative_to(BEPKG).as_posix()
        if rel == "app/core/audit.py":
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name == "OperationLog":
                    n += 1
    return n


def _count_degradation_wirings() -> int:
    """`record_silent_degradation(` 调用点数量（生产代码）。"""
    n = 0
    for p in (BEPKG / "app").rglob("*.py"):
        if "__pycache__" in p.parts or p.name == "degradation.py":
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except Exception:
            continue
        n += len(re.findall(r"record_silent_degradation\(", t))
    return n


class TestP239DeadCodeSplitRuling:
    """#39：保留 UX 常量 ≠ 保留不可达函数体。两侧都要断言。"""

    def test_bert_ux_constant_retained(self):
        # 保留侧：禁用态 + 解释文案仍在（RES-P2-039-01）
        t = (FE / "views/user/components/ExperimentTab.vue").read_text(encoding="utf-8")
        assert "const bertDisabled = true" in t, "BERT 下线 UX 常量应保留（有登记决议）"
        assert ":disabled=\"bertDisabled\"" in t, "禁用态应保留"
        assert "RES-P2-039-01" in t, "代码注释必须指向保留决议编号"

    def test_unreachable_bert_handlers_removed(self):
        # 移除侧：trainBert / evaluateBert 两个不可达函数体必须不存在
        t = (FE / "views/user/components/ExperimentTab.vue").read_text(encoding="utf-8")
        for fn in ("const trainBert", "const evaluateBert", "applyTrainResult", "applyEvaluateResult"):
            assert fn not in t, f"不可达函数体 {fn} 应已移除（F-32）"
        for click in ("@click=\"trainBert\"", "@click=\"evaluateBert\""):
            assert click not in t, f"禁用按钮不应再挂处理函数: {click}"

    def test_import_and_compare_buttons_guarded(self):
        # F-32 另一半：导入/对比按钮必须带 experimentLoading 守卫
        t = (FE / "views/user/components/ExperimentTab.vue").read_text(encoding="utf-8")
        assert t.count(':disabled="experimentLoading"') == 2, (
            "导入/对比两个按钮应各有 1 处 :disabled=\"experimentLoading\""
        )

    def test_bottomnav_dead_component_removed(self):
        assert not (FE / "components/common/BottomNav.vue").exists(), (
            "BottomNav.vue 已按 #39 处置结论删除（死组件：无 import 方、不在构建图）"
        )
        dts = (FE / "components.d.ts").read_text(encoding="utf-8")
        assert "BottomNav" not in dts, "components.d.ts 中的 BottomNav 声明应同步删除"

    def test_retention_registry_has_res_p1_004_body(self):
        # RES-P1-004 此前全仓只有"引用"没有正文 —— 第十一轮补登记册
        assert REGISTRY.exists(), "docs/RETENTION_REGISTRY.md 应存在"
        t = REGISTRY.read_text(encoding="utf-8")
        assert "RES-P1-004" in t
        for field in ("保留理由", "复核触发条件", "正文出处"):
            assert field in t, f"登记条目缺字段: {field}"
        assert "RES-P2-039-01" in t, "第十一轮的 BERT 拆分裁定应一并登记"

    def test_flushed_buffer_comment_matches_retention_decision(self):
        # 根因④活标本：注释必须与"有意保留"决策一致，否则下轮还会被当死代码扫出
        src = (BE / "services/observability_service.py").read_text(encoding="utf-8")
        doc = __import__("importlib").import_module(
            "app.services.observability_service"
        ).ObservabilityCollector.consume_flushed_logs.__doc__ or ""
        assert "RES-P1-004" in doc
        assert "有意保留" in doc, "docstring 必须写明'有意保留'，不能只写'死缓冲区'"
        assert "RETENTION_REGISTRY" in doc, "docstring 必须指向登记册正文"
        # 代码仍在（保留），不是被删
        assert "_flushed_buffer" in src


class TestOrphanComponentRatchet:
    """孤儿组件（无任何引用方的 .vue）棘轮：只降不升。

    BottomNav 是本轮删掉的那个；扫描发现仓库里还有 9 个其它孤儿组件
    （图表/插画/LanguageSelector 等），它们的处置属于产品决策，本轮**不删**，
    但用棘轮锁住"不得新增"，并在审计文档登记清单。
    """

    ORPHAN_BASELINE = 9

    def _orphans(self) -> list[str]:
        comps = sorted(
            p for p in (FE / "components").rglob("*.vue")
        )
        texts = []
        for p in (FE).rglob("*"):
            if p.suffix in {".vue", ".ts", ".tsx", ".js"} and ".test." not in p.name:
                try:
                    texts.append((p, p.read_text(encoding="utf-8")))
                except Exception:
                    pass

        def kebab(s: str) -> str:
            return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s).lower()

        out = []
        for c in comps:
            base = c.stem
            k = kebab(base)
            used = False
            for f, t in texts:
                if f == c:
                    continue
                if re.search(rf"from ['\"].*{re.escape(base)}['\"]", t):
                    used = True
                    break
                if re.search(rf"<{re.escape(base)}[\s/>]", t):
                    used = True
                    break
                if re.search(rf"<{re.escape(k)}[\s/>]", t):
                    used = True
                    break
                if f"'{base}'" in t or f'"{base}"' in t:
                    used = True
                    break
            if not used:
                out.append(c.relative_to(FE).as_posix())
        return out

    def test_orphan_count_not_increased(self):
        got = self._orphans()
        assert len(got) <= self.ORPHAN_BASELINE, (
            f"孤儿组件数 {len(got)} 超过棘轮 {self.ORPHAN_BASELINE}；"
            f"新增孤儿: {[g for g in got if g not in _AUDITED_ORPHANS]}"
        )

    def test_orphan_list_synced_with_audit_doc(self):
        got = set(self._orphans())
        assert AUDIT.exists(), "审计文档缺失，无法同步孤儿清单"
        doc = AUDIT.read_text(encoding="utf-8")
        for o in sorted(got):
            assert o in doc, f"孤儿组件 {o} 未登记进 {AUDIT.name}"


# 审计登记时的孤儿清单（删除 BottomNav 之后实测），用于"新增孤儿"的精确提示
_AUDITED_ORPHANS = {
    "components/charts/ModelPerformanceChart.vue",
    "components/charts/SystemHealthChart.vue",
    "components/common/illustrations/EmptyAssessment.vue",
    "components/common/illustrations/EmptyReport.vue",
    "components/common/illustrations/EmptyUser.vue",
    "components/common/illustrations/EmptyWarning.vue",
    "components/common/LanguageSelector.vue",
    "components/common/LazyImage.vue",
    "components/common/ThemeSwitcher.vue",
}


class TestP233AuditHelperRatchet:
    """#33 第一批：8 个手写审计点已迁 `record_audit`，构造点总数必须下降。"""

    BASELINE_BEFORE = 62  # 第十一轮开工实测（AST 口径，见审计文档）
    AFTER_BATCH1 = 54
    AFTER_BATCH2 = 51  # 第十二轮第二批：counselor.py 3 处（查看类审计日志）
    AFTER_BATCH3 = 44  # 第十二轮第三批：gdpr 2 + auth 助手 1 + uploads 1 + user_upload 2 + user_risk 1
    AFTER_BATCH4 = 37  # 第十二轮第四批：admin 2 + alerts 2 + helpers 1 + analytics 1 + reports 1（helpers 助手计入；扫描器口径不含 helper 本体）
    AFTER_BATCH5 = 34  # 第十二轮第五批：warning_service 3（服务层穿参打样：request/tenant 可选关键字，API 端点传入）
    AFTER_BATCH6 = 0  # 第十二轮第六批：余 24 全部收敛（counselor 3 服务 6 + admin_service 4 + monitoring 4 + 任务层 2 + gdpr 1 + user_intervention 1 + tenant_admin 4 + branding/export 2），app/ 下手写构造归零

    def test_operation_log_construct_sites_decreased(self):
        got = _scan_operation_log_calls()
        assert got == self.AFTER_BATCH6, (
            f"OperationLog( 生产构造点应为 {self.AFTER_BATCH6}，实际 {got}"
        )
        assert (
            got
            < self.AFTER_BATCH5
            < self.AFTER_BATCH4
            < self.AFTER_BATCH3
            < self.AFTER_BATCH2
            < self.AFTER_BATCH1
            < self.BASELINE_BEFORE
        )

    def test_migrated_files_no_longer_construct_operation_log(self):
        for rel in (
            "api/v1/silences.py",
            "api/v1/model_kill_switch.py",
            "api/v1/counselor.py",
            "api/v1/gdpr.py",
            "api/v1/auth.py",
            "api/v1/uploads.py",
            "api/v1/user_upload.py",
            "api/v1/user_risk.py",
            "api/v1/admin.py",
            "api/v1/alerts/__init__.py",
            "api/v1/alerts/_helpers.py",
            "api/v1/analytics_events.py",
            "api/v1/reports.py",
            "services/warning_service.py",
            "services/review_service.py",
            "services/intervention_service.py",
            "services/counselor_service_binding.py",
            # ── 第十二轮第六批（余 24 收敛，构造点 24 → 0）──
            "services/counselor_service_warning.py",
            "services/counselor_service_consultation.py",
            "services/counselor_service_group.py",
            "services/admin_service_config.py",
            "services/admin_service_threshold.py",
            "services/admin_service_template.py",
            "services/gdpr_service_anonymize.py",
            "monitoring/am_sync.py",
            "monitoring/dedup_lock.py",
            "monitoring/notifier.py",
            "monitoring/escalation.py",
            "tasks/anomaly_detection.py",
            "tasks/scheduler.py",
            "api/v1/user_intervention.py",
            "api/v1/tenant_admin.py",
            "api/v1/tenant_branding.py",
            "api/v1/tenant_export.py",
        ):
            t = (BE / rel).read_text(encoding="utf-8")
            assert "OperationLog(" not in t, f"{rel} 仍有手写 OperationLog 构造"
            assert "record_audit(" in t, f"{rel} 应改调 record_audit"

    @staticmethod
    def _record_audit_calls(rel: str) -> list[dict[str, str]]:
        """AST 提取文件内全部 record_audit 调用（解决正则无法处理嵌套括号截断）。

        背景：admin 导出调用的 detail 里含三元表达式括号，非贪婪正则
        会在内层右括号处提前截断，把 request=request 漏在匹配区之外 → 假红。
        AST 按关键字取，天然完整。返回每处调用的 {kwarg: 源码}。
        """
        import ast as _ast

        t = (BE / rel).read_text(encoding="utf-8")
        tree = _ast.parse(t)
        out: list[dict[str, str]] = []
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.Call):
                continue
            fn = node.func
            nm = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if nm != "record_audit":
                continue
            out.append({kw.arg or "*": _ast.unparse(kw.value) for kw in node.keywords})
        return out

    def test_migration_records_ip_from_request(self):
        # 迁移前这些点完全没有 ip_address；迁移后必须把 request 传进 helper。
        # webhook 系统路径（alerts 二处）无 request 可传，显式 request=None，
        # 由 test_system_paths_use_explicit_none 把守，不在此表。
        for rel in ("api/v1/silences.py", "api/v1/content_governance.py", "api/v1/model_kill_switch.py", "api/v1/counselor.py", "api/v1/gdpr.py", "api/v1/auth.py", "api/v1/uploads.py", "api/v1/user_upload.py", "api/v1/user_risk.py", "api/v1/admin.py", "api/v1/analytics_events.py", "api/v1/reports.py", "services/warning_service.py"):
            calls = self._record_audit_calls(rel)
            assert calls, f"{rel} 未找到 record_audit 调用"
            for c in calls:
                assert c.get("request") == "request", f"{rel} 的 record_audit 调用缺 request=request"
                assert "tenant_id" in c, f"{rel} 的 record_audit 调用缺 tenant_id（必填关键字）"

    def test_system_paths_use_explicit_none(self):
        # webhook 系统路径：无 user、无 request、无 tenant，必须显式三 None，
        # 禁止"忘记传"被 sentinel 误判为漏传 TypeError，也禁止手填 ip。
        # alerts/__init__.py 含 ack（有 request，走正常表）+ silenced（系统，走此表），
        # 故只断言"至少一处系统调用"，不断言全部。
        silenced = self._record_audit_calls("api/v1/alerts/__init__.py")
        sys_calls = [c for c in silenced if c.get("request") == "None"]
        assert sys_calls, "alerts silenced 路径必须有显式 request=None 的系统调用"
        for c in sys_calls:
            assert c.get("tenant_id") == "None"
        t = (BE / "api/v1/alerts/_helpers.py").read_text(encoding="utf-8")
        calls = self._record_audit_calls("api/v1/alerts/_helpers.py")
        assert calls, "alerts/_helpers.py 未找到 record_audit 调用"
        # helper 签名自带 operator_role="system" 默认，调用处透传形参，
        # 故此处只锁 request/tenant 双 None，不锁字面 role。
        assert 'operator_role: str = "system"' in t, "alerts/_helpers.py 系统角色默认值被改动"
        for c in calls:
            assert c.get("request") == "None", "alerts/_helpers.py 系统路径必须显式 request=None"
            assert c.get("tenant_id") == "None", "alerts/_helpers.py 系统路径必须显式 tenant_id=None"


class TestP235SilentDegradationRatchet:
    """#35 第一批：8 个真降级点接上 `record_silent_degradation`。"""

    BASELINE = 8

    def test_wiring_count(self):
        got = _count_degradation_wirings()
        assert got >= self.BASELINE, f"接线点 {got} < 棘轮 {self.BASELINE}"

    def test_helper_swallows_metric_failure(self):
        # helper 自身绝不能把 metrics 故障反弹给主流程（那是它存在的全部前提）
        import app.core.degradation as deg

        deg.record_silent_degradation("test.probe")  # 不得抛
        import unittest.mock as mock

        with mock.patch.dict("sys.modules", {"app.core.metrics": None}):
            deg.record_silent_degradation("test.probe.broken")  # 仍不得抛

    def test_wired_locations_documented(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc in (
            "core.ws.publish_to_user",
            "core.ws.broadcast",
            "core.event_bus.publish",
            "core.pii_crypto.process_result_value",
            "api.metrics_helpers.collect_ml_quality",
            "api.metrics_helpers.collect_drift",
            "api.metrics_helpers.collect_canary",
        ):
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    def test_batch6_bucket_counts_pinned(self):
        """第十二轮第六批 #35 收尾：候选清单**逐条裁定**后的桶计数棘轮。

        口径见 `tests/tools/classify_p2_35_batch6.py` 文档字符串（规则本身是
        交付物的一部分）。计数一变即红 → 强制重新跑扫描器+分类器并更新
        审计文档，防止「新增了一个静默降级却被静默放过」。

        桶含义（与分类器文档一致）：
          W 已接线 / P ImportError 特性探测 / S 自报失败 / D 脏数据探测 /
          C 清理路径 / H 检查型 / K 任务取消 / R 自恢复 / M 已有专用计数器 /
          G fail-closed 安全 / V 显式失败上报 / X 真降级留档（后续批待接）
        """
        import importlib.util

        tools = pathlib.Path(__file__).resolve().parent / "tools"
        spec = importlib.util.spec_from_file_location(
            "classify_p2_35_batch6", tools / "classify_p2_35_batch6.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        # 分类器读 scan 产物；先重跑 scan 保证不是陈旧快照
        scan_spec = importlib.util.spec_from_file_location(
            "scan_p2_35_batch6", tools / "scan_p2_35_batch6.py"
        )
        scan_mod = importlib.util.module_from_spec(scan_spec)
        scan_spec.loader.exec_module(scan_mod)  # type: ignore[attr-defined]
        scan_mod.main()  # 重新落盘 scan 产物
        import json as _json

        result = _json.loads(
            (tools / "scan_p2_35_batch6_result.json").read_text(encoding="utf-8")
        )
        counts: dict[str, int] = {}
        for rec in result["real_list"] + result["probe_list"]:
            p_ = BEPKG / rec["file"]
            try:
                src = p_.read_text(encoding="utf-8")
                tree = ast.parse(src)
            except Exception:
                continue
            target = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.lineno == rec["line"]:
                    target = node
                    break
            if target is None:
                continue
            fn_name = mod.enclosing(target, tree)
            body_src = mod.unparse(target)
            func_src = ""
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == fn_name:
                    if fn.lineno <= target.lineno <= (fn.end_lineno or fn.lineno):
                        func_src = mod.unparse(fn)
            bucket = mod.classify(rec, body_src, func_src)
            counts[bucket] = counts.get(bucket, 0) + 1

        expected = {
            "W": 97,   # 已接线（含第十一轮直调风格 2 处 + 第十二轮第五/六批 10 + 第十三轮前二十三批净 70：
                       # 第十九批纯裁定 +0，第二十批 alerts history detail 解析失败 +1，
                       # 第二十四批 ws 订阅循环崩溃重启窗口丢消息 +1）
            "P": 15,   # ImportError 特性探测（第十一批首次把探针记录本身接线：file_security
                        # 的 ImportError 探针分支 wired=True → W，P 16→15；总数 334 不变）
            "S": 36,   # 自报失败（metrics/sentry/otel/gauge）
            "D": 22,   # 脏数据探测
            "C": 7,    # 清理路径
            "H": 6,    # 检查型
            "K": 11,   # 任务取消
            "R": 3,    # 自恢复（第二十四批把 ws pubsub 循环崩溃从 R 改判接线：见下）
            "M": 6,    # 已有专用计数器
            "G": 8,    # fail-closed 安全
            "V": 2,    # 显式失败上报
            "F": 2,    # 保守 fail-safe（宁可少清理/不发）
            "X": 119,  # 真降级留档（第十九批纯裁定不变；第二十批 1 处实记录 X→W：
                       # 告警 history detail JSON 解析失败 → 空壳 item 照常入列表；
                       # 故 X 120→119、W 95→96；总数 334 不变。
                       # 第二十三批纯裁定不变；第二十四批接线的 ws pubsub 循环
                       # 崩溃原分类为 R（sleep+restart 自愈启发式），非 X，
                       # 故 X 维持 119、W 96→97、R 4→3。
                       # 前序口径：第十八批 3 处 X→W（金丝雀检查失败洗白 /
                       # 训练任务 Redis 列表回退 / 训练任务 Redis 更新失败），
                       # X 126→123→120、W 89→92→95；
                       # 第十七批 X 126→123、W 89→92；第十六批 X 130→126、W 85→89。）
        }
        assert counts == expected, (
            "#35 候选裁定桶计数发生变化，必须重跑 tests/tools/scan_p2_35_batch6.py "
            "+ classify_p2_35_batch6.py 并更新审计文档：\n"
            f"  got={dict(sorted(counts.items()))}\n  exp={dict(sorted(expected.items()))}"
        )

    def test_batch6_locations_wired_in_code_and_doc(self):
        """第十二轮第六批 4 个新接线点：源码与审计文档**双向**核对。

        只查文档会漏"登记了但没接线"，只查源码会漏"接了但没登记"，故两侧都要。
        """
        pairs = (
            (
                "services.risk_service_assessment.structured_predict_fallback",
                "services/risk_service_assessment.py",
            ),
            (
                "services.drift_monitoring_service.resolve_canary_version_failed",
                "services/drift_monitoring_service.py",
            ),
            (
                "services.shadow_comparison_service.commit_shadow_stats_failed",
                "services/shadow_comparison_service.py",
            ),
            (
                "api.validation.job_store.create.redis_fallback",
                "api/v1/validation.py",
            ),
            # ── 第十二轮第六批新增 5 个（含第五批漏登记的 4 个，一并收口）──
            (
                "core.model_engine.predict.text_ml_all_unavailable",
                "core/model_engine/predict.py",
            ),
            (
                "core.model_engine.predict.physiological_model_not_found",
                "core/model_engine/predict.py",
            ),
            (
                "core.model_engine.predict.physiological_prediction_failed",
                "core/model_engine/predict.py",
            ),
            (
                "tasks.scheduler.upload_reference_query_failed",
                "tasks/scheduler.py",
            ),
            (
                "tasks.pdf_report.save_pdf_bytes_failed",
                "tasks/pdf_report.py",
            ),
            (
                "api.model_predict._common.assessment_save_schedule_failed",
                "api/v1/model_predict/_common.py",
            ),
        )
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in pairs:
            src = (BE / rel).read_text(encoding="utf-8")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"


class TestP235Round13Batch1Wiring:
    """第十三轮第一批：#35 X 桶 7 处真降级接线。

    接线对象（X 桶 187 → 180，W 27 → 34，扫描器复跑实测）：
    - `api/v1/validation.py` 读路径 5 处：get/update/delete/list_jobs/count 的
      Redis→内存降级。写路径（create）已在第十二轮第五批接线；读路径同型但
      后果不同——任务"不存在/状态冻结/计数偏小"的假象直接呈现给用户，
      审计文档 6.5 节明确留待后续批。
    - `core/cache.py` 客户端初始化 2 处：共享客户端/pubsub 客户端创建失败
      是**根因性**降级——全仓缓存消费者（观测缓存/告警去重/任务存储/ws 推送）
      随后全部静默退回内存层，各消费点只看到"没有客户端"而不知根因。

    存在性→行为双断言：
    - 存在性：location 字面量在源码里 + 登记进审计文档（P2_11 附录第十三轮
      同步块，只查一侧会漏"登记了没接线"/"接了没登记"）；
    - 行为：真触发一次降级分支，`silent_degradation_total{location}` 必须 +1
      （接线了但计数器不动 = 假接线，与 #35 根因「失败不留痕」同罪）。
    """

    PAIRS = (
        ("api.validation.job_store.get.redis_fallback", "api/v1/validation.py"),
        ("api.validation.job_store.update.redis_fallback", "api/v1/validation.py"),
        ("api.validation.job_store.delete.redis_fallback", "api/v1/validation.py"),
        ("api.validation.job_store.list_jobs.redis_fallback", "api/v1/validation.py"),
        ("api.validation.job_store.count.redis_fallback", "api/v1/validation.py"),
        ("core.cache.redis_client_init_failed", "core/cache.py"),
        ("core.cache.redis_pubsub_client_init_failed", "core/cache.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_read_path_fallback_increments_counter(self):
        """行为：Redis 读操作抛异常 → get 走内存降级 → 计数器 +1。"""
        from app.api.v1.validation import ValidationJobStore
        from tests.conftest import run

        class _BrokenRedis:
            async def hgetall(self, key):
                raise ConnectionError("probe: redis down")

        store = ValidationJobStore()
        loc = "api.validation.job_store.get.redis_fallback"
        before = self._counter_value(loc)

        async def _broken_redis():
            return _BrokenRedis()

        # 直接给定一个必炸的客户端：绕过 _get_redis 的探测逻辑，精确打击
        # get 的 except 分支（生产路径是 Redis 连接在操作中途断开）
        store._get_redis = _broken_redis
        run(store.get("probe-job"))
        assert self._counter_value(loc) == before + 1, "读路径降级未计数（假接线）"

    def test_cache_client_init_failure_increments_counter(self, monkeypatch):
        """行为：from_url 抛异常 → 共享/pubsub 客户端初始化失败 → 两个 location 各 +1。"""
        import asyncio

        import app.core.cache as cache_mod
        from tests.conftest import run

        def _boom(*args, **kwargs):
            raise ValueError("probe: malformed redis url")

        # 隔离：全新锁（避免跨事件循环绑定）、无既有单例、URL 探测必返真值
        monkeypatch.setattr(cache_mod, "_redis_client_lock", asyncio.Lock())
        monkeypatch.setattr(cache_mod, "_redis_client", None)
        monkeypatch.setattr(cache_mod, "_redis_pubsub_client", None)
        monkeypatch.setattr(cache_mod, "_get_redis_url", lambda: "redis://probe")
        monkeypatch.setattr(cache_mod.aioredis, "from_url", _boom)

        loc1 = "core.cache.redis_client_init_failed"
        loc2 = "core.cache.redis_pubsub_client_init_failed"
        before1, before2 = self._counter_value(loc1), self._counter_value(loc2)
        run(cache_mod._get_redis_client())
        run(cache_mod.get_redis_pubsub_client())
        assert self._counter_value(loc1) == before1 + 1, "共享客户端初始化失败未计数（假接线）"
        assert self._counter_value(loc2) == before2 + 1, "pubsub 客户端初始化失败未计数（假接线）"


class TestP235Round13Batch2Wiring:
    """第十三轮第二批：#35 X 桶 6 处真降级接线（predict 5 + auto_rollback 1）。

    接线对象（X 174 / W 40，扫描器复跑实测）：
    - `core/model_engine/predict.py` 5 处：scaler 失败→未缩放数据算分、
      影子触发丢失（fire-and-forget）、cleaner 统计量缺失→原始输入、
      SHAP 失败→简单特征重要性（dict/array 两条路径）；
    - `services/auto_rollback_service.py` 1 处：回滚 savepoint 失败——
      results 里追加的仍是 should_rollback=True 的原始结果，数据结构
      在说谎，坏金丝雀继续生产服务而调用方无从得知。

    存在性→行为双断言同第一批；行为侧挑两个可确定触发点：
    影子触发（stub self + 必炸 sink）与回滚 savepoint（真 db_session +
      monkeypatch 四件套：锁/心跳/健康检查/回滚）。
    """

    PAIRS = (
        ("core.model_engine.predict.experimental_v121_scaler_fallback", "core/model_engine/predict.py"),
        ("core.model_engine.predict.shadow_predict_trigger_failed", "core/model_engine/predict.py"),
        ("core.model_engine.predict.physiological_cleaner_fallback", "core/model_engine/predict.py"),
        ("core.model_engine.predict.shap_factors_fallback", "core/model_engine/predict.py"),
        ("core.model_engine.predict.shap_factors_array_fallback", "core/model_engine/predict.py"),
        ("services.auto_rollback_service.rollback_savepoint_failed", "services/auto_rollback_service.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_shadow_trigger_failure_increments_counter(self, monkeypatch):
        """行为：影子 sink 抛异常 → fire-and-forget 样本丢失 → 计数器 +1。"""
        from app.core.config import settings
        from app.core.model_engine.predict import PredictMixin

        class _StubSelf:
            _shadow_sink = None

        class _BoomSink:
            def fire_shadow_predict(self, *args, **kwargs):
                raise RuntimeError("probe: shadow sink broken")

        stub = _StubSelf()
        stub._shadow_sink = _BoomSink()
        monkeypatch.setattr(settings, "shadow_mode_text_enabled", True, raising=False)
        loc = "core.model_engine.predict.shadow_predict_trigger_failed"
        before = self._counter_value(loc)
        # 同步方法（fire-and-forget 调用点无 await），stub self 即可精确打击
        PredictMixin._maybe_fire_shadow_predict(stub, "probe text", {"prediction": 1})
        assert self._counter_value(loc) == before + 1, "影子触发失败未计数（假接线）"

    async def test_rollback_savepoint_failure_increments_counter(
        self, db_session, monkeypatch
    ):
        """行为：execute_rollback 抛异常 → 回滚未发生但结果仍 should_rollback=True → 计数器 +1。"""
        import importlib

        from app.models.monitoring import CanaryRecord, CanaryStatus

        arb = importlib.import_module("app.services.auto_rollback_service")

        canary = CanaryRecord(
            version="v-probe-rollback",
            traffic_percent=50,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds={
                "max_fallback_rate": 0.05,
                "max_drift_alerts_per_hour": 10,
                "max_avg_latency_ms": 500.0,
            },
            triggered_by=None,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db_session.add(canary)
        await db_session.flush()

        service = arb.AutoRollbackService()

        async def _lock_ok(*args, **kwargs):
            return True

        async def _heartbeat_ok(*args, **kwargs):
            return True

        async def _check_should_rollback(session, canary_id):
            return arb.RollbackCheckResult(
                should_rollback=True,
                reason="probe",
                metrics={},
                canary_id=canary_id,
            )

        async def _rollback_boom(*args, **kwargs):
            raise RuntimeError("probe: rollback savepoint failed")

        # 四件套隔离：只留 savepoint 失败这一条路径为真
        monkeypatch.setattr(arb, "try_acquire_check_lock", _lock_ok)
        monkeypatch.setattr(arb, "publish_check_heartbeat", _heartbeat_ok)
        monkeypatch.setattr(service, "check_canary_health", _check_should_rollback)
        monkeypatch.setattr(service, "execute_rollback", _rollback_boom)

        loc = "services.auto_rollback_service.rollback_savepoint_failed"
        before = self._counter_value(loc)
        results = await service.check_all_canaries(db_session, source="probe")
        assert len(results) == 1
        assert results[0].should_rollback is True, "前置条件失效：结果应仍标记 should_rollback"
        assert self._counter_value(loc) == before + 1, "回滚 savepoint 失败未计数（假接线）"


class TestP235Round13Batch3Wiring:
    """第十三轮第三批：#35 X 桶 5 处真降级接线（tasks/pdf_report.py）。

    接线对象（X 169 / W 45，扫描器复跑实测）——第六批已接 `save_pdf_bytes_failed`
    （写入侧），本批补齐**任务侧其余四个 Redis 存取点 + 进度推送**，
    它们与写入侧同族（Redis 不可用时全部退化为「看不见」）：
    - `save_job_to_redis_failed`：任务状态写失败 → 用户轮询查不到任务；
    - `get_job_from_redis_failed`：读失败返回 None → 与「任务不存在」不可区分（假阴性）；
    - `list_jobs_from_redis_failed`：列表读失败返回 [] → 报告列表页凭空变空（部分数据）；
    - `get_pdf_bytes_failed`：字节读失败 → 下载接口拿不到报告；
    - `websocket_progress_notify_failed`：进度推送 fire-and-forget 丢失 → 进度条永远卡住。

    行为侧一次覆盖四个同步存取点（把 `_get_sync_redis` 换成必炸替身，
    真调四个公开函数），第五个（进度推送，需 ws 会话与 db 查询）
    由存在性断言守住并在此记账。
    """

    PAIRS = (
        ("tasks.pdf_report.save_job_to_redis_failed", "tasks/pdf_report.py"),
        ("tasks.pdf_report.get_job_from_redis_failed", "tasks/pdf_report.py"),
        ("tasks.pdf_report.list_jobs_from_redis_failed", "tasks/pdf_report.py"),
        ("tasks.pdf_report.get_pdf_bytes_failed", "tasks/pdf_report.py"),
        ("tasks.pdf_report.websocket_progress_notify_failed", "tasks/pdf_report.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_redis_access_failures_increment_counters(self, monkeypatch):
        """行为：Redis 不可用 → 四个存取点各走降级分支 → 对应计数器各 +1。"""
        import importlib

        pdf = importlib.import_module("app.tasks.pdf_report")

        def _boom():
            raise ConnectionError("probe: redis down")

        monkeypatch.setattr(pdf, "_get_sync_redis", _boom)

        locs = (
            "tasks.pdf_report.save_job_to_redis_failed",
            "tasks.pdf_report.get_job_from_redis_failed",
            "tasks.pdf_report.list_jobs_from_redis_failed",
            "tasks.pdf_report.get_pdf_bytes_failed",
        )
        before = {loc: self._counter_value(loc) for loc in locs}

        # 前置条件：降级分支的返回值本身就是「看不见」的形态
        assert pdf.get_job_from_redis("probe-job") is None
        assert pdf.list_jobs_from_redis() == []
        assert pdf.get_pdf_bytes_from_redis("probe-job") is None
        pdf.save_job_to_redis("probe-job", {"status": "running"})

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"


class TestP235WiringIsNotDeadCode:
    """全仓闸门：接线语句**不得位于 except handler 内 return/raise 之后**。

    第五批踩中：脚本按"logger.warning 块 + return"做锚点插入时，两处接线被插到
    `return None` / `return []` **之后** —— 语法合法、py_compile 通过、位置断言也能
    找到字面量，但**运行时永远执行不到**（假接线，与第四批的 am_sync 同族）。
    ⇒ 用 AST 扫全仓：handler 体里一旦出现过 return/raise，其后的接线即判死。
    读文件用 utf-8-sig：app/api/v1/__init__.py 带 BOM，直接 utf-8 读会解析失败。
    """

    def test_no_wiring_after_return_or_raise(self):
        bad: list[str] = []
        for f in sorted(BE.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8-sig"))
            except SyntaxError as exc:  # pragma: no cover - 语法错由 py_compile 抓
                raise AssertionError(f"{f.as_posix()} 解析失败: {exc}") from exc
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                terminated = False
                for stmt in node.body:
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Call) and (
                            getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                        ) == "record_silent_degradation":
                            if terminated:
                                bad.append(f"{f.relative_to(REPO).as_posix()}:{sub.lineno}")
                    if isinstance(stmt, (ast.Return, ast.Raise)):
                        terminated = True
        assert not bad, (
            "以下接线位于 return/raise 之后 = 永远执行不到的死接线: " + ", ".join(bad)
        )


class TestP235Round13Batch5Wiring:
    """第十三轮第五批：#35 X 桶 5 处接线（app/tasks/model_training.py 任务侧）。

    与第三批 `tasks/pdf_report` 同族（Celery worker 侧 Redis 存取），外加一条
    本批最高价值的点：
    - `artifact_register_failed`：产物已落盘但注册表里没有它 → 该模型无法被激活
      上线，这次训练等于白跑。
    其余四条：任务状态写失败 / 读失败 None（与"任务不存在"不可区分）/ 列表读失败
    []（列表凭空变空）/ 状态更新丢失（进度停在旧值）。

    **调用链已逐个追过**（第四批教训）：四处是叶子级 Redis 调用；`register_training_artifact`
    → `registry.register_model` 也不吞异常 ⇒ 失败确实落在这些 handler 里。
    行为侧把 `_get_sync_redis` 换成必炸替身后真调四个同步存取点；
    产物注册点 patch `model_registry_v2.register_training_artifact` 抛异常。
    """

    PAIRS = (
        ("tasks.model_training.save_job_to_redis_failed", "tasks/model_training.py"),
        ("tasks.model_training.get_job_from_redis_failed", "tasks/model_training.py"),
        ("tasks.model_training.list_jobs_from_redis_failed", "tasks/model_training.py"),
        ("tasks.model_training.update_job_in_redis_failed", "tasks/model_training.py"),
        ("tasks.model_training.artifact_register_failed", "tasks/model_training.py"),
        # 非 except 路径（提前 return）：训练完成但产物目录缺失 → 注册表永远没有它
        ("tasks.model_training.artifact_dir_missing", "tasks/model_training.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_all_six_increment_counters(self, monkeypatch, tmp_path):
        """行为：Redis 不可用 / 产物目录缺失 / 注册写入失败 → 六处各 +1。

        产物注册点需要真实存在的 artifact 目录（否则走 `artifact_dir_missing` 的
        提前 return，根本到不了注册调用）——故把 TRAINED_ROOT patch 到 tmp_path，
        分两次调用分别覆盖"目录缺失"与"注册抛异常"两条降级路径。
        """
        import app.core.model_registry_v2 as reg_v2
        import app.services.experiment_trainer as trainer
        import app.tasks.model_training as mt

        def _boom():
            raise ConnectionError("probe: redis down")

        def _reg_boom(*args, **kwargs):
            raise RuntimeError("probe: registry write failed")

        monkeypatch.setattr(mt, "_get_sync_redis", _boom)
        monkeypatch.setattr(reg_v2, "register_training_artifact", _reg_boom)
        monkeypatch.setattr(trainer, "TRAINED_ROOT", tmp_path)

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # 降级返回值形态本身就是"看不见"：None / []
        assert mt.get_job_from_redis("probe-job") is None
        assert mt.list_jobs_from_redis() == []
        mt.save_job_to_redis("probe-job", {"status": "running"})
        mt.update_job_in_redis("probe-job", status="completed")
        # ① 目录不存在 → 提前 return 路径
        mt._register_training_artifact("probe-missing", "probe-ds", 1, 32, 0.01, {})
        # ② 目录存在但注册写入失败 → exception handler 路径
        (tmp_path / "probe-present").mkdir()
        mt._register_training_artifact("probe-present", "probe-ds", 1, 32, 0.01, {})

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"


class TestP235Round13Batch6Wiring:
    """第十三轮第六批：#35 X 桶 4 处接线（三文件，按第四批纪律先追过调用链）。

    - `services.model_predict.training_jobs.load_failed`：启动快照读失败 →
      TRAINING_JOBS 为空，重启后所有训练任务在管理端"不存在"；
    - `...training_jobs.save_failed`：快照写失败 → 任务状态只在进程内存，重启即丢；
    - `api.alerts.webhook.final_commit_failed`：webhook 末尾 commit 失败 → 本请求
      逐条 savepoint 落库的告警一起回滚，但响应仍 200 且 `failed=0`（逐条计数统计
      不到 commit），**响应与数据结构双双说谎**，告警审计整批丢失；
    - `services.observability.aggregate.lock_stats_unavailable`：dedup_lock 统计读
      失败时回填四个 0，观测页把它当真实数据展示——**假数据比缺数据更危险**。

    同簇的 8 条已记账跳过（理由见 P2_11 附录）：training_jobs 的 get/list/update
    三处失败其实落在第五批刚接线的被调方（`tasks.model_training.*`）或已有
    `storage_degraded` 可见标志；`alerts` 的 detail 解析退化是脏数据且有 warning；
    registry 的 promote 失败以 None 上抛（调用方可见）、quarantine 失败属嵌套清理；
    inference 的 persist 失败下轮自愈（R 型）、Prometheus 上报失败属 S 型。

    运行时覆盖三处（training_jobs 两处用其可注入的 loader/dumper 触发、aggregate
    patch `dedup_lock.get_stats`）；alerts 的 commit 失败**未做运行时断言**——
    它在FastAPI 端点内，测试环境的 `get_db` override 把 `session.commit` 绑成实例
    属性，无法在不伪造整套依赖注入的前提下触发，故只由存在性断言守住并记账。
    """

    PAIRS = (
        ("services.model_predict.training_jobs.load_failed", "services/model_predict/training_jobs.py"),
        ("services.model_predict.training_jobs.save_failed", "services/model_predict/training_jobs.py"),
        ("api.alerts.webhook.final_commit_failed", "api/v1/alerts/__init__.py"),
        ("services.observability.aggregate.lock_stats_unavailable", "services/observability/aggregate.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_training_jobs_snapshot_failures_increment(self, monkeypatch, tmp_path):
        """行为：快照读/写失败 → 两个计数器各 +1（用模块自带的可注入 loader/dumper）。"""
        import app.services.model_predict.training_jobs as tj

        snapshot = tmp_path / "training_jobs.json"
        snapshot.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(tj, "_TRAINING_JOBS_FILE", snapshot)

        def _loader_boom(*args, **kwargs):
            raise OSError("probe: snapshot unreadable")

        def _dumper_boom(*args, **kwargs):
            raise OSError("probe: snapshot unwritable")

        locs = (
            "services.model_predict.training_jobs.load_failed",
            "services.model_predict.training_jobs.save_failed",
        )
        before = {loc: self._counter_value(loc) for loc in locs}
        tj._load_training_jobs(load_json=_loader_boom)
        tj._save_training_jobs(dump_json=_dumper_boom)
        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"

    def test_lock_stats_unavailable_increments(self, monkeypatch):
        """行为：dedup_lock 统计读失败 → 计数器 +1（同时验证返回的是全 0 假数据）。"""
        import app.monitoring.dedup_lock as dl
        import app.services.observability.aggregate as agg

        def _boom(*args, **kwargs):
            raise RuntimeError("probe: lock stats unavailable")

        monkeypatch.setattr(dl, "get_stats", _boom)
        loc = "services.observability.aggregate.lock_stats_unavailable"
        before = self._counter_value(loc)
        stats, last_flush = agg._fetch_lock_memory_stats()
        assert stats == {"acquired": 0, "skipped": 0, "fallback": 0, "errors": 0}
        assert last_flush is None
        assert self._counter_value(loc) == before + 1, "锁统计降级未计数（假接线）"


class TestP235Round13Batch7Wiring:
    """第十三轮第七批：#35 X 桶 2 处接线（`core/model_engine/loading.py`）。

    本簇 8 条里 6 条记账跳过（理由见 P2_11 附录）：82（侧车不可读）与 425
    （adapter 加载失败）均已被调用方 `_incr_model_fallback` 计数（M 型）；
    284/290 是 preload 的 critical 日志（loud）；588 是本地无缓存→Hub 下载的
    设计内回退；704 是 sklearn 兼容补丁的 best-effort（失败后下游 transform 可见）。
    剩下这两条是调用链确认过的真沉默：

    - `...loading.audit_path_resolve_failed`：该模型随后被 `skipped`，不仅不进
      `missing` 清单，调用方（preload）还丢弃了整个 summary 返回值——它就这样
      静默逃过完整性审计（锚点是否存在从此无人再问）。触发 `resolve_model_path`
      抛异常即可；
    - `...loading.keras_compat_load_failed`：Keras 二次加载失败后本函数直接
      `return None`，调用方按“没有这个模型”走 fallback（分数通道彻底缺席，却和
      “从未配置”无法区分）。patch `tf.keras.models.load_model` 抛异常即可。
    """

    PAIRS = (
        ("core.model_engine.loading.audit_path_resolve_failed", "core/model_engine/loading.py"),
        ("core.model_engine.loading.keras_compat_load_failed", "core/model_engine/loading.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_audit_path_resolve_failure_increments(self, monkeypatch):
        """行为：审计中某模型路径解析失败 → 计数器 +1（该模型被 skipped 静默逃审）。"""
        import app.core.model_engine.loading as ld

        def _boom(*args, **kwargs):
            raise RuntimeError("probe: path resolve failed")

        # loading.py 用 `from app.core.model_registry import ... resolve_model_path`
        # —— 必须 patch 使用方命名空间（ld），patch 定义方（mr）对它不可见。
        monkeypatch.setattr(ld, "resolve_model_path", _boom)
        loc = "core.model_engine.loading.audit_path_resolve_failed"
        before = self._counter_value(loc)
        # 审计遍历所有模型；patch 全局后每个"已启用"模型都在 resolve 处失败并计数。
        enabled = [m for m in ld.MODEL_PATHS if ld.is_model_enabled(m)]
        summary = ld.audit_model_integrity_anchors()
        assert summary["missing_anchors"] == []  # 解析失败者不进 missing 清单
        assert len(enabled) >= 1, "测试前提：至少一个模型处于启用态"
        assert (
            self._counter_value(loc) == before + len(enabled)
        ), "审计路径解析降级未计数（假接线）"

    def test_keras_compat_load_failure_increments(self, monkeypatch, tmp_path):
        """行为：Keras 兼容重载失败 → 计数器 +1（模型返回 None，静默 fallback）。

        真调 `_load_model` 的 .keras 分支：注入探针模型使前置守卫全过；第一次
        `tf.keras.models.load_model` 抛带 quantization_config 的 ValueError 进兼容
        分支，第二次（兼容重载）抛 RuntimeError → 落到新接线。
        """
        import sys
        import threading
        import types

        import app.core.model_engine.loading as ld
        from app.core.model_engine import ModelEngine

        keras_file = tmp_path / "probe.keras"
        keras_file.write_bytes(b"probe")

        calls = {"n": 0}

        def _load_model_router(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("probe: bad quantization_config payload")
            raise RuntimeError("probe: keras compat reload failed")

        fake_models = types.SimpleNamespace(load_model=_load_model_router)
        fake_tf = types.ModuleType("tensorflow")
        fake_tf.keras = types.SimpleNamespace(models=fake_models)
        monkeypatch.setitem(sys.modules, "tensorflow", fake_tf)

        fake_dense_mod = types.ModuleType("keras.src.layers.core.dense")

        class _DenseStub:
            @classmethod
            def from_config(cls, config):  # noqa: ANN001
                return object()

        fake_dense_mod.Dense = _DenseStub
        monkeypatch.setitem(sys.modules, "keras.src.layers.core.dense", fake_dense_mod)

        # 前置守卫：model_id 在 MODEL_PATHS 且 enabled
        monkeypatch.setitem(ld.MODEL_PATHS, "probe_keras", "probe_keras.pkl")
        monkeypatch.setattr(ld, "is_model_enabled", lambda _mid: True)
        monkeypatch.setattr(
            ModelEngine, "_abs_path", lambda self, _rel: keras_file
        )

        engine = ModelEngine.__new__(ModelEngine)
        engine.models = {}
        engine._cache_lock = threading.Lock()
        engine._cache_maxsize = 10
        engine._cache_evictions = 0
        engine.model_load_stats = {"probe_keras": {"cache_hits": 0}}

        loc = "core.model_engine.loading.keras_compat_load_failed"
        before = self._counter_value(loc)
        assert engine._load_model("probe_keras") is None
        assert calls["n"] == 2, "必须走到第二次 load_model（兼容重载分支）"
        assert (
            self._counter_value(loc) == before + 1
        ), "Keras 兼容重载降级未计数（假接线）"


class TestP235Round13Batch8Wiring:
    """第十三轮第八批：#35 X 桶 4 处接线（`services/anomaly_detection_service.py`）。

    `detect_all` 聚合 4 个安全异常检测器（高频撞库 / 非工作时间 / 异地 / 横向
    越权），每个各自 try/except 吞掉异常并继续。任一检测器失败 → 该类异常**整类
    漏检**，而调用方（Celery `scan_anomalies`）只拿到合并后的 findings 列表，
    "本次没有异常"与"检测器宕机"无法区分 —— 静默安全盲区。四处全部接线。
    """

    PAIRS = (
        ("services.anomaly_detection.high_frequency_detection_failed", "services/anomaly_detection_service.py"),
        ("services.anomaly_detection.off_hours_detection_failed", "services/anomaly_detection_service.py"),
        ("services.anomaly_detection.cross_region_detection_failed", "services/anomaly_detection_service.py"),
        ("services.anomaly_detection.lateral_detection_failed", "services/anomaly_detection_service.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_all_four_detectors_increment_on_failure(self, monkeypatch):
        """行为：四个检测器各抛异常 → 对应计数器各 +1（且 detect_all 仍返回已聚合项）。"""
        import app.services.anomaly_detection_service as mod

        monkeypatch.setattr(mod.settings, "anomaly_detection_enabled", True)

        def _boom(*args, **kwargs):
            raise RuntimeError("probe: detector down")

        monkeypatch.setattr(mod, "detect_high_frequency", _boom)
        monkeypatch.setattr(mod, "detect_off_hours", _boom)
        monkeypatch.setattr(mod, "detect_cross_region", _boom)
        monkeypatch.setattr(mod, "detect_lateral_access", _boom)

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}
        findings = await mod.detect_all(None)
        assert findings == []  # 全部失败仍返回空列表（与"无异常"同形 = 静默所在）
        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"


class TestP235Round13Batch9Wiring:
    """第十三轮第九批：#35 X 桶 2 处接线（`services/canary_fallback_monitor.py`）。

    该模块是 Celery 不可用时的**最后安全网**（金丝雀自动回滚的兜底监控）：
    - `...rollback_check_failed`：接管后 `check_all_canaries` 本体抛异常 → 超阈值
      金丝雀无人回滚（故障扩大），且只记 error 日志。运行时 patch
      `check_all_canaries` 抛异常 + patch 计数器直接推进断言；
    - `...loop_unexpected_error`：循环内未预期异常 → 本轮接管判定/回滚机会错过
      但循环继续。运行时让 `get_check_heartbeat_age` 抛异常即可直达（外层 except）。

    本簇 4 条里余 2 条记账跳过（理由见 P2_11 附录）：67（`_bump_takeover_counter`
    自身失败）是 S 型；88（breaker 快照失败）走附加信号降级为主判据心跳——若连
    心跳也读不到则落在第三批已接线的 `get_check_heartbeat_age` 被调方，不重复计数。
    """

    PAIRS = (
        ("services.canary_fallback_monitor.rollback_check_failed", "services/canary_fallback_monitor.py"),
        ("services.canary_fallback_monitor.loop_unexpected_error", "services/canary_fallback_monitor.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_rollback_check_failure_increments(self, monkeypatch):
        """行为：接管后回滚检查抛异常 → 计数器 +1（超阈值金丝雀无人回滚）。

        接管判定用 breaker 非 closed（不碰 Redis 心跳）；`check_all_canaries`
        是 `auto_rollback_service` **单例的方法**（非模块函数），故 patch
        单例属性。注意 `import ... as ars` 拿到的是被包 `__init__` 同名
        from-import 遮蔽后的单例（见下个测试 docstring），这里正好是要打
        单例，误打误中但语义正确。
        """
        import asyncio

        import app.services.auto_rollback_service as ars_singleton_shadow
        import app.services.canary_fallback_monitor as mod

        async def _boom(*args, **kwargs):
            raise RuntimeError("probe: check_all_canaries failed")

        async def _sleep_once(_secs):
            raise asyncio.CancelledError()

        monkeypatch.setattr(mod.asyncio, "sleep", _sleep_once)
        monkeypatch.setattr(
            ars_singleton_shadow, "check_all_canaries", _boom
        )
        import app.core.celery_breaker as cb

        monkeypatch.setattr(
            cb.celery_breaker, "get_state_snapshot", lambda: {"state": "open"}
        )
        loc = "services.canary_fallback_monitor.rollback_check_failed"
        before = self._counter_value(loc)
        import pytest

        with pytest.raises(asyncio.CancelledError):
            await mod._canary_fallback_loop()
        assert (
            self._counter_value(loc) == before + 1
        ), "兜底回滚检查降级未计数（假接线）"

    async def test_loop_unexpected_error_increments(self, monkeypatch):
        """行为：心跳年龄读取抛异常 → 外层 except → 计数器 +1（本轮canary 不被检查）。

        踩坑：`app.services.__init__` 从 `auto_rollback_service` 模块里
        from-import 了同名单例 `auto_rollback_service`（类实例）并挂到包属性上，
        于是 `import app.services.auto_rollback_service as ars` 拿到的是**实例**
        而非模块。必须用 `importlib.import_module` 拿真模块再 patch。
        """
        import asyncio
        import importlib

        import app.services.canary_fallback_monitor as mod

        async def _boom(*args, **kwargs):
            raise RuntimeError("probe: heartbeat unreadable")

        async def _cancel_immediately(_secs):
            raise asyncio.CancelledError()

        import app.core.celery_breaker as cb

        monkeypatch.setattr(
            cb.celery_breaker, "get_state_snapshot", lambda: {"state": "closed"}
        )
        ars_mod = importlib.import_module("app.services.auto_rollback_service")
        monkeypatch.setattr(ars_mod, "get_check_heartbeat_age", _boom)
        monkeypatch.setattr(mod.asyncio, "sleep", _cancel_immediately)
        loc = "services.canary_fallback_monitor.loop_unexpected_error"
        before = self._counter_value(loc)
        import pytest

        with pytest.raises(asyncio.CancelledError):
            await mod._canary_fallback_loop()
        assert self._counter_value(loc) == before + 1, "兜底循环异常降级未计数（假接线）"


class TestP235Round13Batch10Wiring:
    """第十三轮第十批：#35 X 桶 4 处接线（`services/shadow_comparison_service.py`）。

    影子对拍是训练产物激活前的**质量门**：样本累积 → 一致率 → 激活校验。四处失败
    全部只记 debug/warning 日志，样本或整条管线静默丢失，最终都收敛到同一种失效：
    `is_shadow_acceptable` 恒返回 `(True, "insufficient_samples(...)")` ——
    **证据不足放行**，坏模型可直接激活上线。
    - `...fire_no_event_loop_skipped`：生产路径无事件循环时该样本对拍直接跳过；
    - `...shadow_check_failed`：管线内未预期异常，本样本丢失；
    - `...candidate_load_failed`：候选产物加载失败，该模型对拍管线实质死亡；
    - `...candidate_predict_failed`：候选预测失败，样本以 (None, None) 丢弃。
    """

    PAIRS = (
        ("services.shadow_comparison_service.fire_no_event_loop_skipped", "services/shadow_comparison_service.py"),
        ("services.shadow_comparison_service.shadow_check_failed", "services/shadow_comparison_service.py"),
        ("services.shadow_comparison_service.candidate_load_failed", "services/shadow_comparison_service.py"),
        ("services.shadow_comparison_service.candidate_predict_failed", "services/shadow_comparison_service.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_all_four_shadow_failures_increment(self, monkeypatch):
        """行为：四条失败路径各触发一次 → 对应计数器各 +1。"""
        import asyncio

        import app.services.shadow_comparison_service as mod

        svc = mod.ShadowComparisonService()
        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 无事件循环：本测试本身跑在事件循环内（async 测试），直接调 fire
        # 反而会成功建 task。故把调用丢进 worker 线程（无 running loop），
        # create_task 必抛 RuntimeError。sample_rate=1.0 保证不抽样早退。
        import asyncio as _asyncio

        await _asyncio.to_thread(
            svc.fire_shadow_check, "probe_model", {}, {"prediction": 0}, 1.0
        )

        # ② 管线内未预期异常：registry 返回无候选后很难抛——patch _load_candidate
        #    抛异常穿透到 _shadow_check 外层 except（asyncio.to_thread 不介入）。
        def _load_boom(_path):
            raise RuntimeError("probe: load exploded")

        monkeypatch.setattr(svc, "_load_candidate", _load_boom)
        fake_record = type("R", (), {"status": "CANDIDATE", "artifact_path": "x.pkl"})()
        fake_registry = type(
            "G", (), {"get_model": lambda self, _mid: fake_record}
        )()
        import sys
        import types

        fake_v2 = types.ModuleType("app.core.model_registry_v2")
        fake_v2.get_registry = lambda: fake_registry
        fake_v2.ModelStatus = type(
            "MS", (), {"CANDIDATE": "CANDIDATE", "STAGING": "STAGING"}
        )()
        monkeypatch.setitem(sys.modules, "app.core.model_registry_v2", fake_v2)
        await svc._shadow_check("probe_model", {}, {"prediction": 0})
        # 恢复：③ 需要真实的 _load_candidate（上面 patch 的必炸版会干扰）。
        monkeypatch.undo()

        # ③ 候选加载失败：真实走 _load_candidate 的 except（不存在的路径抛异常）。
        #    safe_joblib_load 在缺失路径上行为不定——用目录 + 缺失 phys 文件：
        #    直接给一个损坏的 .pkl 内容抛异常更可靠。
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.pkl"
            bad.write_bytes(b"not-a-pickle\xff\xfe")
            assert svc._load_candidate(str(bad)) is None

        # ④ 候选预测失败：predict 抛异常的对象。
        class _BadModel:
            def predict(self, _x):
                raise RuntimeError("probe: predict exploded")

        assert svc._candidate_predict(_BadModel(), None) == (None, None)

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"


class TestP235Round13Batch11Wiring:
    """第十三轮第十一批：#35 X 桶 2 处接线（`services/file_security_service.py`）。

    上传安全网的 fail-open 降级放行：`scan_with_clamav` 在依赖缺失/clamd 不可用/
    扫描异常且运维显式开启 `clamav_fail_open` 时返回 `(True, ...)` —— 文件被当作
    "已扫描通过"保留，调用方 `process_uploaded_file` 只看到 True，与"干净"无法
    区分。降级放行只记 warning 日志，无计数。三处 fail-open 分支各一处接线。

    同文件第 118 行（EXIF 剥离失败）与 `excel_export_service.py` 3 处**不接线、
    留档**：前者返回 `(False, ...)`，调用方直接拒绝保留（调用方可⻅的 V 型）；
    后者三处全部返回 `success=False + error_message` 结构化失败，调用方同样
    可见。接线只会给"调用方已处理"的路径加恒 0/恒可见计数，是第四批 silences
    教训的反例，故文档裁。
    """

    PAIRS = (
        ("services.file_security.clamav_dependency_missing_fail_open", "services/file_security_service.py"),
        ("services.file_security.clamav_unavailable_fail_open", "services/file_security_service.py"),
        ("services.file_security.clamav_error_fail_open", "services/file_security_service.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_all_three_fail_open_branches_increment(self, monkeypatch, tmp_path):
        """行为：fail-open 开启时依赖缺失/clamd 不可用/扫描异常 → 放行且各 +1。"""
        import sys
        import types

        import app.services.file_security_service as mod

        monkeypatch.setattr(mod.settings, "enable_clamav_scan", True)
        monkeypatch.setattr(mod.settings, "clamav_fail_open", True)
        target = tmp_path / "probe.bin"
        target.write_bytes(b"probe")

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 依赖缺失：本仓默认无 pyclamd，ImportError 分支真实可达。
        ok, msg = mod.scan_with_clamav(target)
        assert ok is True and "fail-open" in msg

        # ②/③ 注入假 clamd：NetworkSocket 建连抛 ConnectionError / scan 抛异常。
        class _FakeConnError(Exception):
            pass

        mode = {"scan_boom": False}

        class _FakeSocket:
            def __init__(self, *args, **kwargs):
                raise _FakeConnError("probe: clamd down")

        class _FakeSocket2:
            def __init__(self, *args, **kwargs):
                pass

            def scan(self, _path):
                if mode["scan_boom"]:
                    raise RuntimeError("probe: scan exploded")
                return {str(_path): ("OK", None)}

        fake = types.ModuleType("clamd")
        fake.ConnectionError = _FakeConnError
        fake.ClamdNetworkSocket = _FakeSocket
        fake.ClamdUnixSocket = _FakeSocket2
        monkeypatch.setitem(sys.modules, "clamd", fake)
        monkeypatch.setattr(mod.settings, "clamav_unix_socket", None)

        # ② clamd 不可用 → fail-open 放行。
        ok, msg = mod.scan_with_clamav(target)
        assert ok is True and "fail-open" in msg

        # ③ 扫描异常 → fail-open 放行。
        fake.ClamdNetworkSocket = _FakeSocket2
        mode["scan_boom"] = True
        ok, msg = mod.scan_with_clamav(target)
        assert ok is True and "fail-open" in msg

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    def test_reclassified_five_have_no_counter(self):
        """反向钉：改判移除的 5 处不得再出现通用计数器接线。

        它们有 `am_sync_failed` OperationLog 落点，计数器恒为 0 会误导运维；
        若将来有人"顺手补个计数"，必须先推翻本裁定。
        """
        src = (BE / "api/v1/silences.py").read_text(encoding="utf-8")
        for loc in (
            "api.silences.create.am_sync_failed",
            "api.silences.update.am_delete_failed",
            "api.silences.update.am_push_failed",
            "api.silences.enable.am_push_failed",
            "api.silences.delete.am_sync_failed",
        ):
            assert f'"{loc}"' not in src, (
                f"{loc} 已改判为 M/V 型（am_sync 内部写 am_sync_failed OperationLog），"
                f"不得再接通用计数器——否则计数器恒为 0 误导运维"
            )

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_rollback_compensation_failure_increments_counter(self, monkeypatch):
        """行为：commit 失败 → 补偿删除再失败（db=None 无 OperationLog）→ 计数器 +1。

        直接调端点函数 + 假 session，不走 HTTP：测试环境的 `get_db` override 把
        `session.commit` **绑成实例属性**（`= session.flush`，见 conftest
        `override_db_dependency`），类级 patch 拦不住，走 HTTP 也无法让 commit 失败
        ——本批首版就是这么写成"假绿"的（响应仍是 200，计数器没动）。
        """
        import asyncio

        import pytest

        import app.monitoring.am_sync as am_sync
        from app.api.v1.silences import SilenceCreate, create_silence

        class _FakeSession:
            def add(self, obj):
                return None

            def begin_nested(self):
                class _CM:
                    async def __aenter__(self):
                        return None

                    async def __aexit__(self, *exc):
                        return False

                return _CM()

            async def commit(self):
                raise RuntimeError("probe: commit failed")

            async def flush(self):
                return None

            async def rollback(self):
                return None

        class _FakeUser:
            id = 1
            role = "admin"

        async def _push_ok(*args, **kwargs):
            return {"silenceID": "probe-am-id"}

        async def _delete_boom(*args, **kwargs):
            raise RuntimeError("probe: AM delete unavailable during rollback")

        monkeypatch.setattr(am_sync, "push_silence", _push_ok)
        monkeypatch.setattr(am_sync, "delete_silence", _delete_boom)

        loc = "api.silences.create.am_rollback_failed"
        before = self._counter_value(loc)
        now = datetime.now(timezone.utc)
        payload = SilenceCreate(
            name="probe-rollback",
            matcher={"alertname": "ProbeAlert"},
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=2),
        )
        # commit 失败 → 端点按契约把异常抛给调用方；补偿分支已在抛错前执行
        with pytest.raises(RuntimeError, match="probe: commit failed"):
            asyncio.run(
                create_silence(payload, db=_FakeSession(), current_user=_FakeUser())
            )
        assert self._counter_value(loc) == before + 1, "补偿删除失败未计数（假接线）"


class TestP232ModelMetadataContradictionRecorded:
    """#32 模型元数据：审计结论（"无第二定义处"）与审查原文（3 份）硬矛盾。

    本轮**只裁定不合并**：三份定义处实测都还在，用事实锁固定；将来任一份被合并或
    删除，本测试会红 → 强制同步审计文档，防止"悄悄改了但文档还写着没改"。
    """

    def test_four_definition_sites_still_exist(self):
        # 实测：模型元数据有 **4 处**定义（审查原文说 3 份，第九轮审计说"无第二定义处"）
        reg = (BE / "core/model_registry.py").read_text(encoding="utf-8")
        compat = (BE / "core/model_compatibility.py").read_text(encoding="utf-8")
        v2 = (BE / "core/model_registry_v2.py").read_text(encoding="utf-8")
        assert "MODEL_PATHS: dict[str, str]" in reg, "MODEL_PATHS 定义处应仍在"
        assert "MODEL_REGISTRY: dict[str, ModelMetadata]" in reg, "MODEL_REGISTRY 定义处应仍在"
        assert (
            "MODEL_COMPATIBILITY_REGISTRY: dict[str, ModelCompatibilityInfo]" in compat
        ), "MODEL_COMPATIBILITY_REGISTRY 定义处应仍在"
        assert "class ModelRegistryV2" in v2, "registry_v2 定义处应仍在"

    def test_risk_label_duality_still_exists(self):
        # low/medium（契约输出） vs mild/moderate（分档阈值键）两套标签并存
        risk = (BE / "core/model_engine/risk.py").read_text(encoding="utf-8")
        thr = (BE / "core/risk_thresholds.py").read_text(encoding="utf-8")
        assert '"medium"' in risk, "risk.py 仍应返回 medium 标签（契约输出）"
        assert "mild" in thr and "moderate" in thr, "risk_thresholds 仍用 mild/moderate"

    def test_filename_sanitizers_exemption_still_exists(self):
        """#32 文件名清洗：3 实现语义不等价、不合并（审计豁免）。

        三个实现的语义差异（实测，勿凭印象）：
        - `admin.py::_sanitize_filename` / `user_risk.py::_sanitize_filename`：
          正则 `[^A-Za-z0-9_\\-.]` → 保留下划线/连字符/点号，**无长度限制**；
        - `reports.py::_safe_export_filename`：仅 ASCII 字母数字（`_-.` 也替换），
          **有长度截断**（`_MAX_SAFE_NAME_LEN`）+ 空值兜底 "export"。

        合并会改变至少一个调用方的文件名契约 → 业务决策，不合并；
        书面依据见 `docs/RETENTION_REGISTRY.md` 的 RES-P2-032-03。
        任一处被删/被合并，本测试红 → 强制同步登记册与审计文档。
        """
        admin = (BE / "api/v1/admin.py").read_text(encoding="utf-8")
        user_risk = (BE / "api/v1/user_risk.py").read_text(encoding="utf-8")
        reports = (BE / "api/v1/reports.py").read_text(encoding="utf-8")
        assert r're.sub(r"[^A-Za-z0-9_\-.]", "_", name)' in admin, (
            "admin.py 的 _sanitize_filename 正则应仍在（豁免对象）"
        )
        assert r're.sub(r"[^A-Za-z0-9_\-.]", "_", name)' in user_risk, (
            "user_risk.py 的 _sanitize_filename 正则应仍在（豁免对象）"
        )
        assert "_MAX_SAFE_NAME_LEN" in reports, (
            "reports.py 的长度限制应仍在（与另两处语义不同的证据）"
        )

    def test_exemptions_registered_in_retention_registry(self):
        """#32 三项裁定的书面保留必须登记进 RETENTION_REGISTRY.md。

        只写在审计文档里 = 口头依据（建册动因同型）；登记册是机器可追溯的落点。
        """
        reg = (DOCS / "RETENTION_REGISTRY.md").read_text(encoding="utf-8")
        for entry in ("RES-P2-032-01", "RES-P2-032-02", "RES-P2-032-03"):
            assert entry in reg, f"{entry} 未登记进保留登记册（#32 收尾要求书面保留）"

    def test_contradiction_ruling_appended(self):
        # 裁定必须以"追加"方式落到 P2_09 审计文档，不得删改原文
        t = (DOCS / "P2_09_ROUND9_AUDIT.md").read_text(encoding="utf-8")
        assert "追加更正" in t
        assert "MODEL_COMPATIBILITY_REGISTRY" in t or "model_registry_v2" in t, (
            "模型元数据矛盾裁定应追加进 P2_09 审计文档"
        )


class TestP234RaiseClassificationSynced:
    """#34 分类表与审计文档同步（棘轮 + 文档同步，#38 范式）。"""

    def _classify(self) -> dict[str, int]:
        buckets: dict[str, int] = {}
        for p in (BE).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except Exception:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                    continue
                fn = node.exc.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None) or "other"
                key = "HTTPException" if name == "HTTPException" else (
                    "ServiceError" if str(name).endswith("ServiceError") else "other_raise"
                )
                buckets[key] = buckets.get(key, 0) + 1
        return buckets

    def test_classification_counts_synced_with_doc(self):
        got = self._classify()
        doc = AUDIT.read_text(encoding="utf-8")
        for k, v in sorted(got.items()):
            token = f"{k}={v}"
            assert token in doc, (
                f"#34 分类计数 {token} 未与 {AUDIT.name} 同步；"
                f"改了源码就必须同步审计文档（棘轮）"
            )


class TestScannerSelfProof:
    """扫描器自证：判据必须能命中已知违规，否则是"报 0 型假闸门"。"""

    def test_operation_log_detector_hits_known_violation(self):
        src = "from app.models.admin import OperationLog\nlog = OperationLog(operator_id=1)\n"
        tree = ast.parse(src)
        hits = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) or getattr(n.func, "attr", None)) == "OperationLog"
        ]
        assert len(hits) == 1, "OperationLog 判据失效（应命中 1 处）"

    def test_orphan_detector_distinguishes_used_from_orphan(self):
        # 构造：A 组件被 import，B 组件无人引用 —— 判据应只把 B 判为孤儿
        used = "import C from '@/components/common/A.vue'\n"
        assert re.search(r"from ['\"].*A\.vue['\"]", used)
        assert not re.search(r"from ['\"].*ZzzOrphan\.vue['\"]", used)


class TestModuleLevelNamesDefined:
    """本轮真事故的回归闸：给已有文件加 `logger.warning` 却没定义 `logger`。

    教训（第十一轮 CI 红，backend-coverage 6 failed / 6730 passed）：
    `fusion.py` 原本没有 `logger`，我加 `logger.warning(...)` 时只跑了
    `py_compile`（只查语法、不查名字绑定）→ 模块 import 不报错，运行时才
    `NameError: name 'logger' is not defined`，把 6 个融合测试打红。

    判据：按作用域收集定义（模块级 + 每个函数/类/推导式内的局部名 +
    函数参数 + 异常处理器名 + global/nonlocal 声明 + import 绑定 + builtins），
    再检查每个 `Name(ctx=Load)` 是否在**其所在作用域链**上可解析。
    解析不到 ⇒ 模块 import 不报错但运行期 NameError，正是本事故的形态。
    """

    # 本轮改动过、且新增了 logger/record_audit 等调用的文件 —— 逐个核对
    TARGETS = [
        "core/model_engine/fusion.py",
        "core/ws.py",
        "core/event_bus.py",
        "core/pii_crypto.py",
        "core/degradation.py",
        "core/audit.py",
        "api/v1/silences.py",
        "api/v1/content_governance.py",
        "api/v1/model_kill_switch.py",
        "api/v1/metrics_helpers.py",
        "services/observability_service.py",
    ]

    @staticmethod
    def _scope_names(node: ast.AST) -> set[str]:
        """收集 node 直接作用域内的定义名（不进入嵌套函数/类）。"""
        names: set[str] = set()

        def add_target(t_: ast.AST) -> None:
            for n in ast.walk(t_):
                if isinstance(n, ast.Name):
                    names.add(n.id)

        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda, ast.ClassDef)):
            raw = getattr(node, "body", [])
            if isinstance(raw, list):
                body = list(raw)
            elif raw is None:
                body = []
            else:
                body = []  # Lambda.body 是单个表达式，无语句级定义
            if isinstance(node, ast.Lambda):
                body = []  # lambda 体是单表达式，参数已单列
            for stmt in body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(stmt.name)
                elif isinstance(stmt, ast.Assign):
                    for t_ in stmt.targets:
                        add_target(t_)
                elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                    add_target(stmt.target)
                elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                    add_target(stmt.target)
                elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                    for item in stmt.items:
                        if item.optional_vars is not None:
                            add_target(item.optional_vars)
                elif isinstance(stmt, ast.Import):
                    for a in stmt.names:
                        names.add(a.asname or a.name.split(".")[0])
                elif isinstance(stmt, ast.ImportFrom):
                    for a in stmt.names:
                        if a.name != "*":
                            names.add(a.asname or a.name)
                elif isinstance(stmt, ast.ExceptHandler) and stmt.name:
                    names.add(stmt.name)
                elif isinstance(stmt, (ast.Global, ast.Nonlocal)):
                    names.update(stmt.names)
                elif isinstance(stmt, ast.ExceptHandler):
                    pass  # except ... : 无名绑定不贡献名字
                # 控制流块继续向下（if/try/for/while 与所在作用域同名）
                for sub in ast.walk(stmt):
                    if sub is stmt:
                        continue
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                        ast.Lambda)):
                        continue  # 嵌套作用域单独处理
                    if isinstance(sub, (ast.Global, ast.Nonlocal)):
                        names.update(sub.names)
                    elif isinstance(sub, ast.ExceptHandler):
                        if sub.name:
                            names.add(sub.name)
                    elif isinstance(sub, (ast.For, ast.AsyncFor)):
                        add_target(sub.target)
                    elif isinstance(sub, (ast.With, ast.AsyncWith)):
                        for item in sub.items:
                            if item.optional_vars is not None:
                                add_target(item.optional_vars)
                    elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
                        add_target(sub.target)
                    elif isinstance(sub, ast.Assign):
                        for t_ in sub.targets:
                            add_target(t_)
                    elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
                        add_target(sub.target)
                    elif isinstance(sub, (ast.For, ast.AsyncFor)):
                        add_target(sub.target)
                    elif isinstance(sub, (ast.With, ast.AsyncWith)):
                        for item in sub.items:
                            if item.optional_vars is not None:
                                add_target(item.optional_vars)
                    elif isinstance(sub, ast.ExceptHandler) and sub.name:
                        names.add(sub.name)

        # 函数/类/lambda 参数
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = node.args
            for arg in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
                        + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else [])):
                names.add(arg.arg)
        # 推导式/生成器表达式的循环变量与条件作用域（Python 3 中它们有独立作用域，
        # 但其绑定对同一推导式内部可见 —— 近似：把本节点子树里所有推导式的 target 收进来）
        for sub in ast.walk(node):
            if isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in sub.generators:
                    for n in ast.walk(gen.target):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
        # 函数体内的 import（本仓大量使用函数内延迟 import）：
        # 只在**本作用域内**的 import 才算本作用域可见，故按行号范围过滤。
        if not isinstance(node, ast.Module):
            lo = getattr(node, "lineno", 0)
            hi = getattr(node, "end_lineno", 0)
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    if lo <= getattr(sub, "lineno", 0) <= hi:
                        if isinstance(sub, ast.Import):
                            for a in sub.names:
                                names.add(a.asname or a.name.split(".")[0])
                        else:
                            for a in sub.names:
                                if a.name != "*":
                                    names.add(a.asname or a.name)
        return names

    def test_used_names_are_defined_or_imported(self):
        import builtins as _b

        bad: list[str] = []
        for rel in self.TARGETS:
            src = (BE / rel).read_text(encoding="utf-8")
            tree = ast.parse(src, filename=rel)

            # 建作用域链：每个函数/类/模块节点 -> 定义名集合
            scopes: list[tuple[ast.AST, set[str]]] = [(tree, self._scope_names(tree))]
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    scopes.append((node, self._scope_names(node)))
            # 按包含关系建父子链（用 col_offset/lineno 近似嵌套深度）
            def parents(node: ast.AST) -> list[set[str]]:
                chain: list[set[str]] = []
                for scope_node, names in scopes:
                    if scope_node is node:
                        continue
                    if isinstance(scope_node, ast.Module):
                        chain.append(names)
                        continue
                    if isinstance(node, ast.AST) and isinstance(scope_node, ast.AST):
                        # node 的行号 >= scope 起始行 且 < scope 结束行 视为嵌套
                        if (getattr(node, "lineno", 0) >= getattr(scope_node, "lineno", 0)
                                and getattr(node, "end_lineno", 0) <= getattr(scope_node, "end_lineno", 0)):
                            chain.append(names)
                return chain

            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if node.id in self._scope_names(tree):
                        continue
                    chain = parents(node)
                    if any(node.id in names for names in chain):
                        continue
                    if node.id in dir(_b) or node.id in {"__file__", "__name__", "__path__"}:
                        continue
                    bad.append(f"{rel}:{node.lineno} {node.id}")
        assert not bad, "引用了未定义/未导入的名字（运行期 NameError 形态）:\n" + "\n".join(
            sorted(set(bad))[:20]
        )


class TestP235Round13Batch12Wiring:
    """第十三轮第十二批：#35 X 桶 3 处接线（`core/model_engine/predict.py`）。

    三处都是「分数/对照数据看似有效实则失真，且响应形态与正常态同形」：
    - `...experimental_v123_unavailable`：v1.23 对照路整路失败 →
      `experimental_external_*` 保持 None、`available=False`，与「该模型未部署」
      在响应形态上同形，排查时看不出是没部署还是加载/推理抛异常；
    - `...lite_calibrator_unavailable`：校准产物缺失/被禁用 → 保底返回未校准概率，
      响应里的 `probability_calibrated=False` 与「校准未启用」同形；
    - `...lite_calibration_apply_failed`：产物在但执行失败 → 同样是未校准概率，
      成因与上一条不同，分开计数才能定位是产物问题还是模型接口问题。

    同文件另 2 处**不接线、留档**（判据见 `test_declined_handlers_have_no_wiring`）：
    - `_run_adapter`：同一函数内已有 `adapter_miss` 专用计数器（与 `adapter_hit`
      成对），按 M 桶口径不重复接通用计数器；
    - `_run_experimental_v121` 外层：实测 `get_model_info(
      "structured_v1.21_binary_lr")` 返回 None（注册表已移除 v1.21 四条目），
      该 try 块运行时不可达 —— 接线即死代码，与第五批
      `TestP235WiringIsNotDeadCode` 同族。
    """

    PAIRS = (
        ("core.model_engine.predict.experimental_v123_unavailable", "core/model_engine/predict.py"),
        ("core.model_engine.predict.lite_calibrator_unavailable", "core/model_engine/predict.py"),
        ("core.model_engine.predict.lite_calibration_apply_failed", "core/model_engine/predict.py"),
    )

    # 行为锚点（pin 日志语义而非行号，行号随注释增删漂移）
    DECLINED_MARKERS = (
        "v1.24 adapter unavailable",
        "v1.22 experimental real binary LR unavailable",
    )

    _RAW = {
        "age": 20, "gender": 1, "cgpa": 3.0, "stress_level": 3,
        "sleep_duration": 7, "social_support": 3, "financial_pressure": 3,
        "family_history": 0, "academic_pressure": 3, "exercise_frequency": 2,
        "anxiety": 3, "panic_attack": 0,
    }

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_three_paths_increment(self, monkeypatch):
        """行为：三条失败路径各触发一次 → 对应计数器各 +1。"""
        from app.core.config import settings
        from app.core.model_engine import ModelEngine
        from app.core.model_engine.loading import LoadingMixin

        engine = ModelEngine()
        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}
        monkeypatch.setattr(settings, "lite_calibration_enabled", True)

        async def _boom(self, model_id, *args, **kwargs):  # noqa: ANN001
            raise FileNotFoundError(f"probe: {model_id} unavailable")

        monkeypatch.setattr(LoadingMixin, "_load_model_async", _boom)

        # ① v1.23 对照路整路失败（加载即炸）
        r123 = await engine._run_experimental_v123(dict(self._RAW), 50.0)
        assert r123["experimental_external_available"] is False
        assert r123["experimental_external_score"] is None

        # ② 校准产物加载失败 → 保底返回未校准概率
        prob1, applied1 = await engine._apply_lite_calibration(0.5)
        assert prob1 == 0.5 and applied1 is False

        # ③ 产物在但执行失败：假校准器既非 IsotonicRegression 也没有 predict_proba
        async def _bogus(self, model_id, *args, **kwargs):  # noqa: ANN001
            return object()

        monkeypatch.setattr(LoadingMixin, "_load_model_async", _bogus)
        prob2, applied2 = await engine._apply_lite_calibration(0.5)
        assert prob2 == 0.5 and applied2 is False

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"

    def test_declined_handlers_have_no_wiring(self):
        """反向钉：已裁定不接线的两个 handler 不得出现通用计数器接线。

        `adapter_miss` 专用计数器已覆盖 v1.24 适配器不可用；v1.21 外层 try 运行时
        不可达。将来若有人"顺手补个计数"，必须先推翻本裁定（并证明可达性/非重复）。
        """
        tree = ast.parse((BE / "core/model_engine/predict.py").read_text(encoding="utf-8"))
        hits = 0
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name not in {"_run_adapter", "_run_experimental_v121"}:
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = [ast.unparse(stmt) for stmt in node.body]
                if not any(m in stmt for stmt in body_src for m in self.DECLINED_MARKERS):
                    continue
                hits += 1
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                        assert nm != "record_silent_degradation", (
                            f"{fn.name} 的 handler（锚点 {self.DECLINED_MARKERS}）已裁定不接线，"
                            f"却发现 record_silent_degradation —— 必须先推翻裁定"
                        )
        assert hits == 2, f"行为锚点命中 {hits} 处，期望 2（锚点漂移 = 闸门失效）"


class TestP235Round13Batch13Wiring:
    """第十三轮第十三批：#35 X 桶 5 处接线（escalation / idempotency / validation）。

    五处都是「安全网失效或部分数据，且调用方从返回值上看不出来」：
    - `monitoring.escalation.notify_failed`：升级通知发送失败**不影响本轮提交**
      —— `escalation_level` 照常推进并 commit，告警被标成「已升级」，但没有
      任何人收到通知。既有的 failure 信号只挂在耗时直方图的 result 标签上
      （顺带记录、非专用失败计数），故另记一笔；
    - `core.idempotency.begin_failed_fail_open`：Redis 故障 → 放弃幂等控制返回
      `(True, None)`，调用方当成首次请求执行，重复 upsert 会真的写两次；
    - `core.idempotency.settle_failed`：首次响应没写进 Redis → 窗口内重复请求
      读到 `__PENDING__` 占位值被判「处理中」，重放能力静默丢失；
    - `core.idempotency.dismiss_failed`：失败请求没释放幂等键 → 键残留至 TTL，
      期间客户端修正后的重试被判「处理中」而拒绝；
    - `services.validation_engine.calculate_metrics_failed`：指标计算中段抛异常时
      metrics 已写入 accuracy/precision 等字段，返回「残缺但看起来合法」的对象。

    另 2 处**不接线、留档**（判据见 `test_declined_validation_engine_no_wiring`）：
    `_run_model_inference` / `_compute_baseline_metrics` 的失败都会由调用方写入
    `ValidationResult.errors`，属调用方可见的 V 型（与第十一批 EXIF 剥离同口径）。
    """

    PAIRS = (
        ("monitoring.escalation.notify_failed", "monitoring/escalation.py"),
        ("core.idempotency.begin_failed_fail_open", "core/idempotency.py"),
        ("core.idempotency.settle_failed", "core/idempotency.py"),
        ("core.idempotency.dismiss_failed", "core/idempotency.py"),
        ("services.validation_engine.calculate_metrics_failed", "services/validation_engine.py"),
    )

    # V 型两条的行为锚点（pin 日志语义而非行号）
    DECLINED_MARKERS = (
        "ValidationEngine: 模型推理失败",
        "ValidationEngine: 加载 baseline dataset 失败",
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_five_paths_increment(self, monkeypatch):
        """行为：五条失败路径各触发一次 → 对应计数器各 +1。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        import importlib

        import app.core.idempotency as idem
        import app.monitoring.escalation as esc

        # patch 命名空间第二态（第九批教训）：`app/services/__init__.py` 导出了一个
        # 同名 **ValidationEngine 实例**，会把子模块属性遮蔽掉 ——
        # `import app.services.validation_engine as ve` 拿到的是实例而非模块
        # （实测 AttributeError: 'ValidationEngine' object has no attribute
        # 'roc_auc_score'），必须走 importlib.import_module。
        ve = importlib.import_module("app.services.validation_engine")

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 升级通知失败 —— MagicMock 建模 AsyncSession（record_audit 需 db.flush）
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock(detail="{}")))
        )
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        decision = esc.EscalationDecision(
            alert_id=1,
            should_escalate=True,
            new_severity="P0",
            reason="probe",
            detail={"severity": "P1", "rule": "probe", "escalation_level": 1},
        )
        with patch("app.monitoring.escalation.CompositeNotifier") as mock_notifier:
            mock_notifier.return_value.send = AsyncMock(
                side_effect=RuntimeError("probe: notify boom")
            )
            executed = await esc.apply_escalation(db, [decision])
        # 升级仍被提交（这正是缺陷形态：状态推进了，人没被通知）
        assert [d.alert_id for d in executed] == [1]

        # ② ③ ④ 幂等三兄弟：Redis 整体不可用
        class _BoomRedis:
            async def get(self, key):  # noqa: ANN001
                raise RuntimeError("probe: redis down")

            async def set(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise RuntimeError("probe: redis down")

            async def delete(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise RuntimeError("probe: redis down")

        async def _client():
            return _BoomRedis()

        monkeypatch.setattr(idem, "get_redis_client", _client)
        assert await idem.begin_idempotent_call("probe-key") == (True, None)
        await idem.settle_idempotent_call("probe-key", {"probe": True})
        await idem.dismiss_idempotent_call("probe-key")

        # ⑤ 指标计算中段失败：让 roc_auc_score 抛非 ValueError（内层 try 只吃
        # ValueError），异常穿透到外层 —— 此时 accuracy/precision 已写入。
        def _auc_boom(*args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("probe: auc boom")

        monkeypatch.setattr(ve, "roc_auc_score", _auc_boom)
        metrics = ve.ValidationEngine().calculate_metrics(
            [0, 1, 0, 1, 1, 0], [0, 1, 0, 0, 1, 0], [0.1, 0.9, 0.2, 0.6, 0.8, 0.3]
        )
        assert metrics.accuracy is not None, "前半段（accuracy）应已算出"
        assert metrics.f1 is not None, "前半段（f1）应已算出"
        assert metrics.auc is None, "后半段（auc）缺失 —— 正是「部分数据」形态"

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"

    def test_declined_validation_engine_no_wiring(self):
        """反向钉：两条调用方可见（V 型）的失败路径不得接通用计数器。

        它们的失败会被调用方写进 `ValidationResult.errors` 返回给上层，
        与第十一批「EXIF 剥离失败返回 False、调用方直接拒绝」同口径。
        """
        tree = ast.parse((BE / "services/validation_engine.py").read_text(encoding="utf-8"))
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = [ast.unparse(stmt) for stmt in node.body]
            if not any(m in stmt for stmt in body_src for m in self.DECLINED_MARKERS):
                continue
            hits += 1
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                    assert nm != "record_silent_degradation", (
                        "该 handler 的失败已写进 ValidationResult.errors（V 型），"
                        "接线会给出调用方已处理的幻觉 —— 必须先推翻裁定"
                    )
        assert hits == 2, f"行为锚点命中 {hits} 处，期望 2（锚点漂移 = 闸门失效）"


class TestP235Round13Batch15Wiring:
    """第十三轮第十五批：#35 X 桶 3 处接线（main 侧车审计 / fusion 灰度路由 / 指纹）。

    三处都是「**失效的东西是别人判断的依据**」：

    - `main.sidecar_audit_skipped`：启动时模型侧车完整性审计失败 → 整段跳过，
      「缺失 / 陈旧」的可见性随之消失。启动日志里不再有任何一行说明这次审计没跑
      过，与「审计通过、全部一致」完全同形 —— 而侧车是 strict 环境下拒绝加载的
      依据，其完整性从此无人再问。
    - `services.model_predict.fusion.canary_routing_failed`：灰度路由决策失败 →
      `canary_routed` 保持 False，本该进灰度的用户静默走 stable，且响应里不会带
      `canary_routed` 标记 —— 灰度样本分配因此失真（灰度组被稳定版污染）。
    - `services.model_predict.inference.model_fingerprint_failed`：模型指纹是缓存键
      的版本前缀；计算失败退化为 `"unknown"` 后，「换模型 → 键前缀变化 → 旧缓存
      自然失效」整套机制失效，用户会命中上一个模型版本的缓存结果。

    本批**不接线** 12 处的裁定见 P2_13「一之十五」，其中三类值得单列：
    celery 信号 3 条（worker 是独立容器，计数落不到 `/metrics`）、
    `unified_model_interface` 3 条（生产链路不可达 = 死代码）、
    `excel_export_service` 3 条（`success=False` 显式失败，V 型）。
    """

    PAIRS = (
        ("main.sidecar_audit_skipped", "main.py"),
        ("services.model_predict.fusion.canary_routing_failed", "services/model_predict/fusion.py"),
        ("services.model_predict.inference.model_fingerprint_failed", "services/model_predict/inference.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_two_paths_increment(self, monkeypatch):
        """行为：两条可驱动的路径各触发一次 → 对应计数器各 +1。

        `main.sidecar_audit_skipped` 未做运行时断言 —— 它在 FastAPI `lifespan` 内联，
        触发需跑完整启动链路（init_db / Redis / 模型预加载），与第六批
        `api.alerts.webhook.final_commit_failed` 同口径，只由存在性断言守住。
        """
        import importlib

        inf = importlib.import_module("app.services.model_predict.inference")
        fus = importlib.import_module("app.services.model_predict.fusion")
        cm = importlib.import_module("app.services.canary_manager")
        dbmod = importlib.import_module("app.core.database")

        locs = ("services.model_predict.fusion.canary_routing_failed",
                "services.model_predict.inference.model_fingerprint_failed")
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 指纹失败：只换 inference 命名空间里的 hashlib（不动全局 hashlib）
        class _BoomHashlib:
            @staticmethod
            def sha256(*_args, **_kwargs):  # noqa: ANN205
                raise RuntimeError("probe: fingerprint boom")

        monkeypatch.setattr(inf, "_fingerprint_cache", None)  # 绕过 10s 记忆化
        monkeypatch.setattr(inf, "hashlib", _BoomHashlib)
        assert inf._model_fingerprint() == "unknown", "指纹失败应退化为 unknown"

        # ② 灰度路由失败：必须先让 AsyncSessionLocal 可用，否则异常会来自建会话
        #    而不是 decide_version —— 那样计数照样 +1，是**假绿**。
        seen: list[dict] = []

        async def _boom(**kwargs):  # noqa: ANN003
            seen.append(kwargs)
            raise RuntimeError("probe: canary routing boom")

        monkeypatch.setattr(cm.canary_manager, "decide_version", _boom)

        class _FakeSession:
            async def __aenter__(self):  # noqa: ANN204
                return self

            async def __aexit__(self, *_exc):  # noqa: ANN002, ANN204
                return False

        monkeypatch.setattr(dbmod, "AsyncSessionLocal", lambda: _FakeSession())
        with contextlib.suppress(Exception):  # 后续推理链与本次断言无关
            await fus.FusionMixin().predict_fusion(user_id=1)
        assert seen, (
            "decide_version 未被调用 —— 计数可能来自建会话/其它失败路径（假绿）"
        )

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"

    # 反向钉：excel_export_service 三处失败一律返回 success=False（V 型，调用方可见），
    # 接线会给出「调用方已处理」的幻觉 —— 必须先推翻 P2_13「一之十五」的裁定。
    # 锚点写「不带引号」的语义串：ast.unparse 会把字符串常量渲染成单引号，
    # 写死双引号会静默命中 0 处（锚点失效 = 反向钉变摆设，本批实锤过一次）。
    DECLINED_MARKERS = (
        "Excel export failed",
        "Excel stream export failed",
        "Large Excel export failed",
    )

    def test_declined_excel_export_no_wiring(self):
        tree = ast.parse((BE / "services/excel_export_service.py").read_text(encoding="utf-8"))
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = [ast.unparse(stmt) for stmt in node.body]
            if not any(m in stmt for stmt in body_src for m in self.DECLINED_MARKERS):
                continue
            if not any("success=False" in stmt for stmt in body_src):
                continue
            hits += 1
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                    assert nm != "record_silent_degradation", (
                        "该 handler 的失败已由 success=False 显式返回（V 型），"
                        "接线会造成「调用方已处理」的幻觉 —— 必须先推翻裁定"
                    )
        assert hits == 3, f"行为锚点命中 {hits} 处，期望 3（锚点漂移 = 闸门失效）"


class TestP235Round13Batch14Wiring:
    """第十三轮第十四批：#35 X 桶 4 处接线（safe_pickle 安全加固 / 注册表加载）。

    四处都是「**保护层的保护罩**掉了，而加载/读取本身照样成功」：

    - `core.safe_pickle.joblib_env_guard_unavailable`：ISS-006 的「生产环境强制
      哈希校验」靠读 `settings.app_env` 判定；settings 读不到 → 加固整段跳过，
      `require_hash` 停在调用方传入的 False，函数照常返回模型对象。
    - `core.safe_pickle.torch_env_guard_unavailable`：ISS-046 同理，
      `weights_only` 停在 False → `torch.load` 走回可执行任意代码的路径并成功返回。
    - `core.model_registry_v2.registry_file_unparsable`：注册表整体损坏 → 旁路备份
      后以空表启动，与「全新注册表」完全同形，训练资产的丢失不在任何返回值里。
    - `core.model_registry_v2.registry_records_dropped`：部分记录结构坏 → 已加载的
      留下、其余丢弃，registry 非空且可用，只是少了几条。

    另 1 处**不接线、留档**（判据见 `test_declined_restricted_unpickler_no_wiring`）：
    `_restricted_unpickler_class` 导入 joblib.NumpyUnpickler 失败返回 None，但它的
    唯一调用点在下一句就把 None 翻译成 raise（fail-closed），属 V 型。
    """

    PAIRS = (
        ("core.safe_pickle.joblib_env_guard_unavailable", "core/safe_pickle.py"),
        ("core.safe_pickle.torch_env_guard_unavailable", "core/safe_pickle.py"),
        ("core.model_registry_v2.registry_file_unparsable", "core/model_registry_v2.py"),
        ("core.model_registry_v2.registry_records_dropped", "core/model_registry_v2.py"),
    )

    # 不接线那一条的行为锚点（pin 日志语义而非行号）
    DECLINED_MARKERS = ("无法导入 joblib.NumpyUnpickler，反序列化白名单不可用",)

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_four_paths_increment(self, monkeypatch, tmp_path):
        """行为：四条失败路径各触发一次 → 对应计数器各 +1。"""
        import importlib
        import json

        import app.core.config as cfg

        sp = importlib.import_module("app.core.safe_pickle")
        mrv2 = importlib.import_module("app.core.model_registry_v2")

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ①② 让 settings 不可用：two helpers 各自 `from app.core.config import
        # settings` 后立刻读 `settings.app_env`，让该属性访问抛异常即可命中降级分支
        # （不必伪造整个 import machinery）。
        class _BoomSettings:
            @property
            def app_env(self) -> str:
                raise RuntimeError("probe: settings unusable")

        monkeypatch.setattr(cfg, "settings", _BoomSettings())
        for call in (
            lambda: sp.safe_joblib_load(tmp_path / "absent.pkl", require_hash=False),
            lambda: sp.safe_torch_load(tmp_path / "absent.pt", weights_only=False),
        ):
            with contextlib.suppress(Exception):  # 后续必然因文件不存在而失败
                call()

        # ③ 注册表整体损坏
        bad_path = tmp_path / "broken_registry.json"
        bad_path.write_text("{not valid json", encoding="utf-8")
        empty_registry = mrv2.ModelRegistryV2(registry_path=str(bad_path))
        assert empty_registry.registry == {}, "损坏文件应旁路后以空表启动"

        # ④ 合法 JSON 但第二条记录缺字段 → KeyError → 部分加载
        good = {
            "model_id": "probe_ok",
            "name": "probe",
            "version": "v1.0.0",
            "model_type": "xgboost",
            "status": "candidate",
            "artifact_path": "models/artifacts/probe.pkl",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        partial_path = tmp_path / "partial_registry.json"
        partial_path.write_text(
            json.dumps({"models": {"probe_ok": good, "probe_bad": {"model_id": "probe_bad"}}}),
            encoding="utf-8",
        )
        partial_registry = mrv2.ModelRegistryV2(registry_path=str(partial_path))
        assert list(partial_registry.registry) == ["probe_ok"], (
            "损坏记录应被丢弃、好记录保留 —— 正是「部分数据」形态"
        )

        for loc in locs:
            assert self._counter_value(loc) == before[loc] + 1, f"{loc} 未计数（假接线）"

    def test_declined_restricted_unpickler_no_wiring(self):
        """反向钉：白名单不可用那条 **fail-closed** 路径不得接通用计数器。

        它返回 None 后，唯一调用点 `_restricted_joblib_load` 下一句就把它翻译成
        raise RuntimeError（注释明示「绝不静默退回无白名单的 joblib.load」），
        调用方必见异常 —— 属 V 型，接线只会稀释真降级信号。
        """
        src = (BE / "core/safe_pickle.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = [ast.unparse(stmt) for stmt in node.body]
            if not any(m in stmt for stmt in body_src for m in self.DECLINED_MARKERS):
                continue
            hits += 1
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                    assert nm != "record_silent_degradation", (
                        "白名单不可用是 fail-closed（调用方必见 RuntimeError），接线"
                        "会把「已被硬失败拦下」误报成静默降级 —— 必须先推翻裁定"
                    )
        assert hits == 1, f"行为锚点命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"

        # 同时钉住 fail-closed 判据本身：这条是我的裁定前提，若被移除则上面的
        # 「不接线」结论失效（None 会变成无白名单放行），必须同步重审。
        assert "unpickler_cls is None or validate is None" in src, (
            "_restricted_joblib_load 的 fail-closed 判据消失 —— "
            "_restricted_unpickler_class 返回 None 将不再等于拒绝加载，"
            "本批「不接线」裁定须随之推翻"
        )


class TestP235Round13Batch16Wiring:
    """第十三轮第十六批：#35 X 桶 4 处接线（ws 本进程投递 / ws 订阅消息处理 /
    影子推理器加载 / 影子对拍异常）+ 9 处不接线裁定。

    四处接线的共同形状：**旁路失效，而主链路返回值毫发无损**：

    - `core.ws.local_send_failed`：`_local_send_to_user` 对某条连接的
      `send_text` 失败 → 该用户这一次推送静默丢失；`send_to_user` 继续走
      Redis 发布并正常返回，调用方（notify_warning 等）从返回值看不出
      有一次投递已经失败。
    - `core.ws.pubsub_message_handling_failed`：`_pubsub_loop` 里单条消息
      处理抛异常 → 该条消息被丢弃，订阅循环照常续跑；消息就此消失，而
      投递方（其它 worker 的 publish）早已返回成功。
    - `services.shadow_mode.predictor_unavailable`：M2 BERT 推理器加载失败
      → 对拍停用；生产 TF-IDF 链路毫无变化，影子期的一致率数据却从此断流，
      `get_stats` 的拉取式 flag 之外没有运行时信号。
    - `services.shadow_mode.compare_failed`：单次对拍异常被吞 → 该样本从
      一致率统计中静默消失，影子期切换决策的依据出现无痕缺口。

    本批**不接线** 9 处裁定见 P2_13「一之十七」，四类代表：
    ws disconnect 指标 dec 失败（M 型，指标采集自身）、
    rate_limit 签名修补回退（V 型，失败会以 500 暴露）、
    token_blocklist 撤销失败（V 型，三个调用方均检查返回值并记 ERROR，
    且检查侧 is_token_revoked fail-closed 已堵）、
    tenant_guard 扫描器跳过（运行期不可达，仅两个测试门禁调用）。
    """

    PAIRS = (
        ("core.ws.local_send_failed", "core/ws.py"),
        ("core.ws.pubsub_message_handling_failed", "core/ws.py"),
        ("services.shadow_mode.predictor_unavailable", "services/shadow_mode_service.py"),
        ("services.shadow_mode.compare_failed", "services/shadow_mode_service.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_runtime_paths_increment(self, monkeypatch):
        """行为：四条可驱动的路径各触发一次 → 对应计数器各 +1。

        每条都带防假绿断言（probe 必须真的被调用 / 中间状态必须符合预期），
        避免「计数来自别处」的假绿。
        """
        import asyncio
        import importlib

        wsmod = importlib.import_module("app.core.ws")
        sms = importlib.import_module("app.services.shadow_mode_service")
        cachemod = importlib.import_module("app.core.cache")

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 本进程投递失败：伪造一条 send_text 必炸的连接
        class _BoomWS:
            async def send_text(self, *_args, **_kwargs):  # noqa: ANN205
                raise RuntimeError("probe: local send boom")

        mgr = wsmod.ConnectionManager()
        mgr._connections = {7: [_BoomWS()]}
        await mgr._local_send_to_user(7, {"type": "probe"})
        assert self._counter_value(locs[0]) == before[locs[0]] + 1, (
            "本进程投递失败未计数（假接线）"
        )

        # ② 订阅消息处理失败：_handle_pubsub_message 必炸 + 假 Redis pubsub 客户端
        handled: list[dict] = []

        async def _boom_handler(msg: dict) -> None:  # noqa: ANN001
            handled.append(msg)
            raise RuntimeError("probe: pubsub handling boom")

        mgr2 = wsmod.ConnectionManager()
        monkeypatch.setattr(mgr2, "_handle_pubsub_message", _boom_handler)

        class _FakePubSub:
            async def psubscribe(self, *_args):  # noqa: ANN002, ANN204
                return None

            async def listen(self):  # noqa: ANN201
                yield {
                    "type": "pmessage",
                    "channel": "ws:user:7",
                    "data": '{"node_id": "other", "message": {"type": "probe"}}',
                }
                await asyncio.sleep(3600)

            async def aclose(self):  # noqa: ANN201
                return None

        class _FakeClient:
            def pubsub(self):  # noqa: ANN201
                return _FakePubSub()

        async def _fake_pubsub_client():  # noqa: ANN201
            return _FakeClient()

        # _pubsub_loop 函数体内 from-import → patch 定义方模块属性
        monkeypatch.setattr(cachemod, "get_redis_pubsub_client", _fake_pubsub_client)
        task = asyncio.create_task(mgr2._pubsub_loop())
        for _ in range(200):
            await asyncio.sleep(0.01)
            if self._counter_value(locs[1]) > before[locs[1]]:
                break
        assert handled, "_handle_pubsub_message 未被调用（假绿：计数可能来自别处）"
        assert self._counter_value(locs[1]) == before[locs[1]] + 1, (
            "订阅消息处理失败未计数（假接线）"
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # ③ 影子推理器加载失败（_ensure_predictor 的 except 位于 return False 之前）
        def _boom_predictor():  # noqa: ANN202
            raise RuntimeError("probe: predictor load boom")

        monkeypatch.setattr(sms, "get_m2_bert_predictor", _boom_predictor)
        svc = sms.ShadowModeService()
        assert svc._ensure_predictor() is False, "加载失败应返回 False"
        assert svc._predictor_loaded is False, "加载失败不应标记为已加载（防假绿）"
        assert self._counter_value(locs[2]) == before[locs[2]] + 1, (
            "推理器加载失败未计数（假接线）"
        )

        # ④ 单次对拍异常：predict 必炸，样本不得计入统计
        class _BoomPredictor:
            def __init__(self) -> None:
                self.calls = 0

            async def predict(self, _text: str) -> dict:  # noqa: ANN001, ANN201
                self.calls += 1
                raise RuntimeError("probe: shadow compare boom")

        boom_pred = _BoomPredictor()
        svc2 = sms.ShadowModeService()
        svc2._predictor = boom_pred
        svc2._predictor_loaded = True
        await svc2._shadow_predict("探针文本", {"prediction": 1, "probability": 0.5})
        assert boom_pred.calls == 1, "对拍推理未被调用（假绿）"
        assert svc2._total == 0, "对拍失败不应计入一致率统计（防假绿）"
        assert self._counter_value(locs[3]) == before[locs[3]] + 1, (
            "对拍异常未计数（假接线）"
        )

    # 反向钉：本批 9 处不接线裁定。锚点写「不带引号」的语义串 —— ast.unparse
    # 会把字符串常量渲染成单引号，写死双引号会静默命中 0 处（锚点失效 =
    # 反向钉变摆设，第十五批实锤过一次）。
    DECLINED_MARKERS = (
        ("core/ws.py", "websocket_connections_active.dec failed"),
        ("core/rate_limit.py", "限流装饰器签名修补失败"),
        ("core/rate_limit.py", "Rate limit exceeded at middleware layer"),
        ("api/v1/model_predict/status.py", "[model_status] cache_set failed"),
        ("core/token_blocklist.py", "token_blocklist: redis unavailable"),
        ("utils/checksum.py", "无法解析侧车校验文件"),
        ("utils/checksum.py", "RES-P3-005: failed to remove stale sidecar"),
        ("services/risk_service_warning.py", "Failed to publish warning.created event"),
    )

    def test_declined_handlers_not_wired(self):
        for rel, marker in self.DECLINED_MARKERS:
            tree = ast.parse((BE / rel).read_text(encoding="utf-8-sig"))
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = [ast.unparse(stmt) for stmt in node.body]
                if not any(marker in stmt for stmt in body_src):
                    continue
                hits += 1
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                        assert nm != "record_silent_degradation", (
                            f"{rel} 的「{marker}」handler 已接线 —— "
                            "必须先推翻 P2_13「一之十七」的裁定"
                        )
            assert hits >= 1, f"行为锚点「{marker}」在 {rel} 命中 0 处（锚点漂移 = 闸门失效）"

    def test_declined_token_blocklist_returns_false(self):
        """V 型判据钉住：撤销失败由返回值显式呈现，调用方看得见。"""
        tree = ast.parse((BE / "core/token_blocklist.py").read_text(encoding="utf-8-sig"))
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = [ast.unparse(stmt) for stmt in node.body]
            if not any("token_blocklist: redis unavailable" in s for s in body_src):
                continue
            hits += 1
            assert any("return False" in s for s in body_src), (
                "revoke_token 的 Redis 不可用分支不再返回 False —— "
                "「调用方可见」的裁定前提消失，须重审"
            )
        assert hits == 1, f"行为锚点命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"

    def test_declined_tenant_guard_scanner_unreachable(self):
        """运行时不可达钉住：扫描器在生产代码里没有调用方（仅测试门禁调用）。

        同时钉住 handler 形状（OSError/SyntaxError → continue，部分结果），
        出现任何变化都意味着「静默安全网失效」的裁定前提要重审。
        """
        tree = ast.parse((BE / "core/tenant_guard.py").read_text(encoding="utf-8-sig"))
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not any(isinstance(s, ast.Continue) for s in node.body):
                continue
            types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            names = {getattr(t, "id", None) for t in types}
            if not {"OSError", "SyntaxError"} <= names:
                continue
            hits += 1
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                    assert nm != "record_silent_degradation", (
                        "扫描器跳过分支已接线 —— 生产不可达裁定须先重审"
                    )
        assert hits == 1, f"行为锚点命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"

        callers = []
        for p in (BEPKG / "app").rglob("*.py"):
            if "__pycache__" in p.parts or p.name == "tenant_guard.py":
                continue
            if "scan_unscoped_protected_queries" in p.read_text(encoding="utf-8-sig"):
                callers.append(p.relative_to(BEPKG).as_posix())
        assert callers == [], (
            f"扫描器出现生产调用方，不可达裁定须重审: {callers}"
        )

    def test_declined_event_bus_underlay_wired(self):
        """risk_service_warning 不接线的前提：底层 event_bus.publish 已留痕。

        本层 except 只是防御性捕获（publish 的队列满分支内部已接线且不向上抛），
        若底层接线被拔掉，本层「重复层」裁定即失效。
        """
        src = (BE / "core/event_bus.py").read_text(encoding="utf-8-sig")
        assert '"core.event_bus.publish"' in src, (
            "底层 event_bus.publish 接线消失 —— risk_service_warning "
            "「防御层不接线」裁定须重审"
        )


class TestP235Round13Batch17Wiring:
    """第十三轮第十七批：#35 X 桶 3 处接线（健康监控刷新 / HTTP 指标记录 /
    自动回退检查）+ 12 处不接线裁定。

    三处接线的共同形状：**失效发生后，主链路对外形态与正常态完全同形**：

    - `core.health.monitor_refresh_failed`：`_health_monitor_loop` 快照刷新
      失败 → 缓存留旧值，`/health/ready` 仍以 200 + 陈旧快照应答，K8s 探针
      与调用方无从得知健康数据已停止更新（守护对象实际可能已故障）。
    - `core.middlewares.http_metrics_record_failed`：`metrics_middleware`
      finally 里 `http_requests_total.inc` 失败 → 请求本身照常返回，但 HTTP
      请求量/时延数据出现缺口，SLO 可用性统计静默偏乐观。
    - `services.registry_auto_rollback.check_failed`：`_rollback_loop` 里
      `check_auto_rollback` 失败 → 循环静默续跑，自动回退监控形同停摆，
      回退率超阈值的高风险训练产物继续滞留 PRODUCTION 服务推理，而任何
      调用方都看到系统「正常运行」。

    本批**不接线** 12 处裁定见 P2_13「一之十八」，代表类型：
    hyperparameter_tuning 缓存读写失败（结果正确、仅断点续跑失效的性能降级）、
    pdf_report 两处（success=False + error_message 的 V 型显式失败）、
    instance.get_instance_id（降级值 "unknown-<pid>" 形态可辨）、
    tasks/observability（返回 False → 上层 retry + FAILURE 事件）、
    model_loader/scaler（F 型 fallback，路径不存在时后续加载可见地报错）、
    model_validation（degenerate 计数随返回值暴露）、
    email_service（C 型清理路径低价值）、text_tokenizer（仅日志级别无失真）、
    review_service.create_review_task（底层 event_bus.publish 已接线的重复层）。
    """

    PAIRS = (
        ("core.health.monitor_refresh_failed", "core/health.py"),
        ("core.middlewares.http_metrics_record_failed", "core/middlewares.py"),
        ("services.registry_auto_rollback.check_failed", "services/registry_auto_rollback.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_runtime_paths_increment(self, monkeypatch):
        """行为：三条可驱动的路径各触发一次 → 对应计数器各 +1。

        每条都带防假绿断言（probe 必须真的被调用 / 假计数器必须真的被调用），
        避免「计数来自别处」的假绿。
        """
        import asyncio
        import importlib
        from types import SimpleNamespace

        from fastapi import Request
        from starlette.responses import Response

        health = importlib.import_module("app.core.health")
        mid = importlib.import_module("app.core.middlewares")
        rar = importlib.import_module("app.services.registry_auto_rollback")

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 健康监控刷新失败：get_health_snapshot 必炸 + 间隔压到 0
        probe_calls = {"n": 0}

        async def _boom_snapshot(*_a, **_k):  # noqa: ANN002, ANN202
            probe_calls["n"] += 1
            raise RuntimeError("probe: health snapshot boom")

        monkeypatch.setattr(health, "get_health_snapshot", _boom_snapshot)
        monkeypatch.setattr(health, "HEALTH_MONITOR_INTERVAL_SECONDS", 0)
        task = asyncio.create_task(health._health_monitor_loop(None, "redis://probe"))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if self._counter_value(locs[0]) > before[locs[0]]:
                break
        assert probe_calls["n"] >= 1, "get_health_snapshot 未被调用（假绿）"
        assert self._counter_value(locs[0]) >= before[locs[0]] + 1, (
            "健康监控刷新失败未计数（假接线）"
        )
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # ② HTTP 指标记录失败：inc 必炸 + 假计数器必须被真的调用过
        inc_calls = {"n": 0}

        class _BoomCounter:
            def inc(self, *_a, **_k):  # noqa: ANN002, ANN003, ANN201
                inc_calls["n"] += 1
                raise RuntimeError("probe: metrics inc boom")

        monkeypatch.setattr(mid, "http_requests_total", _BoomCounter())
        req = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "path": "/probe-b17",
                "raw_path": b"/probe-b17",
                "query_string": b"",
                "headers": [],
            }
        )

        async def _call_next(_request):  # noqa: ANN001, ANN201
            return Response(status_code=200)

        resp = await mid.metrics_middleware(req, _call_next)
        assert resp.status_code == 200, "中间件未把正常响应交还调用方（形态失真）"
        assert inc_calls["n"] >= 1, "http_requests_total.inc 未被调用（假绿）"
        assert self._counter_value(locs[1]) == before[locs[1]] + 1, (
            "HTTP 指标记录失败未计数（假接线）"
        )

        # ③ 自动回退检查失败：check_auto_rollback 必炸 + settings 间隔压到 0
        check_calls = {"n": 0}

        def _boom_check():  # noqa: ANN202
            check_calls["n"] += 1
            raise RuntimeError("probe: auto-rollback check boom")

        monkeypatch.setattr(rar, "check_auto_rollback", _boom_check)
        monkeypatch.setattr(
            rar,
            "settings",
            SimpleNamespace(registry_auto_rollback_enabled=True, registry_auto_rollback_interval=0),
        )
        task2 = asyncio.create_task(rar._rollback_loop())
        for _ in range(200):
            await asyncio.sleep(0.01)
            if self._counter_value(locs[2]) > before[locs[2]]:
                break
        assert check_calls["n"] >= 1, "check_auto_rollback 未被调用（假绿）"
        assert self._counter_value(locs[2]) >= before[locs[2]] + 1, (
            "自动回退检查失败未计数（假接线）"
        )
        task2.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task2

    @staticmethod
    def _func_source(rel: str, funcname: str) -> str:
        tree = ast.parse((BE / rel).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                seg = ast.get_source_segment((BE / rel).read_text(encoding="utf-8-sig"), node)
                assert seg is not None, f"{rel}::{funcname} 取不到源码片段"
                return seg
        raise AssertionError(f"{rel} 找不到函数 {funcname}（锚点漂移 = 闸门失效）")

    def _assert_declined(self, rel: str, funcname: str, anchor: str, reason: str):
        """反向钉：该函数体不得接线，且必须仍含锚点行为（否则裁定前提漂移）。"""
        seg = self._func_source(rel, funcname)
        assert "record_silent_degradation" not in seg, (
            f"{rel}::{funcname} 已接线 —— 「{reason}」裁定须重审"
        )
        assert anchor in seg, f"{rel}::{funcname} 行为锚点消失（{anchor!r}），闸门失效"

    def test_declined_no_distortion_batch17(self):
        """12 处不接线裁定的反向钉（逐一锚定行为 + 断言未接线）。"""
        # 性能降级无失真：缓存读/写失败 → 结果正确，仅断点续跑失效
        self._assert_declined(
            "ml/hyperparameter_tuning.py", "_load_tuning_cache", "starting fresh",
            "缓存读失败无结果失真（性能降级）",
        )
        self._assert_declined(
            "ml/hyperparameter_tuning.py", "_append_tuning_cache", "Failed to persist tuning cache",
            "缓存写失败无结果失真（性能降级）",
        )
        # V 型显式失败：success=False + error_message
        self._assert_declined(
            "services/pdf_report_service.py", "generate_pdf", "success=False",
            "PDF 生成失败显式上报（V 型）",
        )
        self._assert_declined(
            "services/pdf_report_service.py", "generate_pdf_stream", "success=False",
            "PDF 流式生成失败显式上报（V 型）",
        )
        # 降级值形态可辨："unknown" 前缀 + 已有 warning
        self._assert_declined(
            "core/instance.py", "get_instance_id", '"unknown"',
            "实例标识降级值形态可辨",
        )
        # V 型：返回 False → 上层 retry + FAILURE 事件
        self._assert_declined(
            "tasks/observability.py", "_flush_lock_stats_impl", "return False",
            "flush 失败显式返回 False 交由上层重试",
        )
        # F 型保守 fallback：解析失败回退路径，路径不存在时后续加载可见报错
        self._assert_declined(
            "ml/model_loader.py", "_resolve_artifacts_dir", "fallback to default",
            "工件目录解析 fallback（失败后续可见）",
        )
        self._assert_declined(
            "ml/scaler.py", "__getattr__", "_LEGACY_ARTIFACTS_DIR",
            "scaler 工件路径 fallback（失败后续可见）",
        )
        # 可辨信号：degenerate 计数随返回值暴露
        self._assert_declined(
            "ml/model_validation.py", "_bootstrap_auc_ci_with_count", "degenerate_samples += 1",
            "bootstrap 退化样本计数随返回值暴露",
        )
        # C 型清理路径低价值：连接已置空不重用，quit 失败仅残留到超时
        self._assert_declined(
            "services/email_service.py", "_close_thread_smtp", "SMTP quit() 失败",
            "SMTP 连接清理失败低价值（C 型）",
        )
        # 无失真：旧版 jieba 无 setLogLevel，仅日志级别差异
        self._assert_declined(
            "core/text_tokenizer.py", "_get_jieba", "pass",
            "jieba setLogLevel 缺失仅影响日志级别",
        )
        # 重复层：底层 event_bus.publish 已接线（Batch16 反向钉覆盖底层）
        self._assert_declined(
            "services/review_service.py", "create_review_task", "review.submitted",
            "EventBus 发布失败底层已接线（防御性重复层）",
        )


class TestP235Round13Batch18Wiring:
    """第十三轮第十八批：#35 X 桶 3 处接线（金丝雀检查洗白 / 训练任务 Redis
    列表回退 / 训练任务 Redis 更新失败）+ 13 处不接线裁定。

    三处接线的共同形状：**失败把「未检查/不完整/只写一半」洗成了正常形态**：

    - `services.auto_rollback_service.check_failed`：`check_all_canaries`
      单 canary 的检查/回滚整体失败 → `check_result` 被置为
      `should_rollback=False + reason="check_error"`；两个调用方
      （scheduler beat 与 fallback monitor）都只按 `should_rollback`
      分支走 **debug 级**日志——「无需回滚」的假象下这次检查根本没跑成，
      超阈值金丝雀静默无人回滚（与已接线的 `rollback_savepoint_failed`
      同族：那个是「结果在说回滚了但其实没有」，这个是「结果在说不用回滚
      但其实没检查」）。
    - `services.model_predict.training_jobs.redis_list_fallback`：
      `list_training_jobs` 读 Redis 失败 → 回退进程内内存表，残缺子集经
      `status.py` 的 `ok({"jobs": ...})` 直接包进成功响应返给前端——
      Redis 里可能仍在运行的任务整体消失，调用方拿到的就是「完整列表」形态。
    - `services.model_predict.training_jobs.redis_update_failed`：
      `update_job` 内存表已改而 Redis 持久化失败 → 双写不一致；函数无
      返回值，调用方无从得知这次状态变更只落了一半，Redis 恢复后读到旧状态。

    本批**不接线** 13 处裁定见 P2_13「一之十九」，代表类型：
    auto_rollback_service 5 条（`_bump_lock_counter` 专用计数器全覆盖的 M 型，
    其中 `get_check_heartbeat_age` 返回 None 时调用方有专门接管分支）、
    notifier 2 条（_dispatch 的 success=False+error_msg 随 results 返回 +
    alert_channel_failed 审计；_write_channel_log 的 C 型审计写失败）、
    am_sync 2 条（pull_silences 返回 None 显式失败 + am_sync_failed 审计；
    _write_sync_log C 型）、silences.create_silence 的 AM sync 异常
    （第四批注释明示：am_sync 内部已写 am_sync_failed，不重复计数）、
    training_jobs.get_training_job（storage_degraded=True + message 变更
    的显式降级标记）、event_bus._consume_loop 2 条（handler_errors 专用
    计数器 + stop 日志汇总；loop 级为 queue.get() 异常的防御性不可达路径）。
    """

    PAIRS = (
        ("services.auto_rollback_service.check_failed", "services/auto_rollback_service.py"),
        ("services.model_predict.training_jobs.redis_list_fallback", "services/model_predict/training_jobs.py"),
        ("services.model_predict.training_jobs.redis_update_failed", "services/model_predict/training_jobs.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_runtime_paths_increment(self, monkeypatch):
        """行为：三条可驱动的路径各触发一次 → 对应计数器各 +1。

        每条都带防假绿断言（检查确被调用且结果被洗白 / 内存表长度与返回一致 /
        内存写确已生效），避免「计数来自别处」的假绿。
        """
        import importlib
        from types import SimpleNamespace

        ars = importlib.import_module("app.services.auto_rollback_service")
        tj = importlib.import_module("app.services.model_predict.training_jobs")

        locs = tuple(loc for loc, _ in self.PAIRS)
        before = {loc: self._counter_value(loc) for loc in locs}

        # ① 金丝雀检查失败被洗白：check_canary_health 必炸 + 假 db/锁/心跳
        check_calls = {"n": 0}

        async def _boom_health(*_a, **_k):  # noqa: ANN002, ANN202
            check_calls["n"] += 1
            raise RuntimeError("probe: canary health boom")

        async def _always_lock(*_a, **_k):  # noqa: ANN002, ANN202
            return True

        async def _noop_heartbeat(*_a, **_k):  # noqa: ANN002, ANN202
            return True

        monkeypatch.setattr(ars.AutoRollbackService, "check_canary_health", _boom_health)
        monkeypatch.setattr(ars, "try_acquire_check_lock", _always_lock)
        monkeypatch.setattr(ars, "publish_check_heartbeat", _noop_heartbeat)

        class _FakeSavepoint:
            async def __aenter__(self):  # noqa: ANN201
                return self

            async def __aexit__(self, *_a):  # noqa: ANN002, ANN201
                return False

        class _FakeResult:
            def __init__(self, items):  # noqa: ANN001
                self._items = items

            def scalars(self):  # noqa: ANN201
                return self

            def all(self):  # noqa: ANN201
                return self._items

        class _FakeDB:
            async def execute(self, *_a, **_k):  # noqa: ANN002, ANN202
                return _FakeResult([SimpleNamespace(id=7)])

            def begin_nested(self):  # noqa: ANN201
                return _FakeSavepoint()

        results = await ars.auto_rollback_service.check_all_canaries(
            _FakeDB(), source="probe-b18"
        )
        assert check_calls["n"] >= 1, "check_canary_health 未被调用（假绿）"
        assert len(results) == 1 and results[0].should_rollback is False, (
            "结果未被洗成 should_rollback=False（防假绿：走的不是洗白路径）"
        )
        assert results[0].reason == "check_error", "reason 不是 check_error（锚点漂移）"
        assert self._counter_value(locs[0]) >= before[locs[0]] + 1, (
            "金丝雀检查失败未计数（假接线）"
        )

        # ② 训练任务 Redis 列表回退：list_jobs_from_redis 必炸 + 内存表有货
        def _boom_redis_list():  # noqa: ANN202
            raise RuntimeError("probe: redis list boom")

        monkeypatch.setattr("app.tasks.model_training.list_jobs_from_redis", _boom_redis_list)
        with tj.TRAINING_JOBS_LOCK:
            tj.TRAINING_JOBS["probe-b18"] = {"job_id": "probe-b18", "status": "running"}
        try:
            jobs = tj.list_training_jobs()
        finally:
            with tj.TRAINING_JOBS_LOCK:
                tj.TRAINING_JOBS.pop("probe-b18", None)
        assert any(j.get("job_id") == "probe-b18" for j in jobs), (
            "内存表任务未出现在返回里（假绿：走的不是回退路径）"
        )
        assert self._counter_value(locs[1]) >= before[locs[1]] + 1, (
            "Redis 列表回退未计数（假接线）"
        )

        # ③ 训练任务 Redis 更新失败：update_job_in_redis 必炸 + 内存写已生效
        def _boom_redis_update(*_a, **_k):  # noqa: ANN002, ANN202
            raise RuntimeError("probe: redis update boom")

        monkeypatch.setattr("app.tasks.model_training.update_job_in_redis", _boom_redis_update)
        with tj.TRAINING_JOBS_LOCK:
            tj.TRAINING_JOBS["probe-b18b"] = {"job_id": "probe-b18b", "status": "queued"}
        try:
            tj.update_job("probe-b18b", status="done")
            with tj.TRAINING_JOBS_LOCK:
                mem_status = tj.TRAINING_JOBS["probe-b18b"]["status"]
        finally:
            with tj.TRAINING_JOBS_LOCK:
                tj.TRAINING_JOBS.pop("probe-b18b", None)
        assert mem_status == "done", "内存表未更新（假绿：走的不是双写不一致路径）"
        assert self._counter_value(locs[2]) >= before[locs[2]] + 1, (
            "Redis 更新失败未计数（假接线）"
        )

    @staticmethod
    def _func_source(rel: str, funcname: str) -> str:
        src = (BE / rel).read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                seg = ast.get_source_segment(src, node)
                assert seg is not None, f"{rel}::{funcname} 取不到源码片段"
                return seg
        raise AssertionError(f"{rel} 找不到函数 {funcname}（锚点漂移 = 闸门失效）")

    def _assert_declined(self, rel: str, funcname: str, anchor: str, reason: str):
        """反向钉：该函数体不得接线，且必须仍含锚点行为（否则裁定前提漂移）。"""
        seg = self._func_source(rel, funcname)
        assert "record_silent_degradation" not in seg, (
            f"{rel}::{funcname} 已接线 —— 「{reason}」裁定须重审"
        )
        assert anchor in seg, f"{rel}::{funcname} 行为锚点消失（{anchor!r}），闸门失效"

    def test_declined_no_distortion_batch18(self):
        """13 处不接线裁定的反向钉（逐一锚定行为 + 断言未接线）。"""
        # M 型：Redis 客户端获取失败 → 调用方全部处理 None + _bump_lock_counter
        self._assert_declined(
            "services/auto_rollback_service.py", "_redis_client_or_none",
            "获取 redis 客户端失败", "锁/心跳辅助的 M 型专用计数器",
        )
        # M 型：锁获取异常 → _bump_lock_counter + 注释明示的降级执行
        self._assert_declined(
            "services/auto_rollback_service.py", "try_acquire_check_lock",
            '_bump_lock_counter("unavailable")', "锁降级执行已有专用计数器（M 型）",
        )
        # M 型：心跳写失败 → _bump_lock_counter + return False
        self._assert_declined(
            "services/auto_rollback_service.py", "publish_check_heartbeat",
            "写入心跳失败", "心跳写失败已有专用计数器（M 型）",
        )
        # M 型：心跳读失败/解析失败 → _bump_lock_counter + return None
        self._assert_declined(
            "services/auto_rollback_service.py", "get_check_heartbeat_age",
            "读取心跳失败", "心跳读失败已有专用计数器（M 型）",
        )
        # V 型：单通道未捕获异常 → success=False + error_msg 随 results 返回
        self._assert_declined(
            "monitoring/notifier.py", "_dispatch",
            "未捕获异常", "通道发送失败显式上报（V 型）",
        )
        # C 型：通道审计写失败不影响通知结果
        self._assert_declined(
            "monitoring/notifier.py", "_write_channel_log",
            "写 OperationLog 失败", "通道审计写失败低价值（C 型）",
        )
        # C 型：AM 同步审计写失败不影响主流程
        self._assert_declined(
            "monitoring/am_sync.py", "_write_sync_log",
            "写 OperationLog 失败", "AM 同步审计写失败低价值（C 型）",
        )
        # V 型：pull 失败返回 None + am_sync_failed 审计
        self._assert_declined(
            "monitoring/am_sync.py", "pull_silences",
            "pull exception", "AM 拉取失败显式返回 None（V 型）",
        )
        # V 型：存储不可用时 not_found 带 storage_degraded + message 变更
        self._assert_declined(
            "services/model_predict/training_jobs.py", "get_training_job",
            "storage_degraded", "存储降级有显式标记（V 型）",
        )
        # M 型：handler 失败有 handler_errors 专用计数器
        self._assert_declined(
            "core/event_bus.py", "_consume_loop",
            "handler_errors += 1", "事件 handler 失败已有专用计数器（M 型）",
        )

    def test_declined_silences_am_sync_exception_not_wired(self):
        """silences.create_silence：AM sync 异常不接线（am_sync 内部已写审计），
        但同函数的补偿失败路径 am_rollback_failed 必须仍在（第四批已接线）。

        两个 except 在同函数内裁决相反，必须分别钉，防止「整个函数不接线」
        的粗粒度断言把已接线路径一起误钉为未接。
        """
        src = (BE / "api/v1/silences.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        seg = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "create_silence":
                seg = ast.get_source_segment(src, node)
                break
        assert seg is not None, "create_silence 取不到源码片段"
        wired = seg.count("record_silent_degradation")
        assert wired == 1, (
            f"create_silence 接线点数量 {wired}，期望 1（am_rollback_failed）；"
            "数量变化意味着第四批补偿路径裁定须重审"
        )
        assert "api.silences.create.am_rollback_failed" in seg, (
            "补偿失败接线消失 —— 孤儿静默（漏预警方向）将无计数"
        )
        assert "AM sync exception" in seg, "AM sync 异常行为锚点消失，闸门失效"
        # AM sync 那个 except 不得接线：用 AST 定位含该日志的 handler
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = ast.get_source_segment(src, node) or ""
            if "AM sync exception" not in body_src:
                continue
            assert "record_silent_degradation" not in body_src, (
                "AM sync 异常分支已接线 —— 「重复层不接线」裁定须重审"
            )
            break
        else:
            raise AssertionError("未找到含 AM sync exception 的 except（锚点漂移）")


class TestP235Round13Batch19Declined:
    """第十三轮第十九批：#35 X 桶**纯裁定批**（0 接线，W=95 / X=120 不变）。

    对 scheduler(7) + model_engine/loading(4) + config(2) 共 13 条 X 候选
    逐条代码实证后全部裁定**不接线**，判据分四类：

    - **S 型（自报失败通道自身失败）**：`scheduler` 的 Sentry
      `capture_message` / `capture_exception` 3 处（L401/L510/L1102）——
      主通道已在：`_daily_risk_scan_impl` / `_stale_warning_reminder_impl`
      的滞留汇总都先记了 **error 级**日志（AUDIT-P0-2 / P0-FIX-2026-10-11），
      `_cleanup_experiment_artifacts_impl` 的保护集解析失败更是先记 error
      再 `raise RuntimeError` 显式中止（celery 任务失败可见）。Sentry 只是
      叠加的第二上报通道，它自己失败记 debug 不构成静默降级。
    - **C 型（清理路径跳过/失败）**：`_cleanup_uploads_dir_impl` 2 处
      （L994 单文件 unlink 失败 skip / L1001 空目录 rmdir 失败 pass）与
      `_cleanup_experiment_artifacts_impl` 2 处（L1054 stat 失败跳过该目录 /
      L1170 rmtree 失败 warning）——清理任务的失败形状是「少删一些」，
      磁盘缓慢增长而非数据/安全失真，且 warning/debug 级日志已在；
      这些任务还跑在 celery worker（跨进程，无 PROMETHEUS_MULTIPROC_DIR，
      按第十五批口径计数不可达）。
    - **V 型（显式失败信号）**：`loading._get_expected_hash` 侧车不可解析
      返回 `(None, "unreadable_sidecar:...")`——AUDIT-2026-10-08 (P0-6)
      专门把「侧车不存在/不可解析/畸形」拆成可区分来源，调用方
      `_verify_file_hash` 按 source 分级处置，形态可辨。
    - **设计内/低价值/dev-only**：`loading._load_model` 的 BERT 无本地
      缓存回退 Hub 下载是注释明示的正常双路径（有缓存零网络、无缓存触网，
      两侧都成功加载，无失真）；`loading._patch_simple_imputer` 补丁失败
      只记 debug，但旧模型 pickle 缺 `_fill_dtype` 会在后续 transform 时
      **可见地**抛 AttributeError，不属静默；`config.apply_env_defaults`
      的 PII key 文件读/写失败 2 处——仅 dev 环境路径（生产缺失密钥由模块级
      检查拦截），且都伴随 `warnings.warn` 显式提示。

    裁定明细（13 条，file:line → 类型）：
    scheduler.py L401/L510/L1102 → S 型；scheduler.py L994/L1001/L1054/
    L1170 → C 型；loading.py L82 → V 型；loading.py L429/L596/L712 →
    M 型/设计内/低价值（详见各钉）；config.py L359/L372 → dev-only 显式警告。
    """

    DECLINED_FUNC_LEVEL = (
        # (文件, 函数, 行为锚点, 裁定理由)
        ("tasks/scheduler.py", "_daily_risk_scan_impl", "Sentry capture_message 调用失败",
         "滞留汇总已记 error 日志，Sentry 为叠加层（S 型）"),
        ("tasks/scheduler.py", "_stale_warning_reminder_impl", "Sentry capture_message 调用失败",
         "滞留已留 OperationLog + error 日志，Sentry 为叠加层（S 型）"),
        ("tasks/scheduler.py", "_cleanup_uploads_dir_impl", "skip file",
         "清理跳过/失败只损失磁盘回收（C 型，celery 跨进程）"),
        ("tasks/scheduler.py", "_cleanup_experiment_artifacts_impl", "中止本次产物清理以避免误删",
         "保护集解析失败已 raise 显式中止；清理跳过为 C 型"),
        ("core/model_engine/loading.py", "_get_expected_hash", "无法解析侧车校验文件",
         "侧车状态以 tuple 来源显式返回（V 型，P0-6 修复）"),
        ("core/model_engine/loading.py", "_patch_simple_imputer", "SimpleImputer _fill_dtype patch failed",
         "补丁失败后续 transform 可见 AttributeError，不静默"),
        ("core/config.py", "apply_env_defaults", "Failed to read PII key file",
         "dev-only 路径 + warnings.warn 显式提示"),
    )

    # except 块级精细钉：同函数内存在**其他**已接线路径，函数级断言会假红，
    # 必须 AST 定位目标 handler（与 Batch18 silences 同款教训）。
    DECLINED_HANDLER_LEVEL = (
        ("core/model_engine/loading.py", "_load_adapter", '_incr_model_fallback("v1.24_adapter", "load_failed")',
         "适配器加载失败有 _incr_model_fallback 专用计数器（M 型）",
         'core.model_engine.loading.adapter.pkl_fallback'),
        ("core/model_engine/loading.py", "_load_model", "无本地缓存，回退 Hub 下载",
         "BERT 无缓存回退 Hub 是设计内双路径，两侧都成功加载",
         'core.model_engine.loading.keras_compat_load_failed'),
    )

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    def test_declined_func_level_not_wired(self):
        """函数级反向钉：7 个函数体不得接线，且行为锚点必须在。"""
        for rel, funcname, anchor, reason in self.DECLINED_FUNC_LEVEL:
            src = self._read(rel)
            tree = ast.parse(src)
            seg = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                    seg = ast.get_source_segment(src, node)
                    break
            assert seg is not None, f"{rel} 找不到函数 {funcname}（锚点漂移 = 闸门失效）"
            assert "record_silent_degradation" not in seg, (
                f"{rel}::{funcname} 已接线 —— 「{reason}」裁定须重审"
            )
            assert anchor in seg, f"{rel}::{funcname} 行为锚点消失（{anchor!r}），闸门失效"

    def test_declined_handler_level_not_wired(self):
        """except 块级反向钉：目标 handler 不得接线；同函数的其他已接线路径
        （witness location）必须仍在——两侧同时钉，防粗粒度误判。"""
        for rel, funcname, anchor, reason, witness in self.DECLINED_HANDLER_LEVEL:
            src = self._read(rel)
            tree = ast.parse(src)
            func_seg = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                    func_seg = ast.get_source_segment(src, node)
                    break
            assert func_seg is not None, f"{rel} 找不到函数 {funcname}"
            assert witness in func_seg, (
                f"{rel}::{funcname} 的见证接线 {witness} 消失 —— "
                "精细钉的前提（同函数其他路径已接线）失效"
            )
            hit = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = ast.get_source_segment(src, node) or ""
                if anchor not in body_src:
                    continue
                hit = True
                assert "record_silent_degradation" not in body_src, (
                    f"{rel}::{funcname} 目标 except 已接线 —— 「{reason}」裁定须重审"
                )
            assert hit, f"{rel}::{funcname} 未找到含锚点 {anchor!r} 的 except（锚点漂移）"

    def test_doc_registered_batch19(self):
        """文档登记：P2_13「一之二十」节含 13 条裁定关键标识；P2_11 附录
        含第十九批条目与三个文件名（两文档各管一侧，防止读错文档假红）。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十、" in doc13, (
            "P2_13 缺少第十九批（一之二十）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "scheduler.py", "loading.py", "config.py",
            "_daily_risk_scan_impl", "_stale_warning_reminder_impl",
            "_cleanup_uploads_dir_impl", "_cleanup_experiment_artifacts_impl",
            "_get_expected_hash", "_load_adapter", "_load_model",
            "_patch_simple_imputer", "apply_env_defaults",
            "S 型", "C 型",
        ):
            assert token in doc13, f"P2_13 第十九批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第十九批" in doc11, "P2_11 附录缺少第十九批条目"
        for token in ("scheduler", "model_engine/loading", "config"):
            assert token in doc11, f"P2_11 附录第十九批条目缺少文件名: {token}"
        # 纯裁定批账实一致：桶计数钉不变（W=95 / X=120）
        counts_doc = "W=95 / X=120" in doc13 or "W 95" in doc13
        assert counts_doc, "第十九批为纯裁定批，累计状态应维持 W=95 / X=120"


class TestP235Round13Batch20Wiring:
    """第十三轮第二十批：#35 X 桶接线 1 处（api.alerts.history_detail_parse_failed）
    + 14 处不接线裁定（W 95→96 / X 120→119，总数 334 不变）。

    **接线点形状**：`list_alert_history` 逐条解析 OperationLog.detail 的
    JSON，解析失败 → warning + `detail = {}` → rule/severity/message 全为
    **空的 item 仍照常 append 进列表**（无 severity 过滤时；有过滤时该条被
    `continue` 跳过，total 仍计它）。前端告警历史页因此看到一条字段全空的
    告警记录——与正常记录同形（列表项存在、只是内容空），告警内容静默丢失，
    从响应形态无法分辨。

    **14 处不接线**（裁定明细见 P2_13「一之二十一」）：
    - alerts 4（V 型：failed/notify_failed 计数或 return False 显式上报）
    - pii_crypto 2（V 型：密钥全耗尽时 decrypt_field raise ValueError + error 日志）
    - escalation 2（M 型：alert_detail_parse_failed_total 专用计数器）
    - drift 2（V 型 DriftCheckResult(failed=True) / S 型 gauge 自报失败）
    - model_registry_v2 2（上游已接线的旁路最佳努力 / V 型内存回滚 return None）
    - fusion 1（M 型指标自身失败，_log_canary_event 仍写事件）
    - main 1（V 型：startup_status.record("model_preload", "failed") 显式状态）
    """

    PAIRS = (
        ("api.alerts.history_detail_parse_failed", "api/v1/alerts/__init__.py"),
    )

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = (BE / rel).read_text(encoding="utf-8-sig")
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    async def test_runtime_paths_increment(self):
        """行为：detail 损坏的行 → 空壳 item 照常入列表（同形失真实证）+
        计数器 +1。一行正常 + 一行损坏，证明两者在响应里不可分辨。"""
        import importlib
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from fastapi import Request

        alerts = importlib.import_module("app.api.v1.alerts")

        loc = self.PAIRS[0][0]
        before = self._counter_value(loc)

        row_ok = SimpleNamespace(
            id=1001,
            detail='{"rule": "high_error_rate", "severity": "P1", "message": "5xx > 5%"}',
            action_type="alert_fired",
            operator_id=7,
            operator_role="counselor",
            created_at=datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc),
        )
        row_bad = SimpleNamespace(
            id=1002,
            detail="{invalid json!!",
            action_type="alert_fired",
            operator_id=7,
            operator_role="counselor",
            created_at=datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc),
        )

        class _FakeResult:
            def __init__(self, items):  # noqa: ANN001
                self._items = items

            def scalars(self):  # noqa: ANN201
                return self

            def all(self):  # noqa: ANN201
                return self._items

            def scalar_one(self):  # noqa: ANN201
                return len(self._items)

        class _FakeDB:
            def __init__(self, rows):  # noqa: ANN001
                self._rows = rows

            async def execute(self, *_a, **_k):  # noqa: ANN002, ANN202
                return _FakeResult(self._rows)

        req = Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "path": "/api/v1/alerts/history",
                "raw_path": b"/api/v1/alerts/history",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        resp = await alerts.list_alert_history(
            request=req,
            db=_FakeDB([row_ok, row_bad]),
            _=None,
            page=1,
            page_size=50,
            severity=None,
            status=None,
            start_time=None,
            end_time=None,
        )
        data = resp["data"]
        assert data["total"] == 2, "total 未统计全部行（防假绿：走的不是列表路径）"
        assert len(data["items"]) == 2, "两条记录都应入列表（同形失真实证）"
        bad_item = next(i for i in data["items"] if i["id"] == 1002)
        ok_item = next(i for i in data["items"] if i["id"] == 1001)
        assert (
            bad_item["rule"] == ""
            and bad_item["severity"] == ""
            and bad_item["message"] == ""
        ), "损坏行的字段未洗空（防假绿：走的不是 detail={} 路径）"
        assert ok_item["rule"] == "high_error_rate", "正常行内容异常（对照组失效）"
        assert self._counter_value(loc) >= before + 1, "detail 解析失败未计数（假接线）"

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    def _assert_declined(self, rel: str, funcname: str, anchor: str, reason: str):
        """反向钉：该函数体不得接线，且必须仍含锚点行为（否则裁定前提漂移）。"""
        src = self._read(rel)
        tree = ast.parse(src)
        seg = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                seg = ast.get_source_segment(src, node)
                break
        assert seg is not None, f"{rel} 找不到函数 {funcname}（锚点漂移 = 闸门失效）"
        assert "record_silent_degradation" not in seg, (
            f"{rel}::{funcname} 已接线 —— 「{reason}」裁定须重审"
        )
        assert anchor in seg, f"{rel}::{funcname} 行为锚点消失（{anchor!r}），闸门失效"

    def _assert_declined_handler(
        self, rel: str, funcname: str, anchor: str, reason: str, witness: str | None = None
    ):
        """except 块级反向钉：AST 定位含锚点的 handler，断言其未接线；
        witness 为同函数内**其他**已接线路径，必须仍在（精细钉前提）。"""
        src = self._read(rel)
        tree = ast.parse(src)
        func_seg = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                func_seg = ast.get_source_segment(src, node)
                break
        assert func_seg is not None, f"{rel} 找不到函数 {funcname}"
        if witness is not None:
            assert witness in func_seg, (
                f"{rel}::{funcname} 的见证接线 {witness} 消失 —— 精细钉前提失效"
            )
        hit = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = ast.get_source_segment(src, node) or ""
            if anchor not in body_src:
                continue
            hit = True
            assert "record_silent_degradation" not in body_src, (
                f"{rel}::{funcname} 目标 except 已接线 —— 「{reason}」裁定须重审"
            )
        assert hit, f"{rel}::{funcname} 未找到含锚点 {anchor!r} 的 except（锚点漂移）"

    def test_declined_func_level_not_wired(self):
        """函数级反向钉：9 个函数体不得接线，且行为锚点必须在。"""
        # V 型：静默告警持久化失败 → error 日志 + return False（调用方累计 failed）
        self._assert_declined(
            "api/v1/alerts/__init__.py", "_handle_silenced_alert", "return False",
            "静默告警持久化失败显式返回 False（V 型）",
        )
        # V 型：旧密钥派生失败 → 跳过该密钥；decrypt_field 密钥全耗尽时
        # raise ValueError + error 日志（exhausted），失败显式
        self._assert_declined(
            "core/pii_crypto.py", "_get_previous_fernets", "Failed to derive previous Fernet key",
            "旧密钥派生失败的后果是 decrypt_field 显式 raise（V 型）",
        )
        self._assert_declined(
            "core/pii_crypto.py", "_get_previous_aes_gcms", "Failed to derive previous AES-GCM key",
            "旧密钥派生失败的后果是 decrypt_field 显式 raise（V 型）",
        )
        # M 型：detail 解析失败已有 alert_detail_parse_failed_total 专用计数器
        self._assert_declined(
            "monitoring/escalation.py", "compute_escalation", "alert_detail_parse_failed_total",
            "detail 解析失败已有专用计数器（M 型）",
        )
        # V 型：单模态检测失败 → DriftCheckResult(failed=True) 显式入结果列表
        self._assert_declined(
            "services/drift_monitoring_service.py", "check_all_modalities", "failed=True",
            "漂移检测失败以 failed=True 显式上报（V 型）",
        )
        # S 型：PSI/KL 推送 Gauge 失败只记 debug，且注释明示 failed 模态跳过推送
        self._assert_declined(
            "services/drift_monitoring_service.py", "_push_to_gauge", "推送 PSI/KL 到 Gauge 失败",
            "Gauge 上报失败为指标自身通道（S 型）",
        )
        # 上游已接线：_load_registry 对 registry_file_unparsable /
        # records_dropped 均已计数，旁路失败只是恢复现场的最佳努力
        self._assert_declined(
            "core/model_registry_v2.py", "_quarantine_corrupt_file", "无法旁路损坏的注册表文件",
            "旁路失败上游已计数，且为最佳努力兜底",
        )
        # V 型：磁盘写失败 → 内存状态回滚 + return None（调用方显式得知失败）
        self._assert_declined(
            "core/model_registry_v2.py", "_promote_model_locked", "Failed to persist model promotion",
            "晋升持久化失败内存回滚并返回 None（V 型）",
        )
        # V 型：后台预加载失败 → startup_status.record("model_preload", "failed")
        self._assert_declined(
            "main.py", "_preload_models_background", "Model preload failed in background",
            "预加载失败经 startup_status 显式记录（V 型）",
        )

    def test_declined_handler_level_not_wired(self):
        """except 块级反向钉：同函数多路径分别裁定 / 同函数有其他已接线
        路径时，必须 AST 定位目标 handler（函数级断言会假红或漏红）。"""
        # _handle_active_alert 三个 except 分别裁定（去重 fail-open / 持久化失败 /
        # 通知失败），全部 V 型显式；该函数内无任何已接线路径
        self._assert_declined_handler(
            "api/v1/alerts/__init__.py", "_handle_active_alert", "defaulting to send",
            "去重检查失败注释明示放行 + error 日志（V 型变体）",
        )
        self._assert_declined_handler(
            "api/v1/alerts/__init__.py", "_handle_active_alert", "return 0, 1, 0",
            "持久化失败计入 failed（V 型）",
        )
        self._assert_declined_handler(
            "api/v1/alerts/__init__.py", "_handle_active_alert", "return 1, 0, 1",
            "通知失败计入 notify_failed（V 型）",
        )
        # escalation 内层：专用计数器的上传失败（观察者的观察者），主信号已在
        self._assert_declined_handler(
            "monitoring/escalation.py", "compute_escalation", "告警 detail 解析失败计数上报失败",
            "专用计数器上传失败不影响升级决策（主信号已在）",
        )
        # predict_fusion 同函数内已有 canary_routing_failed 接线（见证），
        # 目标 except 是指标自增失败（M 型变体：指标自身，主链路无失真）
        self._assert_declined_handler(
            "services/model_predict/fusion.py", "predict_fusion",
            "canary 指标自增失败（不影响推理结果）",
            "canary 指标自增失败为指标自身通道（M 型变体）",
            witness="services.model_predict.fusion.canary_routing_failed",
        )

    def test_declined_premises_still_hold(self):
        """裁定前提的见证钉：V 型/M 型裁定的依据若消失，裁定须重审。"""
        # pii_crypto V 型前提：decrypt_field 密钥全耗尽时显式 raise
        seg = self._read("core/pii_crypto.py")
        assert 'raise ValueError("PII 解密失败（密钥错误或数据损坏）")' in seg, (
            "decrypt_field 的显式 raise 消失 —— pii_crypto「V 型不接线」前提失效"
        )
        # model_registry_v2 旁路裁定前提：上游两条接线仍在
        mrv = self._read("core/model_registry_v2.py")
        for witness in (
            "core.model_registry_v2.registry_file_unparsable",
            "core.model_registry_v2.registry_records_dropped",
        ):
            assert witness in mrv, f"上游接线 {witness} 消失 —— 旁路「上游已计数」裁定前提失效"

    def test_doc_registered_batch20(self):
        """文档登记：P2_13「一之二十一」节（结构钉）含 1 接 14 不接关键标识；
        P2_11 附录含第二十批条目；桶计数改钉 W=96 / X=119。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十一、" in doc13, (
            "P2_13 缺少第二十批（一之二十一）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "api.alerts.history_detail_parse_failed",
            "api/v1/alerts/__init__.py", "pii_crypto.py", "escalation.py",
            "drift_monitoring_service.py", "model_registry_v2.py",
            "fusion.py", "main.py",
            "_handle_silenced_alert", "_handle_active_alert",
            "_get_previous_fernets", "_get_previous_aes_gcms",
            "compute_escalation", "check_all_modalities", "_push_to_gauge",
            "_quarantine_corrupt_file", "_promote_model_locked",
            "predict_fusion", "_preload_models_background",
            "V 型", "M 型", "S 型",
        ):
            assert token in doc13, f"P2_13 第二十批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十批" in doc11, "P2_11 附录缺少第二十批条目"
        for token in ("api/v1/alerts", "pii_crypto", "escalation", "drift_monitoring", "model_registry_v2"):
            assert token in doc11, f"P2_11 附录第二十批条目缺少文件名: {token}"
        counts_doc = "W=96 / X=119" in doc13 or "W 96" in doc13
        assert counts_doc, "第二十批接线 1 处，累计状态应改钉 W=96 / X=119"


class TestP235Round13Batch21Declined:
    """第十三轮第二十一批：#35 X 桶**纯裁定批**（0 接线，W=96 / X=119 不变）。

    挑簇对象 `core/model_engine/predict.py` 剩余 6 条未接线候选，逐条实测：

    1. **`predict_structured` scaler 加载失败 handler（L178，本批新裁，不接）**
       —— 初判似真降级（scaler 缺失 → 未缩放特征直接算分，响应
       `fallback_used=False`、无 `fallback_reason`、`model_used` 与正常态同形，
       与第二批 `experimental_v121_scaler_fallback` 同型），但存在性实测发现
       **双重外部阻断**：① `structured_default_model` 当前默认 `"v1.23"`
       （v1.23 是 Pipeline 无需单独 scaler，`primary_needs_scaler=False`，
       根本进不了该分支）；② `models/*.pkl` 按 `.gitignore` L303-307 **有意
       不入库**（全仓 tracked pkl 数为 0），v1.20 主模型在官方交付形态下恒
       `FileNotFoundError` → L167 except → `model is None` → scaler 分支的
       `if model is not None` guard 为假。与第十二批 `_run_experimental_v121`
       外层（注册表移除 v1.21）同族，也同 keras 三条目「生产/CI 恒 MISSING」
       先例 —— 接线即计数器恒 0 的死代码。**解锁条件**（任一满足须重审）：
       默认配置切回 v1.20 且 pkl 纳入交付，或部署侧手工放置 v1.20 产物。
    2. **模型加载失败 handler（L167，V 型）**——`fallback_reason =
       "model_load_failed: {exc}"` 显式赋值，下游 `model_used=
       "structured_heuristic_fallback"` + `fallback_used=True`，响应可见。
       这正是当前交付形态下**真实可达**的降级点，且显式。
    3. **`predict_lite` 两个 handler（L887/L897，V 型）**——非有限概率 /
       通用异常都 `logger.error/warning` + `_incr_fallback()` +
       `fallback_reason` 显式写入响应（`lite_model_non_finite_output:` /
       `lite_model_unavailable:`），P0-5 修复后的成熟范式。
    4. **两条已裁维持（第十二批，本批实测复核防 stale）**——
       `_run_experimental_v121` 外层：`get_model_info(
       "structured_v1.21_binary_lr")` 实测仍返回 None（注册表已移除）；
       `_run_adapter`：`adapter_hit`/`adapter_miss` 专用计数器仍在（M 型）。

    **连带修复**：`predict.py` L147 注释漂移——原文写「v1.20 (默认)」，
    而 `config.py` 的 `structured_default_model` 默认值是 `"v1.23"`
    （S-02 时代以降改的配置、注释没跟上）。该漂移正是初裁被引向
    「默认路径」误判的根源，本批更正并写入可达性事实。
    """

    def test_scaler_handler_not_wired(self):
        """except 块级反向钉：scaler 加载失败 handler 不得接线（死代码家族），
        且行为锚点（未缩放告警日志）必须在。"""
        src = (BE / "core/model_engine/predict.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = ast.get_source_segment(src, node) or ""
            if "proceeding without scaling" not in body_src:
                continue
            hits += 1
            assert "record_silent_degradation" not in body_src, (
                "scaler 加载失败 handler 已接线 —— 「双重外部阻断不可达」"
                "裁定须重审（先验证默认配置与 pkl 交付形态）"
            )
        assert hits == 1, f"锚点 'proceeding without scaling' 命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"

    def test_model_load_handler_explicit_fallback(self):
        """V 型反向钉：模型加载失败 handler 未接线，且 fallback_reason 显式
        赋值必须在（响应可见性前提）。"""
        src = (BE / "core/model_engine/predict.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body_src = ast.get_source_segment(src, node) or ""
            if "model_load_failed" not in body_src:
                continue
            hits += 1
            assert "record_silent_degradation" not in body_src, (
                "模型加载失败 handler 已接线 —— V 型（fallback_reason 显式）裁定须重审"
            )
            assert "fallback_reason =" in body_src, (
                "模型加载失败 handler 的 fallback_reason 显式赋值消失 —— V 型裁定前提失效"
            )
        assert hits == 1, f"锚点 'model_load_failed' 命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"

    def test_lite_handlers_explicit_fallback(self):
        """V 型反向钉：predict_lite 两个 handler 未接线，且 fallback_reason
        显式写入必须在（P0-5 修复后的显式降级范式）。"""
        src = (BE / "core/model_engine/predict.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(src)
        for anchor in ("lite_model_non_finite_output", "lite_model_unavailable"):
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = ast.get_source_segment(src, node) or ""
                if anchor not in body_src:
                    continue
                hits += 1
                assert "record_silent_degradation" not in body_src, (
                    f"predict_lite handler（锚点 {anchor}）已接线 —— V 型裁定须重审"
                )
                assert "fallback_reason" in body_src and "_incr_fallback" in body_src, (
                    f"predict_lite handler（锚点 {anchor}）的显式降级信号消失 —— 裁定前提失效"
                )
            assert hits == 1, f"锚点 {anchor!r} 命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"

    def test_prior_rulings_still_hold(self):
        """第十二批两条已裁项的现状复核（防 stale）：v1.21 注册条目仍移除、
        adapter 专用计数器仍在。"""
        from app.core.model_registry import get_model_info

        assert get_model_info("structured_v1.21_binary_lr") is None, (
            "v1.21 注册条目已恢复 —— _run_experimental_v121 外层不再是死代码，"
            "第十二批裁定须重审"
        )
        src = (BE / "core/model_engine/predict.py").read_text(encoding="utf-8-sig")
        for counter in ('"adapter_hit"', '"adapter_miss"'):
            assert counter in src, f"adapter 专用计数器 {counter} 消失 —— M 型裁定前提失效"

    def test_delivery_form_premise(self):
        """死代码裁定的交付形态前提钉：默认配置 v1.23 + pkl 有意不入库。
        任一事实变化（切回 v1.20 / pkl 纳入交付）都意味着 scaler 路径恢复
        可达，本批裁定必须重审。"""
        import subprocess

        from app.core.config import settings

        assert settings.structured_default_model == "v1.23", (
            "structured_default_model 默认已切离 v1.23 —— scaler 分支可达性前提变化，须重审"
        )
        gitignore = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert "backend/models/*" in gitignore, (
            ".gitignore 的 models 排除规则消失 —— pkl 交付形态可能已变，须重审"
        )
        out = subprocess.run(
            ["git", "ls-files", "*.pkl"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert out.stdout.strip() == "", (
            f"仓库已出现 tracked pkl（{out.stdout.strip()[:200]}）—— "
            "scaler 路径可达性前提变化，须重审"
        )

    def test_doc_registered_batch21(self):
        """文档登记：P2_13「一之二十二」节（结构钉）含本批裁定关键标识；
        P2_11 附录含第二十一批条目；纯裁定批账实一致 W=96 / X=119 维持。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十二、" in doc13, (
            "P2_13 缺少第二十一批（一之二十二）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "proceeding without scaling", "model_load_failed",
            "lite_model_non_finite_output", "lite_model_unavailable",
            "structured_v1.21_binary_lr", "adapter_hit", "adapter_miss",
            "structured_default_model", ".gitignore",
            "双重外部阻断", "死代码", "V 型",
        ):
            assert token in doc13, f"P2_13 第二十一批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十一批" in doc11, "P2_11 附录缺少第二十一批条目"
        for token in ("model_engine/predict", "scaler", "v1.20", "v1.23"):
            assert token in doc11, f"P2_11 附录第二十一批条目缺少关键标识: {token}"
        counts_doc = "W=96 / X=119" in doc13 or "W 96" in doc13
        assert counts_doc, "第二十一批为纯裁定批，累计状态应维持 W=96 / X=119"


class TestP235Round13Batch22Declined:
    """第十三轮第二十二批：#35 X 桶**纯裁定批**（0 接线，W=96 / X=119 不变）
    + 连带修复一对「自出生即死」的专用计数器。

    挑簇对象（分类器现场重算确认仍在 X 桶）：`core/health.py` 1 条 +
    `services/auto_rollback_service.py` 5 条 + `core/pii_crypto.py` 4 条，
    共 10 条；另同文件 8 条已被分类器定型（health 6×H 检查型 /
    auto_rollback 2×S 自报失败）复核维持。

    **本批核心发现（连带修复）**：auto_rollback 锁/心跳家族的 M 型裁定
    （第二批 L143 / 第十八批）理由是「已有专用计数器
    `canary_rollback_check_lock_total{outcome}`」——存在性实测发现该
    计数器**自引入（e120ce3）起从未递增**：本仓 `app.core.metrics.Counter`
    是自研实现（`inc(**labels)`，无 `.labels()` 方法），而两个调用点写成
    prometheus_client 的 `.labels(...).inc()`，每次 AttributeError 被
    `except Exception` 吞掉只留 debug 日志。既有闸门只钉「调用点在源码里」
    的字面量，从无运行时计数断言，故死计数器活过全部往批。「失败路径不
    允许静默」的设计被计数器自身击穿。本批修两处调用点并补运行时回归。

    逐条裁定：
    1. **health.py L375 `stop_health_monitor`（K 型）**——lifespan 关闭阶段
       主动 `cancel()` 后台监控任务，`except CancelledError: pass` 是标准
       清理形态；取消是设计行为而非降级。
    2. **auto_rollback 锁/心跳家族 5 条（M/V 型，前提已修复）**——每个
       失败路径都有专用计数器 `canary_rollback_check_lock_total
       {outcome="unavailable"}` + error/warning 日志 + 显式返回值；
       `try_acquire_check_lock` 的 fail-open（Redis 不可用→返回 True
       降级执行）由 docstring 明示取舍。修复后 M 型前提真正成立。
    3. **pii_crypto 回退链中间步 4 条（V 型）**——`_decrypt_aes_gcm` /
       `decrypt_field` 的「当前密钥失败→试旧密钥」链中 `pass`/`continue`
       是回退尝试而非降级；链路末端显式 `raise InvalidTag` /
       `raise ValueError` + error 日志（exhausted），调用方可见。
    """

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    @staticmethod
    def _handlers_in_func(tree, src, funcname, exc_name=None):
        """AST 定位**指定函数内**的 except handler（可按异常名过滤）。

        不能全局扫异常名：如 InvalidTag 在 pii_crypto 有 4 处、CancelledError
        在 health.py 有 2 处，不过滤函数会把别的函数的 handler 误计入。
        """
        fn_span = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                fn_span = (node.lineno, node.end_lineno or node.lineno)
                break
        assert fn_span is not None, f"找不到函数 {funcname}（锚点漂移 = 闸门失效）"
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not (fn_span[0] <= node.lineno <= fn_span[1]):
                continue
            if exc_name is not None:
                names = (
                    [
                        getattr(n, "id", None) or getattr(n, "attr", None)
                        for n in ast.walk(node.type)
                    ]
                    if node.type
                    else []
                )
                if exc_name not in names:
                    continue
            out.append(node)
        return out

    def test_health_check_family_h_type_not_wired(self):
        """H 型复核维持：6 个健康检查 handler 未接线，且 return False +
        warning 日志锚点必须在（/health 经 HealthSnapshot 显式暴露）。"""
        src = self._read("core/health.py")
        tree = ast.parse(src)
        anchors = (
            ("check_database", "Database health check failed"),
            ("check_redis", "Redis health check timed out"),
            ("check_redis", "Redis health check failed"),
            ("check_celery_worker", "Celery worker health check timed out"),
            ("check_celery_worker", "Celery worker health check failed"),
            ("check_models", "Model health check failed"),
        )
        for funcname, anchor in anchors:
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = ast.get_source_segment(src, node) or ""
                if anchor not in body_src:
                    continue
                hits += 1
                assert "record_silent_degradation" not in body_src, (
                    f"health.py::{funcname} 目标 except（锚点 {anchor!r}）已接线"
                    " —— H 型（检查型，/health 显式暴露）裁定须重审"
                )
                assert "return False" in body_src, (
                    f"health.py::{funcname} 的 return False 显式上报消失"
                    f"（锚点 {anchor!r}）—— H 型裁定前提失效"
                )
            assert hits == 1, (
                f"锚点 {anchor!r} 命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"
            )
        # /health 暴露见证：四个字段进 HealthSnapshot，故障对负载均衡可见
        for field in (
            "database: bool | None = None",
            "redis: bool | None = None",
            "celery_worker: bool | None = None",
            "models: bool | None = None",
        ):
            assert field in src, f"HealthSnapshot 字段 {field!r} 消失 —— 暴露见证失效"
        # S 型元素见证：celery 检查失败同时置 heartbeat gauge=0
        assert "celery_worker_heartbeat" in src, "celery heartbeat gauge 见证消失"

    def test_stop_health_monitor_k_type_not_wired(self):
        """K 型反向钉：stop_health_monitor 的 CancelledError handler 未接线，
        且 cancel + info 日志清理锚点必须在（主动取消非降级）。

        注意不能全局扫 CancelledError：_health_monitor_loop 也有一个
        （L323），必须按函数过滤。"""
        src = self._read("core/health.py")
        tree = ast.parse(src)
        handlers = self._handlers_in_func(tree, src, "stop_health_monitor", "CancelledError")
        assert len(handlers) == 1, (
            f"stop_health_monitor 的 CancelledError handler 数 {len(handlers)}，期望 1"
        )
        seg = ast.get_source_segment(src, handlers[0]) or ""
        assert "record_silent_degradation" not in seg, (
            "stop_health_monitor 的 CancelledError handler 已接线"
            " —— K 型（任务取消）裁定须重审"
        )
        assert "pass" in seg, "stop_health_monitor 的清理 pass 消失 —— K 型锚点漂移"
        for anchor in ("_health_monitor_task.cancel()", 'logger.info("Health monitor stopped")'):
            assert anchor in src, f"stop_health_monitor 清理锚点 {anchor!r} 消失"

    def test_auto_rollback_lock_heartbeat_not_wired(self):
        """V/M 型反向钉：锁/心跳家族 5 条 X 桶候选未接线，且每失败路径的
        专用计数器 + 显式返回 + error 日志锚点必须在；2 条 S 型（指标
        自身失败）复核维持。"""
        src = self._read("services/auto_rollback_service.py")
        tree = ast.parse(src)
        # (anchor, 计数必须在**调用方 None 分支**还是本 handler, return 形态)
        # _redis_client_or_none 是 helper：自身只 error + return None，
        # 计数由三个调用方的 `if client is None:` 分支负责（下方见证）。
        cases = (
            ("获取 redis 客户端失败", False, "return None"),
            ("获取跨进程锁异常", True, "return True"),
            ("写入心跳失败", True, "return False"),
            ("读取心跳失败", True, "return None"),
            ("心跳内容解析失败", True, "return None"),
        )
        for anchor, need_counter, ret in cases:
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = ast.get_source_segment(src, node) or ""
                if anchor not in body_src:
                    continue
                hits += 1
                assert "record_silent_degradation" not in body_src, (
                    f"auto_rollback 目标 except（锚点 {anchor!r}）已接线"
                    " —— 「专用计数器 + 显式返回」裁定须重审"
                )
                if need_counter:
                    assert '_bump_lock_counter("unavailable")' in body_src, (
                        f"auto_rollback（锚点 {anchor!r}）的 unavailable 计数消失"
                        " —— M/V 型裁定前提失效"
                    )
                assert ret in body_src, (
                    f"auto_rollback（锚点 {anchor!r}）的 {ret} 显式上报消失"
                    " —— V 型裁定前提失效"
                )
            assert hits == 1, (
                f"锚点 {anchor!r} 命中 {hits} 处，期望 1（锚点漂移 = 闸门失效）"
            )
        # 调用方 None 分支计数见证：3 个调用方各 1 次 + 4 个 handler 各 1 次
        # = 7 处 unavailable 计数（Redis 不可用的每一跳都可观测）
        n = src.count('_bump_lock_counter("unavailable")')
        assert n == 7, (
            f"unavailable 计数点 {n} 处，期望 7（3 调用方 None 分支 + 4 handler）"
            " —— M 型「专用计数器全覆盖」裁定前提失效"
        )
        # API 形态防回退钉：自研 Counter 无 .labels()，写回旧形态即复燃死计数
        assert "canary_rollback_check_lock_total.inc(outcome=outcome)" in src, (
            "锁计数器调用不是自研 API `inc(outcome=...)` —— "
            " prometheus_client 形态（.labels().inc()）会重新变成死计数"
        )
        assert not self._has_labels_call(src), (
            "auto_rollback_service.py 出现 .labels( 调用（AST 级，注释/docstring"
            "不算）—— 死计数形态回潮"
        )
        # S 型复核：指标/gauge 自身失败只记 debug，主链路无失真
        for anchor in ("canary_rollback 锁计数更新失败", "心跳年龄 gauge 更新失败"):
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = ast.get_source_segment(src, node) or ""
                if anchor not in body_src:
                    continue
                hits += 1
                assert "record_silent_degradation" not in body_src, (
                    f"auto_rollback（锚点 {anchor!r}）已接线 —— S 型裁定须重审"
                )
            assert hits == 1, f"S 型锚点 {anchor!r} 命中 {hits} 处，期望 1"
        # 设计意图见证：docstring 明示「不允许静默」与 fail-open 取舍
        for witness in (
            "Redis 不可用等失败路径不允许静默",
            "不得静默跳过检查",
            "Redis 不可用时返回 True（降级执行）",
            "调用方必须自行记录/计数",
        ):
            assert witness in src, f"auto_rollback 设计意图见证 {witness!r} 消失"

    def test_pii_crypto_fallback_chains_not_wired(self):
        """V 型反向钉：pii_crypto 回退链 4 个中间 handler（pass/continue）
        未接线；链路末端显式 raise（AES-GCM InvalidTag / Fernet ValueError）
        与 exhausted error 日志必须在。"""
        src = self._read("core/pii_crypto.py")
        tree = ast.parse(src)
        # _decrypt_aes_gcm：两个 InvalidTag 中间步（pass / continue）
        aes_handlers = self._handlers_in_func(tree, src, "_decrypt_aes_gcm", "InvalidTag")
        assert len(aes_handlers) == 2, (
            f"_decrypt_aes_gcm 的 InvalidTag handler 数 {len(aes_handlers)}，期望 2"
        )
        for node in aes_handlers:
            seg = ast.get_source_segment(src, node) or ""
            assert "record_silent_degradation" not in seg, (
                "_decrypt_aes_gcm 回退链中间步已接线 —— V 型裁定须重审"
            )
        assert 'raise InvalidTag("AES-GCM decryption exhausted current + previous keys")' in src, (
            "_decrypt_aes_gcm 末端显式 raise 消失 —— V 型裁定前提失效"
        )
        # decrypt_field：两个 InvalidToken 中间步 + v2 InvalidTag 中转
        tok_handlers = self._handlers_in_func(tree, src, "decrypt_field", "InvalidToken")
        assert len(tok_handlers) == 2, (
            f"decrypt_field 的 InvalidToken handler 数 {len(tok_handlers)}，期望 2"
        )
        for node in tok_handlers:
            seg = ast.get_source_segment(src, node) or ""
            assert "record_silent_degradation" not in seg, (
                "decrypt_field 回退链中间步已接线 —— V 型裁定须重审"
            )
        # 末端：v1/v2 两条路径各一次显式 raise ValueError + exhausted error 日志
        raise_count = src.count('raise ValueError("PII 解密失败（密钥错误或数据损坏）")')
        assert raise_count == 2, (
            f"decrypt_field 的显式 raise ValueError 计 {raise_count}，期望 2"
            "（v1 Fernet + v2 AES-GCM 各一）—— V 型裁定前提失效"
        )
        assert "PII v1 decryption failed (exhausted current + %d previous keys)" in src, (
            "Fernet 末端 exhausted error 日志消失 —— V 型裁定前提失效"
        )
        assert "PII v2 decryption failed (exhausted current + previous keys)" in src, (
            "AES-GCM 末端 exhausted error 日志消失 —— V 型裁定前提失效"
        )

    def test_pii_crypto_rotation_probe_explicit(self):
        """见证钉：密钥轮换探测 is_encrypted_with_current_key 对解密失败
        返回 False（显式信号给轮换脚本），不是静默。"""
        src = self._read("core/pii_crypto.py")
        assert "def is_encrypted_with_current_key" in src
        assert "用于密钥轮换脚本判断是否需要重新加密某行数据" in src, (
            "轮换探测用途注释消失 —— 见证锚点漂移"
        )

    @staticmethod
    def _lock_counter(outcome: str) -> float:
        from app.core.metrics import canary_rollback_check_lock_total

        for labels, value in canary_rollback_check_lock_total.collect():
            if labels.get("outcome") == outcome:
                return value
        return 0.0

    @staticmethod
    def _takeover_counter(reason: str) -> float:
        from app.core.metrics import canary_rollback_takeover_total

        for labels, value in canary_rollback_takeover_total.collect():
            if labels.get("reason") == reason:
                return value
        return 0.0

    def test_dedicated_counters_actually_increment(self):
        """回归测试（本批连带修复的核心取证）：两个专用计数器必须**真的**
        递增。

        背景：调用点原写成 prometheus_client 的 `.labels(x=y).inc()`，而
        本仓 `app.core.metrics.Counter` 是自研类（`inc(**labels)`，无
        `.labels()`）——每次调用 AttributeError 被 except 吞掉只留 debug
        日志，计数器自引入（e120ce3）起恒 0。往批闸门只钉「调用点在源码
        里」的字面量，从无运行时断言，故死计数器活过全部批次。此处直接
        调 helper 并读计数器值，API 形态回退（.labels 复潮）即红。
        """
        import importlib

        ars = importlib.import_module("app.services.auto_rollback_service")
        cfm = importlib.import_module("app.services.canary_fallback_monitor")

        probe = "p2_35_b22_probe"
        lock_before = self._lock_counter(probe)
        takeover_before = self._takeover_counter(probe)
        ars._bump_lock_counter(probe)
        cfm._bump_takeover_counter(probe)
        assert self._lock_counter(probe) >= lock_before + 1, (
            "canary_rollback_check_lock_total 未递增 —— 锁/心跳计数器仍是死的"
            "（.labels().inc() 形态回潮？）"
        )
        assert self._takeover_counter(probe) >= takeover_before + 1, (
            "canary_rollback_takeover_total 未递增 —— 接管计数器仍是死的"
            "（.labels().inc() 形态回潮？）"
        )
        # fallback monitor 侧同样不得出现死计数形态
        monitor_src = self._read("services/canary_fallback_monitor.py")
        assert "canary_rollback_takeover_total.inc(reason=reason)" in monitor_src, (
            "接管计数器调用不是自研 API `inc(reason=...)`"
        )
        assert not self._has_labels_call(monitor_src), (
            "canary_fallback_monitor.py 出现 .labels( 调用（AST 级，注释/docstring"
            "不算）—— 死计数形态回潮"
        )

    @staticmethod
    def _has_labels_call(src: str) -> bool:
        """AST 判定是否存在 `.labels(...)` 调用（注释/docstring 里的字样不算）。

        自研 `app.core.metrics.Counter` 没有 `.labels()` 方法，出现该形态
        即意味着 prometheus_client API 误用回归（调用会被 except 吞成死计数）。
        """
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "labels":
                    return True
        return False

    async def test_runtime_lock_unavailable_observable(self):
        """运行时：Redis 不可用 → try_acquire_check_lock 返回 True（设计内
        降级执行）+ unavailable 计数器 +1（M/V 型显式，非静默）。"""
        import importlib

        mod = importlib.import_module("app.services.auto_rollback_service")

        async def _none():  # noqa: ANN202
            return None

        before = self._lock_counter("unavailable")
        orig = mod._redis_client_or_none
        mod._redis_client_or_none = _none
        try:
            got = await mod.try_acquire_check_lock()
        finally:
            mod._redis_client_or_none = orig
        assert got is True, "Redis 不可用未按设计返回 True（降级执行）"
        assert self._lock_counter("unavailable") >= before + 1, (
            "锁不可用未计数 —— 「专用计数器显式」裁定前提失效（假绿）"
        )

    async def test_runtime_heartbeat_missing_observable(self):
        """运行时：Redis 不可读 → get_check_heartbeat_age 返回 None +
        unavailable 计数器 +1；兜底 monitor 对 None 走接管（fail-safe
        方向是多查而非漏查），不得静默跳过。"""
        import importlib

        mod = importlib.import_module("app.services.auto_rollback_service")

        async def _none():  # noqa: ANN202
            return None

        before = self._lock_counter("unavailable")
        orig = mod._redis_client_or_none
        mod._redis_client_or_none = _none
        try:
            age = await mod.get_check_heartbeat_age()
        finally:
            mod._redis_client_or_none = orig
        assert age is None, "Redis 不可读未返回 None（调用方无从按未知处理）"
        assert self._lock_counter("unavailable") >= before + 1, (
            "心跳不可读未计数 —— 「专用计数器显式」裁定前提失效（假绿）"
        )
        # 调用方契约见证：fallback monitor 对 None 判定接管并计数
        monitor = self._read("services/canary_fallback_monitor.py")
        assert "heartbeat_missing" in monitor and "_bump_takeover_counter" in monitor, (
            "fallback monitor 的 None→接管计数分支消失 —— 「调用方不得静默跳过」前提失效"
        )

    async def test_runtime_decrypt_exhausted_raises(self):
        """运行时：密钥全耗尽 → 两条路径均显式 raise（InvalidTag /
        ValueError），回退链不是静默降级。"""
        import pytest

        from app.core.pii_crypto import _decrypt_aes_gcm, decrypt_field
        from cryptography.exceptions import InvalidTag

        # AES-GCM 链：合法 base64 但过短 → 当前密钥 InvalidTag → 旧密钥穷尽 → raise
        with pytest.raises(InvalidTag, match="exhausted"):
            _decrypt_aes_gcm("QUJDREU=", "email")
        # v2 路径经 decrypt_field：InvalidTag 被中转为 ValueError + error 日志
        with pytest.raises(ValueError, match="PII 解密失败"):
            decrypt_field("enc:v2:QUJDREU=", "email")
        # v1 Fernet 路径：InvalidToken 穷尽后同样显式 raise
        with pytest.raises(ValueError, match="PII 解密失败"):
            decrypt_field("enc:v1:QUJDREU=", "email")

    async def test_runtime_health_check_reports_false(self):
        """运行时：数据库健康检查失败 → return False（H 型显式，
        /health 据此降级，非静默）。"""
        from app.core.health import check_database

        class _BoomEngine:
            def connect(self):  # noqa: ANN202
                raise RuntimeError("db down")

        assert await check_database(_BoomEngine()) is False, (
            "数据库健康检查失败未返回 False —— H 型裁定前提失效"
        )

    def test_doc_registered_batch22(self):
        """文档登记：P2_13「一之二十三」节（结构钉）含本批裁定关键标识；
        P2_11 附录含第二十二批条目；纯裁定批账实一致 W=96 / X=119 维持。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十三、" in doc13, (
            "P2_13 缺少第二十二批（一之二十三）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "stop_health_monitor", "check_database", "check_redis",
            "check_celery_worker", "check_models",
            "try_acquire_check_lock", "publish_check_heartbeat",
            "get_check_heartbeat_age", "_redis_client_or_none",
            "canary_rollback_check_lock_total",
            "_decrypt_aes_gcm", "decrypt_field",
            "K 型", "V 型", "M 型", "H 型", "S 型",
            "health.py", "auto_rollback_service.py", "pii_crypto.py",
        ):
            assert token in doc13, f"P2_13 第二十二批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十二批" in doc11, "P2_11 附录缺少第二十二批条目"
        for token in ("health", "auto_rollback", "pii_crypto"):
            assert token in doc11, f"P2_11 附录第二十二批条目缺少文件名: {token}"
        counts_doc = "W=96 / X=119" in doc13 or "W 96" in doc13
        assert counts_doc, "第二十二批为纯裁定批，累计状态应维持 W=96 / X=119"


class TestP235Round13Batch23Declined:
    """第十三轮第二十三批：#35 X 桶**纯裁定批**（0 接线，W=96 / X=119 不变，
    `services/validation_engine.py` 5 条）。

    挑簇对象（分类器现场重算 + 存在性实测确认，见
    `tests/tools/verify_p2_35_batch23_candidates.py`）：

    - L422 `_run_model_inference` / L512 `_compute_baseline_metrics`：
      分类器仍判 **X**（真降级留档），第十三批 1.39 已裁 V 型，本批
      复核维持；
    - L147 `_load_csv_dataset` / L207 `calculate_metrics` 内层 auc /
      L271 `_calculate_small_classification_metrics`：分类器定型 **D**
      （脏数据探测——`types <= DIRTY_TYPES`，单条解析跳过、数据本来
      就是坏的），本批做首次书面裁定，复核维持 D 定型。

    逐条裁定：
    1. **L422/L512（V 型，第十三批已裁）**——失败均 `return None` +
       error 日志；调用方 `validate_model` 显式写入 `result.errors`
       （"Model inference unavailable …" / "Baseline metrics
       unavailable …"），与第十一轮 EXIF 剥离失败同口径。
    2. **L147（D 型 + V 型链）**——非数值特征**原样保留字符串**
       （`test_load_dataset_csv_numeric_conversion` 钉住），数据不
       丢失也不造假；字符串特征若令下游推理失败，走 L422 handler →
       `result.errors` 显式链，本 handler 无「洗白」形态。
    3. **L207（D 型 + V 型）**——`roc_auc_score` 仅对单类标签抛
       ValueError，此时 AUC 本就无定义，`metrics.auc = None` 是诚实
       取值且在返回值中显式。块级互锁：`calculate_metrics` 内层
       （L207，`pass`，不得接线）与外层（L237，已接线
       `calculate_metrics_failed`，必须仍在）两侧互钉。
    4. **L271（D 型 + V 型）**——非数字标签样本跳过是 H-Svc-16 设计
       行为（`test_calculate_metrics_skips_non_numeric_labels` 钉住），
       且循环后 `metrics.sample_count = total` 更新为**有效样本数**，
       调用方核对返回值即可发现样本缩减，不存在「残缺但看起来合法」。
    """

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    @staticmethod
    def _handlers_in_func(tree, src, funcname):
        """AST 定位指定函数内的全部 except handler（不过滤异常名）。

        不能全局扫异常名：`ValueError` 在本文件多处出现；且
        `calculate_metrics` 内有两个 handler（内层 auc L207 + 外层
        L237），必须按函数限定后再按块内容区分。
        """
        fn_span = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                fn_span = (node.lineno, node.end_lineno or node.lineno)
                break
        assert fn_span is not None, f"找不到函数 {funcname}（锚点漂移 = 闸门失效）"
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and fn_span[0] <= node.lineno <= fn_span[1]:
                out.append(node)
        return out

    def test_d_trio_reconfirmed_not_wired(self):
        """D 型三兄弟反向钉（块级）：三个 handler 均未接线，且各自
        「数据本来就是坏的 / 信号显式」见证锚点必须在。"""
        src = self._read("services/validation_engine.py")
        tree = ast.parse(src)

        # L147 _load_csv_dataset：单 handler，pass 保留原值，未接线
        hs = self._handlers_in_func(tree, src, "_load_csv_dataset")
        assert len(hs) == 1, f"_load_csv_dataset handler 数 {len(hs)}，期望 1"
        seg = ast.get_source_segment(src, hs[0]) or ""
        assert "record_silent_degradation" not in seg, (
            "_load_csv_dataset 的数值转换跳过 handler 已接线 —— D 型裁定须重审"
        )
        assert "pass" in seg, "非数值保留原值的 pass 消失（数据不再原样保留）"
        fn_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name == "_load_csv_dataset":
                fn_src = ast.get_source_segment(src, fn) or ""
        assert "float(value)" in fn_src, "数值转换尝试消失 —— D 型前提失效"

        # L207 calculate_metrics 内层 auc：两个 handler 中 body 含 pass 的
        # 是内层（不得接线）；另一个是外层（已接线，互锁必须仍在）
        hs = self._handlers_in_func(tree, src, "calculate_metrics")
        assert len(hs) == 2, f"calculate_metrics handler 数 {len(hs)}，期望 2"
        inner = [h for h in hs if "pass" in (ast.get_source_segment(src, h) or "")]
        outer = [h for h in hs if "record_silent_degradation" in (ast.get_source_segment(src, h) or "")]
        assert len(inner) == 1 and len(outer) == 1, (
            "内层（pass）/外层（已接线）handler 分辨失败 —— 块级定位失效"
        )
        inner_seg = ast.get_source_segment(src, inner[0]) or ""
        assert "record_silent_degradation" not in inner_seg, (
            "calculate_metrics 内层 auc handler 已接线 —— D/V 型裁定失效"
        )
        assert "services.validation_engine.calculate_metrics_failed" in (
            ast.get_source_segment(src, outer[0]) or ""
        ), "外层 calculate_metrics_failed 接线消失 —— 互锁前提失效"
        cm_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name == "calculate_metrics":
                cm_src = ast.get_source_segment(src, fn) or ""
        assert "metrics.auc = float(roc_auc_score(" in cm_src, (
            "auc 赋值语句消失 —— 内层 except 守护的对象不存在"
        )

        # L271 _calculate_small_classification_metrics：单 handler，
        # total -= 1 + continue，未接线；循环后 sample_count=有效数
        hs = self._handlers_in_func(tree, src, "_calculate_small_classification_metrics")
        assert len(hs) == 1, (
            f"_calculate_small_classification_metrics handler 数 {len(hs)}，期望 1"
        )
        seg = ast.get_source_segment(src, hs[0]) or ""
        assert "record_silent_degradation" not in seg, (
            "非数字标签跳过 handler 已接线 —— D 型裁定须重审"
        )
        assert "total -= 1" in seg and "continue" in seg, (
            "跳过样本时递减有效样本数的设计行为消失 —— D 型前提失效"
        )
        sm_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name == "_calculate_small_classification_metrics":
                sm_src = ast.get_source_segment(src, fn) or ""
        assert "metrics.sample_count = total" in sm_src, (
            "循环后 sample_count=有效样本数更新消失 —— 「返回值可核对」前提失效"
        )

    def test_d_trio_runtime_signals_visible(self, tmp_path):
        """运行时：三条 D 型路径的信号都在返回值里显式可见。"""
        import importlib

        ve = importlib.import_module("app.services.validation_engine")
        engine = ve.ValidationEngine()

        # L147：非数值特征原样保留字符串（不丢失、不造假），数值仍转换
        csv_path = tmp_path / "d.csv"
        csv_path.write_text("a,b,label\n1.5,x,1\n2,y,0\n", encoding="utf-8")
        features, _labels = engine.load_dataset(csv_path)
        assert features[0]["b"] == "x", "非数值特征未原样保留（数据被洗掉）"
        assert features[1]["b"] == "y"
        assert features[0]["a"] == 1.5 and features[1]["a"] == 2.0, "数值转换失效"

        # L271：非数字标签样本跳过 → sample_count=有效样本数（可核对）
        m = engine.calculate_metrics([1, "negative", 0], [1, "positive", 0])
        assert m.sample_count == 2, "有效样本数未如实反映（调用方无从核对）"
        assert m.accuracy == 1.0

        # L207：单类标签 → roc_auc_score ValueError → auc=None 显式，
        # 且内层 handler 不接线（record_silent_degradation 零调用）
        calls: list[str] = []
        orig_deg = ve.record_silent_degradation
        orig_roc = ve.roc_auc_score

        def _single_class(*_a, **_k):  # noqa: ANN002, ANN003
            raise ValueError("Only one class present in y_true")

        ve.record_silent_degradation = lambda loc: calls.append(loc)
        ve.roc_auc_score = _single_class
        try:
            m2 = engine.calculate_metrics([1, 1, 1, 1], [1, 0, 1, 0], [0.9, 0.8, 0.7, 0.6])
        finally:
            ve.record_silent_degradation = orig_deg
            ve.roc_auc_score = orig_roc
        assert m2.auc is None, "AUC 计算失败未留 None（调用方无从按未算处理）"
        assert m2.accuracy == 0.5, "其余指标未照常计算（不是干净的单点失败）"
        assert calls == [], "内层 auc handler 已接线 —— D/V 型裁定失效（假绿）"

    def test_x_pair_batch13_declines_reconfirmed(self):
        """X 二兄弟复核维持（第十三批 1.39 V 型）：handler 未接线，
        error 锚点 + return None 在；调用方 result.errors 显式链在。"""
        src = self._read("services/validation_engine.py")
        tree = ast.parse(src)
        for funcname, anchor in (
            ("_run_model_inference", "ValidationEngine: 模型推理失败"),
            ("_compute_baseline_metrics", "ValidationEngine: 加载 baseline dataset 失败"),
        ):
            hs = self._handlers_in_func(tree, src, funcname)
            assert len(hs) == 1, f"{funcname} handler 数 {len(hs)}，期望 1"
            seg = ast.get_source_segment(src, hs[0]) or ""
            assert "record_silent_degradation" not in seg, (
                f"{funcname} 已接线 —— 第十三批 V 型裁定须重审"
            )
            assert anchor in seg, f"{funcname} 的 error 日志锚点消失（锚点漂移）"
            assert "return None" in seg, f"{funcname} 的 return None 显式上报消失"
        # 调用方 V 型见证：validate_model 把两类不可用写进 result.errors
        vm_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "validate_model":
                vm_src = ast.get_source_segment(src, fn) or ""
        assert "Model inference unavailable for version" in vm_src, (
            "validate_model 的推理不可用 errors 分支消失 —— V 型前提失效"
        )
        assert "Baseline metrics unavailable for version" in vm_src, (
            "validate_model 的 baseline 不可用 errors 分支消失 —— V 型前提失效"
        )

    async def test_runtime_inference_unavailable_writes_errors(self, tmp_path):
        """运行时：推理不可用 → result.errors 显式 + 空指标（无假数据）。"""
        import importlib
        import json as _json

        ve = importlib.import_module("app.services.validation_engine")
        engine = ve.ValidationEngine()

        async def _none(*_a, **_k):  # noqa: ANN002, ANN003
            return None

        ds = tmp_path / "d.json"
        ds.write_text(
            _json.dumps([{"a": 1, "label": 1}, {"a": 2, "label": 0}]),
            encoding="utf-8",
        )
        orig = engine._run_model_inference
        engine._run_model_inference = _none
        try:
            result = await engine.validate_model("v1.20", ds)
        finally:
            engine._run_model_inference = orig
        assert any("Model inference unavailable" in e for e in result.errors), (
            "推理不可用未写入 result.errors —— V 型（调用方可见）裁定失效"
        )
        assert result.metrics.sample_count == 0 and result.metrics.accuracy is None, (
            "空指标被填了值 —— 出现假数据，裁定须重审"
        )

    def test_doc_registered_batch23(self):
        """文档登记：P2_13「一之二十四」节（结构钉）含本批裁定关键标识；
        P2_11 附录含第二十三批条目；纯裁定批账实一致 W=96 / X=119 维持。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十四、" in doc13, (
            "P2_13 缺少第二十三批（一之二十四）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "_load_csv_dataset", "calculate_metrics",
            "_calculate_small_classification_metrics",
            "_run_model_inference", "_compute_baseline_metrics",
            "validation_engine.py", "D 型", "V 型",
            "roc_auc_score", "sample_count",
        ):
            assert token in doc13, f"P2_13 第二十三批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十三批" in doc11, "P2_11 附录缺少第二十三批条目"
        assert "validation_engine" in doc11, "P2_11 附录第二十三批条目缺少文件名"
        assert "W=96 / X=119" in doc13, "第二十三批为纯裁定批，累计状态应维持 W=96 / X=119"


class TestP235Round13Batch24Wiring:
    """第十三轮第二十四批：#35 接线 1 处（ws 订阅循环崩溃重启窗口丢消息）
    + 12 处不接线裁定（W 96→97 / R 4→3 / X 119 不变，总数 334 不变）。

    接线裁定（分类器现场重算原判 R「自恢复」，本批改判接线）：

    - `core.ws.pubsub_loop_crashed`：`_pubsub_loop` 外层 handler 捕获订阅/
      连接异常后 sleep 1s 重启。R 型「下轮自愈」启发式在此**不成立**——
      自愈只恢复订阅、不恢复窗口内已丢失的消息：崩溃→重订阅的 ≥1s 内
      （Redis 持续故障时每秒崩溃一次，窗口长期存在）没有任何订阅者，
      其它 worker 发布到本节点用户 channel 的消息被 Redis 直接丢弃，
      而发布方的 `publish` 早已返回成功。与第十六批已接线的
      `core.ws.pubsub_message_handling_failed`（单条消息处理失败）是
      不同位置、不同形状：前者丢「一条」，此处丢「整个窗口的全部」。
      对照先例：第六批 inference persist 失败判 R 不接，因其下轮从
      进程内状态重新生成快照、无外部输入丢失；此处丢失的是外部输入
      （其它 worker 的消息），不可恢复。

    不接线 12 处（书面记账，详见 P2_13「一之二十五」）：
      S 型 2 —— `_inc_ws_auth_failure` / `connect` 的指标 inc 失败
      （指标采集自身失败，主链路不受影响；认证失败对客户端可见）；
      M 型 1 —— `disconnect` 指标 dec 失败（第十六批已裁，本批复核）；
      K 型 2 —— `stop_pubsub_subscriber` / `_pubsub_loop` 的
      CancelledError（关停与取消是正常控制流）；
      C 型 2 —— `stop_pubsub_subscriber` 的 stop 异常（仅关停时调用）、
      `_pubsub_loop` finally 的 aclose 失败（资源清理，debug 日志
      留痕，AUDIT-2026-10-06 已定性为泄漏定位）；
      D 型 2 —— `_handle_pubsub_message` 的畸形 payload / 非法
      channel（数据本来就是坏的，warning 日志 + return 丢弃）；
      V 型 3 —— `websocket_endpoint` 的 unexpected_error / db_error /
      runtime.error（均 close 带原因码 + 专用计数器 + 日志，
      失败对客户端显式）。
    """

    PAIRS = (("core.ws.pubsub_loop_crashed", "core/ws.py"),)

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    @staticmethod
    def _counter_value(location: str) -> float:
        from app.core.metrics import silent_degradation_total

        for labels, value in silent_degradation_total.collect():
            if labels.get("location") == location:
                return value
        return 0.0

    def test_locations_wired_in_code_and_doc(self):
        doc = AUDIT.read_text(encoding="utf-8")
        for loc, rel in self.PAIRS:
            src = self._read(rel)
            assert f'"{loc}"' in src, f"{rel} 未接线（源码找不到 location 字面量）: {loc}"
            assert loc in doc, f"接线点 {loc} 未登记进审计文档"

    async def test_runtime_pubsub_loop_crash_increments(self, monkeypatch):
        """运行时：psubscribe 抛异常 → 外层 handler 计数恰好 +1。

        防假绿：假 pubsub 的 psubscribe 必须真的被调用（否则计数可能
        来自别处）；且断言**恰好** +1 —— 重启后的第二轮崩溃尚未发生
        就被取消，避免「崩溃循环多轮计数」把断言写成 >= 而放过大计数。
        """
        import asyncio
        import importlib

        wsmod = importlib.import_module("app.core.ws")
        cachemod = importlib.import_module("app.core.cache")

        loc = self.PAIRS[0][0]
        before = self._counter_value(loc)

        class _BoomPubSub:
            def __init__(self) -> None:
                self.psubscribe_calls = 0

            async def psubscribe(self, *_args):  # noqa: ANN002, ANN204
                self.psubscribe_calls += 1
                raise RuntimeError("probe: psubscribe boom")

            async def aclose(self):  # noqa: ANN201
                return None

        boom_ps = _BoomPubSub()

        class _BoomClient:
            def pubsub(self):  # noqa: ANN201
                return boom_ps

        async def _fake_pubsub_client():  # noqa: ANN201
            return _BoomClient()

        # _pubsub_loop 函数体内 from-import → patch 定义方模块属性
        monkeypatch.setattr(cachemod, "get_redis_pubsub_client", _fake_pubsub_client)
        mgr = wsmod.ConnectionManager()
        task = asyncio.create_task(mgr._pubsub_loop())
        try:
            for _ in range(300):
                await asyncio.sleep(0.01)
                if self._counter_value(loc) > before:
                    break
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        assert boom_ps.psubscribe_calls >= 1, (
            "psubscribe 未被调用（假绿：计数可能来自别处）"
        )
        assert self._counter_value(loc) == before + 1, (
            "订阅循环崩溃未计数或计数翻倍（假接线/双计数）"
        )

    # 反向钉：本批 12 处不接线裁定。锚点写「不带引号」的语义串 ——
    # ast.unparse 会把字符串常量渲染成单引号，写死双引号会静默命中
    # 0 处（锚点失效 = 反向钉变摆设）。
    DECLINED_MARKERS = (
        # S 型：指标自报失败（采集自身，主链路不受影响）
        ("core/ws.py", "ws_auth_failures_total.inc failed"),
        ("core/ws.py", "websocket_connections_active.inc failed"),
        # M 型：第十六批已裁，本批复核维持
        ("core/ws.py", "websocket_connections_active.dec failed"),
        # K 型：循环取消是正常控制流
        ("core/ws.py", "WebSocket pubsub loop cancelled"),
        # C 型：关停/清理路径
        ("core/ws.py", "WebSocket pubsub subscriber stop encountered error"),
        ("core/ws.py", "WebSocket pubsub aclose() 失败"),
        # D 型：脏数据（畸形 payload / 非法 channel）
        ("core/ws.py", "WebSocket pubsub received malformed payload"),
        ("core/ws.py", "WebSocket pubsub invalid channel"),
        # V 型：显式失败上报（close 带原因码 + 计数器 + 日志）
        ("core/ws.py", "websocket.auth.unexpected_error"),
        ("core/ws.py", "websocket.auth.db_error"),
        ("core/ws.py", "websocket.runtime.error"),
    )

    def test_declined_handlers_not_wired(self):
        for rel, marker in self.DECLINED_MARKERS:
            tree = ast.parse(self._read(rel))
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = [ast.unparse(stmt) for stmt in node.body]
                if not any(marker in stmt for stmt in body_src):
                    continue
                hits += 1
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        nm = getattr(sub.func, "id", None) or getattr(sub.func, "attr", None)
                        assert nm != "record_silent_degradation", (
                            f"{rel} 的「{marker}」handler 已接线 —— "
                            "必须先推翻 P2_13「一之二十五」的裁定"
                        )
            assert hits >= 1, f"行为锚点「{marker}」在 {rel} 命中 0 处（锚点漂移 = 闸门失效）"

    def test_declined_stop_cancelled_not_wired(self):
        """K 型函数级反向钉：`stop_pubsub_subscriber` 的 CancelledError
        handler 体是裸 `pass`（无文本锚点可用），按 enclosing function
        定位；不得接线，且 pass 形状必须在（取消即正常关停）。"""
        src = self._read("core/ws.py")
        tree = ast.parse(src)
        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # 函数级限定：取 lineno 最紧致的 enclosing 函数
            fn = None
            for f in ast.walk(tree):
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if f.lineno <= node.lineno <= (f.end_lineno or f.lineno):
                        if fn is None or f.lineno > fn.lineno:
                            fn = f
            if fn is None or fn.name != "stop_pubsub_subscriber":
                continue
            type_names = []
            if node.type is not None:
                elts = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
                type_names = [getattr(e, "id", getattr(e, "attr", "?")) for e in elts]
            if "CancelledError" not in type_names:
                continue
            hits += 1
            seg = ast.get_source_segment(src, node) or ""
            assert "record_silent_degradation" not in seg, (
                "stop_pubsub_subscriber 的 CancelledError handler 已接线 —— K 型裁定须重审"
            )
            assert "pass" in seg, "取消 handler 的 pass 形状消失（锚点漂移）"
        assert hits == 1, (
            f"stop_pubsub_subscriber 的 CancelledError handler 命中 {hits} 处，期望 1"
        )

    # V 型见证锚点：三个 handler 必须仍把失败显式呈现给客户端
    V_WITNESSES = (
        ("websocket.auth.unexpected_error", "code=4001"),
        ("websocket.auth.db_error", "code=4503"),
        ("websocket.runtime.error", "disconnect"),
    )

    def test_declined_v_type_witnesses(self):
        """V 型判据钉住：认证/DB/运行期失败均由 close 原因码或 disconnect
        显式呈现，调用方（客户端）看得见 —— 不存在「洗白」形态。"""
        src = self._read("core/ws.py")
        tree = ast.parse(src)
        for marker, witness in self.V_WITNESSES:
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                body_src = [ast.unparse(stmt) for stmt in node.body]
                if not any(marker in stmt for stmt in body_src):
                    continue
                hits += 1
                seg = ast.get_source_segment(src, node) or ""
                assert witness in seg, (
                    f"「{marker}」handler 的 V 型见证「{witness}」消失 —— "
                    "失败不再对客户端显式，裁定须重审"
                )
            assert hits == 1, f"V 型锚点「{marker}」命中 {hits} 处，期望 1"

    def test_doc_registered_batch24(self):
        """文档登记：P2_13「一之二十五」节（结构钉）含本批裁定关键标识；
        P2_11 附录含第二十四批条目；计数账实一致 W=97 / X=119。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十五、" in doc13, (
            "P2_13 缺少第二十四批（一之二十五）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "_pubsub_loop", "pubsub_loop_crashed", "core/ws.py",
            "R 型", "S 型", "M 型", "K 型", "C 型", "D 型", "V 型",
            "psubscribe", "Redis",
        ):
            assert token in doc13, f"P2_13 第二十四批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十四批" in doc11, "P2_11 附录缺少第二十四批条目"
        assert "pubsub_loop_crashed" in doc11, "P2_11 附录第二十四批条目缺少接线 location"
        assert "W=97 / X=119" in doc13, "第二十四批后累计状态应为 W=97 / X=119"


class TestP235Round13Batch25Declined:
    """第十三轮第二十五批：#35 **纯裁定批**（0 接线，W=97 / X=119 不变，
    `app/tasks/scheduler.py` 5 条新候选）。

    第十九批已裁 scheduler 7 条（L401/L510/L994/L1001/L1054/L1102/
    L1170），本批 5 条为挑簇器列出的剩余未裁定项（ws.py 12 条系
    第二十四批已裁，挑簇器文档匹配格式缺陷误列，不在本批范围）。

    逐条裁定（分类器现场重算 + 运行时实证，见
    `tests/tools/verify_p2_35_batch25_candidates.py`）：

    1. **L81 `_notify_warning` 重试 except（M 型）**——失败先就地重试
       （`_NOTIFY_MAX_ATTEMPTS=2`），耗尽后 error 级完整上下文日志 +
       `warning_notify_failed_total` 专用计数器（运行时实测**真涨**
       +1，非第二十二批那对死计数器）+ Sentry + `return False`；
       调用方 `_daily_risk_scan_impl` L360 检查 `ok` 并汇总 error
       上报。专用计数器已覆盖同一失败，不重复接通用计数器。
    2. **L108 指标 inc 失败（S 型）**——`warning_notify_failed_total
       .inc()` 自身失败只记 debug；失败的是指标采集通道本身
       （第五批 S 型裁定同族）。
    3. **L129 Sentry capture_exception 失败（S 型）**——自报通道
       自身失败；主通道（L93 error 日志 + L107 计数器）已先触发，
       Sentry 是叠加的第二上报通道（第十九批①②③ 同型）。
    4. **L1134 产物目录 resolve 失败（F 型）**——AUDIT-P0-3 明示
       「宁可整个清理中止，也不能带残缺保护集继续删」：warning +
       `is_active = True` 保守跳过删除，安全方向 fail-safe。
    5. **L1150 产物文件 resolve 失败（F 型）**——同族保守跳过
       （「无法判定真实位置 → 保守视为 active」+ break）。

    运行时实证两条：① 推送失败 → `return False` + 专用计数器 +1 +
    探针确被调用 2 次（重试发生）+ 通用计数器零调用；② resolve
       失败 → 对照组删 1 个、实验组删 0 个且目录保留（差分证明
       保守跳过生效），全程零接线调用。
    """

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    @staticmethod
    def _handlers_in_func(tree, funcname):
        """AST 定位指定函数内的全部 except handler（不过滤异常名）。"""
        fn_span = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                fn_span = (node.lineno, node.end_lineno or node.lineno)
                break
        assert fn_span is not None, f"找不到函数 {funcname}（锚点漂移 = 闸门失效）"
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and fn_span[0] <= node.lineno <= fn_span[1]:
                out.append(node)
        return out

    def test_notify_trio_not_wired(self):
        """`_notify_warning` 三个 handler 块级反向钉 + 各自见证锚点。"""
        src = self._read("tasks/scheduler.py")
        tree = ast.parse(src)
        hs = self._handlers_in_func(tree, "_notify_warning")
        assert len(hs) == 3, f"_notify_warning handler 数 {len(hs)}，期望 3"

        by_marker = {}
        for h in hs:
            seg = ast.get_source_segment(src, h) or ""
            if "WebSocket notification attempt" in seg:
                by_marker["retry"] = (h, seg)
            elif "warning_notify_failed_total 指标上报失败" in seg:
                by_marker["metric"] = (h, seg)
            elif "Sentry capture_exception 调用失败" in seg:
                by_marker["sentry"] = (h, seg)
        assert set(by_marker) == {"retry", "metric", "sentry"}, (
            f"三个 handler 分辨失败：{sorted(by_marker)}（锚点漂移 = 闸门失效）"
        )
        for name, (_h, seg) in by_marker.items():
            assert "record_silent_degradation" not in seg, (
                f"_notify_warning 的 {name} handler 已接线 —— 裁定须重审"
            )
        # L81 重试 handler 见证：warning 级 + exc_info（重试不静默）
        assert "exc_info=True" in by_marker["retry"][1], "重试 except 的 exc_info 消失"
        # 函数级终端见证：return False + error 级汇总日志 + 专用计数器 + Sentry
        fn_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_notify_warning":
                fn_src = ast.get_source_segment(src, fn) or ""
        assert "return False" in fn_src, "重试耗尽的 return False 消失 —— V/M 前提失效"
        assert "AUDIT-P0-2 预警推送最终失败" in fn_src, "error 级汇总日志消失"
        assert "warning_notify_failed_total.inc()" in fn_src, "专用计数器调用消失"
        assert "capture_exception(" in fn_src, "Sentry 上报调用消失"

    def test_notify_caller_aggregates_failure(self):
        """调用方见证：`_daily_risk_scan_impl` 检查 `ok` 并汇总 error 上报
        —— 失败对调用方显式，不存在「洗白」形态。"""
        src = self._read("tasks/scheduler.py")
        tree = ast.parse(src)
        fn_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "_daily_risk_scan_impl":
                fn_src = ast.get_source_segment(src, fn) or ""
        assert fn_src, "找不到 _daily_risk_scan_impl（锚点漂移）"
        assert "ok = await _notify_warning(" in fn_src, "调用点消失 —— M 型前提失效"
        assert "if not ok:" in fn_src, "返回值检查消失 —— 失败不再对调用方显式"
        assert "failed_notifications.append(warning_id)" in fn_src, "失败汇总收集消失"
        assert "AUDIT-P0-2 本次风险扫描有" in fn_src, "汇总 error 日志消失"

    def test_cleanup_resolve_pair_not_wired(self):
        """`_cleanup_experiment_artifacts_impl` 两个 resolve 失败 handler
        （F 型保守跳过）块级反向钉 + `is_active = True` 见证。"""
        src = self._read("tasks/scheduler.py")
        tree = ast.parse(src)
        hs = self._handlers_in_func(tree, "_cleanup_experiment_artifacts_impl")
        markers = {
            "entry": "无法解析产物目录真实路径",
            "file": "无法解析产物文件真实路径",
        }
        found = {}
        for h in hs:
            seg = ast.get_source_segment(src, h) or ""
            for key, marker in markers.items():
                if marker in seg:
                    found[key] = (h, seg)
        assert set(found) == set(markers), (
            f"两个 resolve 失败 handler 分辨失败：{sorted(found)}（锚点漂移 = 闸门失效）"
        )
        for key, (_h, seg) in found.items():
            assert "record_silent_degradation" not in seg, (
                f"resolve 失败（{key}）handler 已接线 —— F 型裁定须重审"
            )
            assert "is_active = True" in seg, (
                f"resolve 失败（{key}）的保守跳过赋值消失 —— F 型前提失效"
            )
        # file 侧还带 break（停止遍历该目录）
        assert "break" in found["file"][1], "文件侧 resolve 失败的 break 消失"
        # 函数级见证：rmtree 仍在（保守跳过不影响正常删除路径）
        fn_src = ""
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name == "_cleanup_experiment_artifacts_impl":
                fn_src = ast.get_source_segment(src, fn) or ""
        assert "shutil.rmtree(entry" in fn_src, "rmtree 删除路径消失 —— F 型前提失效"

    async def test_runtime_notify_failure_explicit(self, monkeypatch):
        """运行时：推送双探针均炸 → return False + 专用计数器 +1 +
        探针确被调用 2 次（重试发生，防假绿）+ 通用计数器零调用。"""
        import importlib

        metrics = importlib.import_module("app.core.metrics")
        ws = importlib.import_module("app.core.ws")
        sched = importlib.import_module("app.tasks.scheduler")

        generic_calls: list[tuple] = []
        probe_calls: list[int] = []

        async def _boom(*_a, **_k):  # noqa: ANN002, ANN003
            probe_calls.append(1)
            raise RuntimeError("probe: notify boom")

        monkeypatch.setattr(metrics.silent_degradation_total, "inc", lambda *a, **k: generic_calls.append((a, k)))
        monkeypatch.setattr(ws, "notify_warning", _boom)
        monkeypatch.setattr(ws, "notify_counselor", _boom)

        before = sum(v for _, v in metrics.warning_notify_failed_total.collect())
        ok = await sched._notify_warning(7, 42, 2, "probe", None)
        after = sum(v for _, v in metrics.warning_notify_failed_total.collect())

        assert ok is False, "重试耗尽未返回 False —— 失败不再对调用方显式"
        assert len(probe_calls) == 2, (
            f"探针调用 {len(probe_calls)} 次，期望 2（重试一次）—— 防假绿失效"
        )
        assert after == before + 1, (
            f"专用计数器增量 {after - before}，期望 1（死计数器/假接线）"
        )
        assert generic_calls == [], (
            "通用静默降级计数器被调用 —— 说明已接线或接了别处，M/S 裁定须重审"
        )

    def test_runtime_resolve_failure_conservative_skip(self, tmp_path):
        """运行时差分：最老目录 resolve 抛 OSError → 保守跳过（removed 0、
        目录保留），对照组（无 probe）同设置删 1 个 —— 证明 F 型行为
        且无接线调用。"""
        import os
        import time
        from pathlib import Path
        from unittest.mock import patch

        import importlib

        sched = importlib.import_module("app.tasks.scheduler")

        def _build() -> list[Path]:
            trained = tmp_path / "trained"
            trained.mkdir(parents=True, exist_ok=True)
            dirs = []
            for i in range(11):
                d = trained / f"model_v{i}"
                d.mkdir(parents=True, exist_ok=True)
                (d / "model.bin").write_text("x")
                old = time.time() - (20 - i) * 86400
                os.utime(d, (old, old))
                dirs.append(d)
            return dirs

        # 对照组：11 个目录 keep_recent=10 → 删最老 1 个
        dirs = _build()
        with patch("app.core.config.settings.model_dir", str(tmp_path)):
            with patch("app.core.model_registry.MODEL_PATHS", {}):
                removed_control = sched._cleanup_experiment_artifacts_impl(keep_recent=10)
        assert removed_control == 1, f"对照组删除数 {removed_control}，期望 1（测试前提失效）"
        assert not dirs[0].exists() and dirs[1].exists(), "对照组删除目标不符（最老一个）"

        # 实验组：重建 + 最老目录 resolve 抛 → 保守跳过
        import shutil

        shutil.rmtree(tmp_path / "trained")
        dirs = _build()
        real_resolve = Path.resolve

        def _selective(self, *_a, **_k):  # noqa: ANN002, ANN003
            if self == dirs[0]:
                raise OSError("probe: resolve boom")
            return real_resolve(self, *_a, **_k)

        with patch("app.core.config.settings.model_dir", str(tmp_path)):
            with patch("app.core.model_registry.MODEL_PATHS", {}):
                with patch.object(Path, "resolve", _selective):
                    removed_probe = sched._cleanup_experiment_artifacts_impl(keep_recent=10)
        assert removed_probe == 0, (
            f"resolve 失败未保守跳过（removed={removed_probe}）—— F 型裁定失效"
        )
        assert dirs[0].exists(), "保守跳过的目录仍被删除 —— 安全方向失效"

    def test_doc_registered_batch25(self):
        """文档登记：P2_13「一之二十六」节（结构钉）含本批裁定关键标识；
        P2_11 附录含第二十五批条目；纯裁定批账实一致 W=97 / X=119 维持。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十六、" in doc13, (
            "P2_13 缺少第二十五批（一之二十六）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "_notify_warning", "_cleanup_experiment_artifacts_impl",
            "warning_notify_failed_total", "scheduler.py",
            "M 型", "S 型", "F 型", "AUDIT-P0-3", "保守跳过删除",
        ):
            assert token in doc13, f"P2_13 第二十五批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十五批" in doc11, "P2_11 附录缺少第二十五批条目"
        assert "scheduler" in doc11, "P2_11 附录第二十五批条目缺少文件名"
        assert "W=97 / X=119" in doc13, "第二十五批为纯裁定批，累计状态应维持 W=97 / X=119"


class TestP235Round13Batch26Declined:
    """第十三轮第二十六批：#35 **纯裁定批**（0 接线，W=97 / X=119 不变，
    `app/core/model_engine/loading.py` 收口）。

    挑簇器列 loading.py 7 条。逐条存在性核查后的真实库存：

    - **本批首次书面裁定的 3 条**（往批从未钉过）：
      1. **L244 `_incr_model_fallback` 指标 inc 失败（S 型）**——失败的是
         **指标采集通道自身**；P0 (2026-09-24) 注释已定性：变更前的 debug
         被提到 warning，因为「指标递增失败时 Grafana 降级率曲线会变平
         （运维看到降级率 0%），若日志同时静默则两种情况都不可见」。**日志
         侧盲区已被 2026-10-05 的升级补齐**（warning + exc_info=True）。
         注意此函数是第二批两次接线（L82 侧车 / L429 adapter）的 M 型
         理由来源；它自身失败只影响曲线形状，不改变任何调用方返回值。
      2. **L288 `preload` PermissionError** 3. **L294 `preload` OSError**
         ——**消费点已接线（V/M 混合型）**：`predict_structured` 的模型加载
         try **只捕获 `(FileNotFoundError, ValueError)`**（AST 实测，本文件
         该函数的全部 handler 就这两条），PermissionError / 一般 OSError
         **不被捕获 → 向调用方传播**；而主消费方 `risk_service_assessment`
         对该调用包了 `except Exception` 并已接
         `services.risk_service_assessment.structured_predict_fallback`
         （第二批接线），且返回 dict 自带 `"error": str(exc)` 与
         `"model_used": "heuristic_fallback"`。⇒ 真正导致用户可见结果降级的
         那一刻**已被计数**，预热期再加一次会重复计数。
    - **往批已裁、本批复核维持 4 条**：`_get_expected_hash` L82（V 型，
      P0-6 三态可区分）、`_load_adapter` L429（M 型 + 见证接线
      `adapter.pkl_fallback`）、`_load_model` L596（设计内 Hub 回退 +
      见证接线 `keras_compat_load_failed`）、`_patch_simple_imputer` L712
      （补丁失败后续 transform 可见 AttributeError）——第十九批
      `TestP235Round13Batch19Declined` 已钉，此处只做**记账一致性复核**。

    运行时三条：① preload 内 `_load_model` 抛 PermissionError → 循环继续、
    **零接线调用**（防与消费点重复计数）+ critical 日志文明；② 同型 OSError；
    ③ `predict_structured` 对该异常**真的向上抛**（pytest.raises 实证）。
    """

    LD_REL = "core/model_engine/loading.py"
    RS_REL = "services/risk_service_assessment.py"
    PT_REL = "core/model_engine/predict.py"

    PRELOAD_WIRED_LOCS = (
        "core.model_engine.loading.preload.missing_file",
        "core.model_engine.loading.preload.failed",
    )
    PRELOAD_OS_HANDLERS = (288, 294)
    CONSUMER_LOC = "services.risk_service_assessment.structured_predict_fallback"

    @staticmethod
    def _read(rel: str) -> str:
        return (BE / rel).read_text(encoding="utf-8-sig")

    @staticmethod
    def _handlers_of(src: str, tree, funcname: str) -> dict[int, str]:
        """返回 {handler 起始行: 源码片段}，按 enclosing function 定位。"""
        span = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                span = (node.lineno, node.end_lineno or node.lineno)
                break
        assert span is not None, f"找不到函数 {funcname}（锚点漂移 = 闸门失效）"
        out = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and span[0] <= node.lineno <= span[1]:
                out[node.lineno] = ast.get_source_segment(src, node) or ""
        return out

    def test_incr_model_fallback_metric_channel_not_wired(self):
        """L244（S 型）：指标采集通道自身失败不得接线；日志侧盲区必须仍在补位。"""
        src = self._read(self.LD_REL)
        tree = ast.parse(src)
        hs = self._handlers_of(src, tree, "_incr_model_fallback")
        hit = [line for line, seg in hs.items() if "model_fallback_total inc failed" in seg]
        assert len(hit) == 1, f"_incr_model_fallback 目标 handler 数 {len(hit)}，期望 1（锚点漂移）"
        seg = hs[hit[0]]
        assert "record_silent_degradation" not in seg, (
            "_incr_model_fallback 指标 inc 失败已接线 —— S 型裁定须重审"
        )
        # 见证钉：2026-10-05 把 debug 提到 warning 以补齐指标侧盲区 + 堆栈
        assert "logger.warning(" in seg, "warning 级升级消失 —— S 型前提失效"
        assert "exc_info=True" in seg, "exc_info 消失 —— 指标侧盲区失去补位"
        # 见证钉：专用计数器本身仍被调用（M 型理由来源没被拆掉）
        fn_seg = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_incr_model_fallback":
                fn_seg = ast.get_source_segment(src, node) or ""
        assert "model_fallback_total.inc(" in fn_seg, "专用计数器调用消失 —— M 型前提失效"

    def test_preload_oserror_pair_not_wired(self):
        """L288/L294（V/M 混合）：不得接线；两对见证必须仍在。"""
        src = self._read(self.LD_REL)
        tree = ast.parse(src)
        hs = self._handlers_of(src, tree, "preload")
        for line in self.PRELOAD_OS_HANDLERS:
            assert line in hs, f"preload L{line} handler 不在（行号漂移 = 闸门失效）"
            seg = hs[line]
            assert "record_silent_degradation" not in seg, (
                f"preload L{line} 已接线 —— 消费点已接线，重复计数须重审"
            )
            assert "logger.critical(" in seg, f"preload L{line} 的 critical 日志消失"
            assert "NON-RECOVERABLE" in seg, f"preload L{line} 的不可恢复定性消失"
        # 互锁：同函数 FileNotFoundError / 兜底 Exception 两条**仍在接线**
        wired_src = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.lineno in hs:
                s = ast.get_source_segment(src, node) or ""
                if "record_silent_degradation" in s:
                    wired_src += s
        for loc in self.PRELOAD_WIRED_LOCS:
            # 同上：子串匹配会被 `_typo` 变异绕过，按带引号的字面量核对
            assert f'"{loc}"' in wired_src, f"preload 的见证接线 {loc} 消失 —— 精细钉前提失效"

    def test_consumer_already_wired_and_oserror_propagates(self):
        """消费点见证：① `predict_structured` 只捕获 (FileNotFoundError,
        ValueError) ⇒ PermissionError / 一般 OSError 向调用方传播；
        ② 主消费方 `risk_service_assessment` 已对该调用接了专用 location
        并在返回 dict 里显式 error / heuristic_fallback。"""
        # ① 结构证据：该函数全部 handler 的捕获类型
        src = self._read(self.PT_REL)
        tree = ast.parse(src)
        fn_seg = ""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "predict_structured":
                fn_seg = ast.get_source_segment(src, node) or ""
        assert fn_seg, "找不到 predict_structured（锚点漂移）"
        caught = set()
        for node in ast.walk(ast.parse(fn_seg)):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                t = node.type
                names = [e.id for e in t.elts] if isinstance(t, ast.Tuple) else [getattr(t, "id", "")]
                caught.update(names)
        assert caught == {"FileNotFoundError", "ValueError"}, (
            f"predict_structured 捕获类型变为 {sorted(caught)} —— "
            "PermissionError 若被吞，L288/L294 的「向调用方传播」前提失效"
        )

        # ② 消费点接线仍在 + 返回形态显式（定位包住该调用的 Try，再取其 handler）
        rs = self._read(self.RS_REL)
        rs_tree = ast.parse(rs)
        target = None
        for node in ast.walk(rs_tree):
            if not isinstance(node, ast.Try):
                continue
            body = "".join(ast.get_source_segment(rs, s) or "" for s in node.body)
            if "await model_engine.predict_structured(" in body:
                assert len(node.handlers) == 1, "该 try 的 handler 数不为 1（锚点漂移）"
                target = node.handlers[0]
                break
        assert target is not None, (
            "risk_service_assessment 包 predict_structured 的 except Exception 消失 —— "
            "V/M 混合裁定前提失效"
        )
        seg = ast.get_source_segment(rs, target) or ""
        # 注意：必须按**带引号的字面量**核对（子串匹配会被 `_typo` 之类
        # 的变异绕过 —— 第二十六批 M2 实锤）
        assert f'"{self.CONSUMER_LOC}"' in seg, f"消费点接线 {self.CONSUMER_LOC} 消失"
        assert '"model_used": "heuristic_fallback"' in seg, "返回形态不再显式标注降级"
        assert '"error": str(exc)' in seg, "返回结果不再携带 error 字段"

    def test_runtime_preload_oserror_no_double_count(self, caplog):
        """运行时：preload 内 `_load_model` 抛 PermissionError / OSError →
        循环继续（不中断预热）、**零接线调用**（防与消费点重复计数）、
        critical 日志文明。"""
        import importlib
        import logging

        ld = importlib.import_module("app.core.model_engine.loading")
        me_mod = importlib.import_module("app.core.model_engine")

        calls: list[tuple] = []
        orig_sd = ld.record_silent_degradation
        orig_ids = me_mod.model_engine.PRELOAD_IDS

        def _record(*args, **kwargs):  # noqa: ANN002, ANN003
            calls.append((args, kwargs))

        ld.record_silent_degradation = _record  # patch **使用方命名空间**（第七批教训）
        me_mod.model_engine.PRELOAD_IDS = ["probe_model_for_batch26"]
        caplog.set_level(logging.CRITICAL)
        try:
            for exc_cls in (PermissionError, OSError):
                def _boom(self, model_id, _cls=exc_cls):  # noqa: ANN001, ANN002
                    raise _cls("probe: batch26 disk/permission failure")

                setattr(type(me_mod.model_engine), "_load_model", _boom)
                try:
                    me_mod.model_engine.preload()  # 不得抛出
                finally:
                    delattr(type(me_mod.model_engine), "_load_model")
        finally:
            ld.record_silent_degradation = orig_sd
            me_mod.model_engine.PRELOAD_IDS = orig_ids

        assert calls == [], (
            f"preload 的 OSError 族分支调用了通用计数器（{calls}）—— "
            "与消费点 structured_predict_fallback 重复计数，裁定须重审"
        )
        assert any("NON-RECOVERABLE" in r.message for r in caplog.records), (
            "critical 日志未出现 —— 「仍能型号化地notify运维」的前提失效"
        )

    async def test_runtime_oserror_propagates_from_predict(self, monkeypatch):
        """运行时：`predict_structured` 对 PermissionError 不捕获，真的向调用方抛。"""
        import importlib

        pytest = importlib.import_module("pytest")
        me_mod = importlib.import_module("app.core.model_engine")
        engine = me_mod.ModelEngine()

        async def _boom(model_id):  # noqa: ANN001
            raise PermissionError("probe: batch26 permission denied")

        monkeypatch.setattr(engine, "_load_model_async", _boom)
        # 完整 14 特征：否则 routing 会在「信息不足」处提前 return，走不到加载
        features = {
            "age": 22, "gender": 1, "study_year": 3, "cgpa": 3.5,
            "stress_level": 3, "sleep_duration": 7, "social_support": 4,
            "financial_pressure": 2, "family_history": 0,
            "academic_pressure": 3, "exercise_frequency": 2,
            "anxiety": 2, "panic_attack": 0, "treatment_seeking": 1,
        }
        with pytest.raises(PermissionError):
            await engine.predict_structured(features)

    def test_previously_ruled_loading_items_still_unwired(self):
        """记账一致性：第十九批已裁的 loading 4 条仍是未接线状态
        （本批不重复钉，只做跨批口径复核）。"""
        src = self._read(self.LD_REL)
        tree = ast.parse(src)
        # (函数名, 该藏仍需存在的锚点)
        checks = (
            ("_get_expected_hash", "无法解析侧车校验文件"),
            ("_patch_simple_imputer", "SimpleImputer _fill_dtype patch failed"),
            ("_load_adapter", '_incr_model_fallback("v1.24_adapter", "load_failed")'),
            ("_load_model", "无本地缓存"),
        )
        for funcname, anchor in checks:
            fn_seg = ""
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == funcname:
                    fn_seg = ast.get_source_segment(src, node) or ""
                    break
            assert fn_seg, f"找不到 {funcname}（锚点漂移）"
            assert anchor in fn_seg, f"{funcname} 的行为锚点 {anchor!r} 消失"
        # 这四条里只有 _load_adapter/_load_model 的同函数其它路径接线了——
        # 见证必须与第十九批口径一致（不能凭空多出也不能消失）
        for loc in (
            "core.model_engine.loading.adapter.pkl_fallback",
            "core.model_engine.loading.keras_compat_load_failed",
        ):
            assert f'"{loc}"' in src, f"第十九批见证接线 {loc} 消失 —— 跨批口径不一致"

    def test_doc_registered_batch26(self):
        """文档登记：P2_13「一之二十七」节（结构钉）含本批裁定关键标识；
        P2_11 附录含第二十六批条目；纯裁定批账实一致 W=97 / X=119 维持。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        assert "## 一之二十七、" in doc13, (
            "P2_13 缺少第二十六批（一之二十七）**节标题**（结构断言：正文提及不算）"
        )
        for token in (
            "loading.py", "_incr_model_fallback", "preload",
            "structured_predict_fallback", "predict_structured",
            "S 型", "FileNotFoundError, ValueError", "NON-RECOVERABLE",
        ):
            assert token in doc13, f"P2_13 第二十六批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十六批" in doc11, "P2_11 附录缺少第二十六批条目"
        assert "loading" in doc11, "P2_11 附录第二十六批条目缺少文件名"
        assert "W=97 / X=119" in doc13, "第二十六批为纯裁定批，累计状态应维持 W=97 / X=119"


class TestP235Round13Batch27Declined:
    """第二十七批：app/core/sentry.py 6 条 + app/api/v1/metrics.py 5 条。

    两簇在往批审计文档中**完全无裁定记载**（sentry 此前只在「scheduler 里的
    Sentry 调用点」语境被裁过，metrics.py 的 5 个 _set_* 采集器从未逐条裁过），
    属真正的新库存而非行号平移。分类器现场重算 11 条全判 S（两文件均在
    SELF_REPORT_FILES 里），本批逐条独立复核后维持不接线，桶计数不变。
    """

    SENTRY_REL = "app/core/sentry.py"
    METRICS_REL = "app/api/v1/metrics.py"

    # 裁定不接线的 11 处（文件, 行号, 所属函数）
    TARGETS = (
        (SENTRY_REL, 103, "init_sentry"),
        (SENTRY_REL, 148, "capture_exception"),
        (SENTRY_REL, 163, "capture_message"),
        (SENTRY_REL, 27, "_extract_status_code"),
        (SENTRY_REL, 36, "_extract_status_code"),
        (SENTRY_REL, 47, "_extract_status_code"),
        (METRICS_REL, 84, "_set_breaker_metrics"),
        (METRICS_REL, 96, "_set_db_pool_metrics"),
        (METRICS_REL, 117, "_set_model_fallback_metric"),
        (METRICS_REL, 136, "_set_mttr_metrics"),
        (METRICS_REL, 152, "_set_slo_metrics"),
    )

    def _read(self, rel: str) -> str:
        return (BEPKG / rel).read_text(encoding="utf-8")

    @staticmethod
    def _handler_at(src: str, line: int):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.lineno == line:
                return node
        return None

    def test_eleven_handlers_exist_and_not_wired(self):
        """存在性核查 + 反向钉：11 处 handler 均在原位且均未接线。"""
        for rel, line, fn_name in self.TARGETS:
            src = self._read(rel)
            handler = self._handler_at(src, line)
            assert handler is not None, f"{rel}:{line} handler 消失或位移"
            seg = ast.get_source_segment(src, handler) or ""
            assert "record_silent_degradation" not in seg, (
                f"{rel}:{line}（{fn_name}）被接线 —— 第二十七批裁定为不接线，"
                "若改判需先更新审计文档并同步桶计数棘轮"
            )
            assert "silent_degradation_total" not in seg, (
                f"{rel}:{line}（{fn_name}）出现直调式 silent_degradation_total 计数"
            )

    def test_sentry_handlers_keep_warning_anchors(self):
        """sentry 三处 SDK 层 handler 的 warning 文案仍在（诊断侧留痕）。"""
        src = self._read(self.SENTRY_REL)
        for line, token in (
            (103, '"sentry_sdk not available, skipping Sentry initialization"'),
            (148, '"sentry_sdk not available, exception not captured"'),
            (163, '"sentry_sdk not available, message not captured"'),
        ):
            handler = self._handler_at(src, line)
            assert handler is not None, f"sentry.py:{line} handler 消失"
            seg = ast.get_source_segment(src, handler) or ""
            assert token in seg, f"sentry.py:{line} 的 warning 文案消失：{token}"

    def test_extract_status_code_keeps_three_paths(self):
        """_extract_status_code 三条 ValueError/TypeError handler 的设计行为见证。

        既有 tests/test_sentry.py::TestExtractStatusCode 已钉「非数值 status code
        → None」，本批复核三条 `pass` 路径未被裁掉（裁掉任一条会让该测试红）。
        """
        src = self._read(self.SENTRY_REL)
        tree = ast.parse(src)
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_extract_status_code":
                fn = node
                break
        assert fn is not None, "_extract_status_code 函数消失"
        handlers = [n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)]
        assert len(handlers) == 3, f"_extract_status_code handler 数变为 {len(handlers)}，应为 3"
        for node in handlers:
            types = ast.unparse(node.type)
            assert types == "(ValueError, TypeError)", f"捕获类型漂移为 {types}"
            seg = ast.get_source_segment(src, node) or ""
            assert seg.strip().endswith("pass"), "三条 handler 应为 `pass` 后继续下一路径"
        # 三条路径各自的取值键仍在（按 AST 的字符串实参断言，不受引号风格影响）
        wanted = {"response_status_code", "http.status_code", "http.response.status_code"}
        got = set()
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                got.add(node.args[0].value)
        assert wanted <= got, f"三条路径的取值键缺失：缺 {sorted(wanted - got)}"
        assert "return None" in ast.unparse(fn), "最终 return None 消失"

    def test_metrics_collectors_keep_warning_anchors(self):
        """metrics.py 五个 _set_* 采集器的 warning 文案仍在。"""
        src = self._read(self.METRICS_REL)
        for line, token in (
            (84, '"%s circuit metric collection failed: %s"'),
            (96, '"db_pool_size metric collection failed: %s"'),
            (117, '"model_fallback_rate metric collection failed: %s"'),
            (136, '"mttr metric collection failed: %s"'),
            (152, '"slo metric collection failed: %s"'),
        ):
            handler = self._handler_at(src, line)
            assert handler is not None, f"metrics.py:{line} handler 消失"
            seg = ast.get_source_segment(src, handler) or ""
            assert token in seg, f"metrics.py:{line} 的 warning 文案消失：{token}"

    def test_redis_collector_keeps_fail_visible_paradigm(self):
        """文件内正确范式互锁：_set_redis_metrics 失败时把状态编码进指标值。

        这是 metrics.py 里唯一「失败被显式编码」的采集器（L108
        `redis_circuit_state.set(2)`），与五处只 warning 的采集器形成对照。
        若有人把 set(2) 改成纯 warning，本钉会红 —— 那会把「Redis 不可达」
        从可观测降为静默。
        """
        src = self._read(self.METRICS_REL)
        tree = ast.parse(src)
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_set_redis_metrics":
                fn = node
                break
        assert fn is not None, "_set_redis_metrics 函数消失"
        handler = None
        for node in ast.walk(fn):
            if isinstance(node, ast.ExceptHandler):
                handler = node
                break
        assert handler is not None, "_set_redis_metrics 的 except handler 消失"
        seg = ast.get_source_segment(src, handler) or ""
        assert "redis_circuit_state.set(2)" in seg, (
            "失败时的 redis_circuit_state.set(2) 消失 —— "
            "Redis 不可达将从可观测退化为静默"
        )
        assert "logger" not in seg, (
            "该 handler 应只设指标不记日志（对照范式），出现 logger 说明形态漂移"
        )

    def test_runtime_init_sentry_failure_records_ok(self):
        """运行时：SDK 不可导入时 /health/startup 把 init_sentry 记为 ok。

        这是本批最关键的可客断言 —— 证明「不接线」不是因为信号已显式，而是
        因为 signal 通道（startup_status）确实把它记成了成功：运维读
        /health/startup 无法区分「Sentry 已初始化」与「SDK 根本导不进来」。
        判据据此改写（详见审计文档）：不是 V 型，而是 S 型 —— 失败的是
        可观测性设施自身启动，且 sentry-sdk 是 requirements.lock 硬锁依赖
        （镜像构建期安装），生产不可达。
        """
        import builtins
        import importlib
        import sys

        ss = importlib.import_module("app.core.startup_status")
        sentry_mod = importlib.import_module("app.core.sentry")

        real_import = builtins.__import__

        def _blocked(name, *a, **k):
            if name == "sentry_sdk" or name.startswith("sentry_sdk."):
                raise ImportError("probe: sentry_sdk blocked")
            return real_import(name, *a, **k)

        saved = {k: v for k, v in sys.modules.items() if k.startswith("sentry_sdk")}
        for k in saved:
            del sys.modules[k]
        builtins.__import__ = _blocked
        try:
            ss.record_step_sync(
                "init_sentry",
                lambda: sentry_mod.init_sentry(dsn="https://key@sentry.io/123"),
                fatal=False,
            )
        finally:
            builtins.__import__ = real_import
            for k in [m for m in sys.modules if m.startswith("sentry_sdk")]:
                del sys.modules[k]
            sys.modules.update(saved)

        rec = ss.startup_status.components["init_sentry"]
        assert rec.status == "ok", (
            f"init_sentry 启动状态变为 {rec.status!r} —— 若改为 failed/skipped，"
            "说明 signal 已显式，第二十七批「S 型不接线」判据需重估"
        )
        assert rec.error_type == "", "不应有 error_type"

    def test_runtime_extract_status_code_non_numeric_returns_none(self):
        """运行时：非数值 status code 三条路径都返回 None（既有设计行为见证）。"""
        import importlib

        sentry_mod = importlib.import_module("app.core.sentry")
        extract = sentry_mod._extract_status_code

        assert extract({"request": {"response_status_code": "not-a-number"}}) is None
        assert extract({"tags": {"http.status_code": "bad"}}) is None
        assert extract(
            {"contexts": {"trace": {"tags": {"http.response.status_code": []}}}}
        ) is None
        # 对照：合法值仍能提取（证明不是「一律返回 None」的退化实现）
        assert extract({"request": {"response_status_code": 500}}) == 500

    def test_existing_sentry_tests_still_pin_design_behavior(self):
        """往批既有测试互锁：三处关键设计行为测试仍在且钉住预期语义。"""
        test_src = (BEPKG / "tests" / "test_sentry.py").read_text(encoding="utf-8")
        for token in (
            "def test_sdk_import_failure_does_not_raise",
            "def test_extract_handles_invalid_code_gracefully",
            "def test_5xx_always_retained",
        ):
            assert token in test_src, f"既有设计行为测试消失：{token}"
        main_src = self._read("app/main.py")
        assert 'record_step_sync("init_sentry", _init_sentry, fatal=False)' in main_src, (
            "main.py 的 init_sentry 启动登记（fatal=False）消失 —— "
            "「不抛出以免阻断启动」的前提失效"
        )
        assert "# R-006: sentry 初始化失败不影响启动 (仅监控降级)" in main_src, (
            "R-006 设计注释消失"
        )

    def test_document_registration(self):
        """文档登记：P2_13「一之二十八」节 + P2_11 附录第二十七批条目。"""
        doc13 = (DOCS / "P2_13_ROUND13_AUDIT.md").read_text(encoding="utf-8")
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "## 一之二十八、" in doc13, "P2_13 缺少「一之二十八」节标题"
        for token in (
            "sentry.py",
            "api/v1/metrics.py",
            "init_sentry",
            "_set_redis_metrics",
            "S 型",
        ):
            assert token in doc13, f"P2_13 第二十七批登记缺少关键标识: {token}"
        doc11 = AUDIT.read_text(encoding="utf-8")
        assert "第十三轮第二十七批" in doc11, "P2_11 附录缺少第二十七批条目"
        assert "sentry" in doc11, "P2_11 附录第二十七批条目缺少文件名"
        assert "W=97 / X=119" in doc13, "第二十七批为纯裁定批，累计状态应维持 W=97 / X=119"
