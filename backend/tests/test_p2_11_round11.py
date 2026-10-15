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
            "W": 78,   # 已接线（含第十一轮直调风格 2 处 + 第十二轮第五/六批 10 + 第十三轮前十三批净 51）
            "P": 15,   # ImportError 特性探测（第十一批首次把探针记录本身接线：file_security
                        # 的 ImportError 探针分支 wired=True → W，P 16→15；总数 334 不变）
            "S": 36,   # 自报失败（metrics/sentry/otel/gauge）
            "D": 22,   # 脏数据探测
            "C": 7,    # 清理路径
            "H": 6,    # 检查型
            "K": 11,   # 任务取消
            "R": 4,    # 自恢复
            "M": 6,    # 已有专用计数器
            "G": 8,    # fail-closed 安全
            "V": 2,    # 显式失败上报
            "F": 2,    # 保守 fail-safe（宁可少清理/不发）
            "X": 137,  # 真降级留档（第十三批 5 处实记录 X→W：escalation 通知失败 /
                        # idempotency begin/settle/dismiss / validation 指标中段失败；
                        # 故 X 142→137、W 73→78；总数 334 不变。
                        # 前一行起为第十二批口径：X 145→142、W 70→73；
                        # 再前一批含 ImportError 探针接线：X 147→145、P 16→15。）
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
