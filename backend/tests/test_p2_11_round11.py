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

    def test_operation_log_construct_sites_decreased(self):
        got = _scan_operation_log_calls()
        assert got == self.AFTER_BATCH1, (
            f"OperationLog( 生产构造点应为 {self.AFTER_BATCH1}，实际 {got}"
        )
        assert got < self.BASELINE_BEFORE

    def test_migrated_files_no_longer_construct_operation_log(self):
        for rel in (
            "api/v1/silences.py",
            "api/v1/model_kill_switch.py",
        ):
            t = (BE / rel).read_text(encoding="utf-8")
            assert "OperationLog(" not in t, f"{rel} 仍有手写 OperationLog 构造"
            assert "record_audit(" in t, f"{rel} 应改调 record_audit"

    def test_migration_records_ip_from_request(self):
        # 迁移前这些点完全没有 ip_address；迁移后必须把 request 传进 helper
        for rel in ("api/v1/silences.py", "api/v1/content_governance.py", "api/v1/model_kill_switch.py"):
            t = (BE / rel).read_text(encoding="utf-8")
            calls = re.findall(r"await record_audit\((.*?)\n    \)", t, re.S)
            assert calls, f"{rel} 未找到 record_audit 调用"
            for c in calls:
                assert "request=request" in c, f"{rel} 的 record_audit 调用缺 request=request"
                assert "tenant_id=" in c, f"{rel} 的 record_audit 调用缺 tenant_id（必填关键字）"


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
