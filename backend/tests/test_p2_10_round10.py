"""P2 第十轮闸门：#37 FE helper + #32 BE/FE收编 + CSV + #38。

反假闸门设计：
- 不断言"helper 存在"，断言收编点原文消失 + helper 被调用（E35 教训）。
- 异常/计数断言带 match/精确值（E33 教训）；扫描器先经临时违规文件自证。
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
BE = REPO / "backend/app"
FE = REPO / "frontend/src"

BE_IN_SCOPE = [
    "services/counselor_service_binding.py",
    "services/counselor_service_consultation.py",
    "services/counselor_service_group.py",
    "services/counselor_service_warning.py",
    "services/intervention_service.py",
    "services/warning_service.py",
    "services/review_service.py",
    "services/admin_service_log.py",
    "services/admin_service_stats.py",
    "services/anomaly_detection_service.py",
    "services/admin_service_template.py",
    "services/auth_service.py",
    "tasks/scheduler.py",
    "core/seed.py",
]
ROLE_LIT = re.compile(r'"(counselor|admin|super_admin|user)"')
# 豁免形态：label 别名 / target_type / 用户名字面量 / 注释 / doctest / dict 键（响应字段名/查找键，非角色语义）
EXEMPT = re.compile(r"\.label\(|target_type|username|^\s*#|>>>|^\s*\"(counselor|admin|super_admin|user)\"\s*:")


class TestP232BERoles:
    def test_no_bare_role_literals_in_scope(self):
        bad: list[str] = []
        for f in BE_IN_SCOPE:
            for i, l in enumerate((BE / f).read_text(encoding="utf-8").splitlines(), 1):
                if ROLE_LIT.search(l) and not EXEMPT.search(l):
                    bad.append(f"{f}:{i} {l.strip()[:100]}")
        assert bad == [], "收编文件仍有裸角色字面量:\n" + "\n".join(bad)

    def test_constants_actually_used(self):
        # P2-33 第六批：迁移到 record_audit 后，角色形参语义由 `operator_role=`
        # 变为 `actor_role=`（helper 侧口径）。断言改为 pin「角色取自 USER_ROLE_*
        # 常量」这一行为，不再 pin 具体形参名 —— 否则迁移后断言恒假。
        t = (BE / "services/counselor_service_binding.py").read_text(encoding="utf-8")
        assert "USER_ROLE_COUNSELOR" in t
        assert re.search(r"actor_role\s*=\s*USER_ROLE_COUNSELOR", t), (
            "binding 审计角色必须来自 USER_ROLE_* 常量"
        )
        t = (BE / "services/review_service.py").read_text(encoding="utf-8")
        assert re.search(
            r"actor_role\s*=\s*USER_ROLE_ADMIN if is_admin else USER_ROLE_COUNSELOR",
            t,
        ), "review 审计角色必须来自 USER_ROLE_* 常量"

    def test_require_role_args_exempt_with_reason(self):
        # require_role("…") 是 Depends 工厂参数语义，50+ 端点签名，移治理轮——
        # 本断言锁死"豁免仍在"，防有人半收编造成两派并存无人记账。
        t = (BE / "api/v1/counselor.py").read_text(encoding="utf-8")
        assert 'require_role("counselor")' in t


class TestP237FERoles:
    BEHAVIORAL = re.compile(r"(===|!==|includes\()")

    def test_no_bare_behavioral_checks(self):
        # 第十一轮：`components/common/BottomNav.vue` 已按 #39 处置结论删除
        # （死组件，无 import 方，见 docs/RETENTION_REGISTRY.md 与 P2_11 审计），
        # 故从点名清单移除。该清单是第十轮 #37 的收编目标文件，删文件不等于免检：
        # 全仓裸角色判定改由 scan_p2_11_audit.py 的口径复核（本轮已重扫，见审计文档）。
        targets = [
            "components/common/HelpCenter.vue",
            "layouts/components/main-layout/useLayoutMenu.ts",
            "layouts/MainLayout.vue",
            "router/guard.ts",
            "views/common/ForbiddenPage.vue",
            "views/counselor/CounselorReviewListPage.vue",
            "views/user/components/experiment-charts/EvalResultCard.vue",
            "views/user/components/user-model-training/useModelTrainingData.ts",
            "views/user/components/user-settings-page/ProfileCard.vue",
            "views/user/components/user-settings-page/BindingCard.vue",
            "views/user/UserSettingsPage.vue",
            "App.vue",
        ]
        lit = re.compile(r"'(counselor|admin|super_admin|user)'")
        bad: list[str] = []
        for f in targets:
            for i, l in enumerate((FE / f).read_text(encoding="utf-8").splitlines(), 1):
                s = l.strip()
                if s.startswith("//") or s.startswith("*"):
                    continue
                if lit.search(l) and ("===" in l or "!==" in l):
                    bad.append(f"{f}:{i} {s[:100]}")
        assert bad == [], "仍有裸角色比较:\n" + "\n".join(bad)

    def test_helpers_called_not_just_existing(self):
        t = (FE / "router/guard.ts").read_text(encoding="utf-8")
        assert "isAdminRole(role)" in t and "isCounselorRole(role)" in t and "isUserRole(role)" in t
        t = (FE / "views/counselor/CounselorReviewListPage.vue").read_text(encoding="utf-8")
        assert "isAdminRole(auth.role)" in t

    def test_no_import_inside_import_block(self):
        # 回归闸：applier 曾把 import 插进多行 import 块内部（BottomNav/useModelTrainingData）。
        # BottomNav 是死组件（无 import 方），构建/测试/CI 全碰不到，只能靠本断言。
        # 第十一轮：BottomNav.vue 已按 #39 处置结论删除（见 docs/RETENTION_REGISTRY.md
        # 与 P2_11 审计），此处同步移除该路径；其"死组件"职责改由
        # test_p2_11_round11.py::test_orphan_component_ratchet 用棘轮把守（全组件扫描，
        # 不再逐个点名）。
        for f in [
            "views/user/components/user-model-training/useModelTrainingData.ts",
        ]:
            lines = (FE / f).read_text(encoding="utf-8").splitlines()
            depth = 0
            for i, l in enumerate(lines, 1):
                s = l.strip()
                if s.startswith("import ") and depth > 0:
                    raise AssertionError(f"{f}:{i} import 落在多行块内部: {s[:80]}")
                depth += s.count("{") - s.count("}")
                if depth < 0:
                    depth = 0

    def test_exemptions_documented(self):
        # 类型并集 / 路由 path / meta.role 数组 / 模板表单值豁免仍在
        assert "role: 'user' | 'counselor' | 'admin' | 'super_admin'" in (
            FE / "types/auth.ts"
        ).read_text(encoding="utf-8")


class TestP232CSV:
    FILES = [
        "views/user/components/PhysioTab.vue",
        "views/user/components/composables/useTextPredictionHistory.ts",
        "views/user/components/structured-steps/usePredictionHistory.ts",
    ]

    def test_use_ssot(self):
        for f in self.FILES:
            t = (FE / f).read_text(encoding="utf-8")
            assert "csvEscape" in t, f"{f} 未改调 SSOT"
            assert 'sanitizeCellForExcel(String(cell)).replace' not in t, f"{f} 仍有内联链"


FULL = re.compile(r"(必然|恒为|恒[A-Z]|永远|不会|保证|一定|所有.+都会|仅当|只[有会])")


def _assertive(p: pathlib.Path) -> list[str]:
    out = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return out
    for i, l in enumerate(lines, 1):
        s = l.strip()
        if (s.startswith("#") or s.startswith("//") or s.startswith("*")) and FULL.search(s) and len(s) > 12:
            out.append(f"{p.name}:{i} {s[:80]}")
    return out


class TestP238Comments:
    def test_inventory_ratchet_be(self):
        got: list[str] = []
        for p in sorted(BE.rglob("*.py")):
            got += _assertive(p)
        assert len(got) == 116, (
            f"BE 全称注释数 {len(got)} != 116：新增/删除全称注释必须同步更新 docs/P2_10_ROUND10_AUDIT.md 附录"
        )

    def test_top_claims_supported(self):
        # 1) severe 只存在于注释（UserReportsPage:52-54 描述已修复的旧实现）
        t = (FE / "views/user/UserReportsPage.vue").read_text(encoding="utf-8")
        code_hits = [
            (i, l.strip()[:60])
            for i, l in enumerate(t.splitlines(), 1)
            if "severe" in l and not l.strip().startswith("*")
        ]
        assert code_hits == [], f"severe 重现于代码: {code_hits}"
        # 2) GdprTab AbortError 描述的是已被 HEAD 实现替换的旧实现
        t = (FE / "views/admin/components/admin-settings-page/GdprTab.vue").read_text(encoding="utf-8")
        assert "method: 'HEAD'" in t
        # 3) 请求失败 fallback 只存在于注释
        t = (FE / "api/request.ts").read_text(encoding="utf-8")
        code_hits = [
            (i, l.strip()[:60])
            for i, l in enumerate(t.splitlines(), 1)
            if "请求失败" in l and not l.strip().startswith("//")
        ]
        assert code_hits == [], f"请求失败 fallback 重现: {code_hits}"
        # 4) risk.py 部分唯一索引真实存在（"此前永远不会触发"已修复的证据）
        t = (BE / "models/risk.py").read_text(encoding="utf-8")
        assert re.search(r"sqlite_where\s*=\s*text\(\"is_latest = 1\"\)", t)
        assert re.search(r"postgresql_where\s*=\s*text\(\"is_latest\"\)", t)
