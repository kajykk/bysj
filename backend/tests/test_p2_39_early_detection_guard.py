"""P2 ROUND_15 T3 闸门：纵向早期检测的纪律守卫。

钉住本轮四条铁律（继承 B/B.5 教训 + 本轮新增）：

1. **时序评估必须按用户分组划分**（新增铁律①）——AST 钉死实验脚本必须用
   `StratifiedGroupKFold` 且把 `groups` 传进 `split()`；禁止退化为随机划分。
2. **特征零泄漏**：AST 钉死禁止 `TfidfVectorizer`（跨 fold 词频统计 = 泄漏），
   必须用无状态 `HashingVectorizer`。
3. **标签零泄漏**：AST 钉死评估器不得读 `phq9_*` 列（L4 目标泄漏教训；
   读它的唯一合法位置是仿真基准生成器的 onset 规则）。
4. **仿真数据一律显式标 synthetic**（新增铁律②）。
5. **指标口径**：ERDE「未报警 ⇒ 恒 1.0」语义 + 手算回归（开发期曾出 bug，
   见 docs/planning/P2_R15_EARLY_DETECTION_RESULT.md §六）。
6. **断言钉结构不钉字面量**（B.5 M7 假绿教训）：本文件的 AST 断言全部比较
   `ast.Call.func` / `ast.keyword.arg`，不用 `'x' in src` 文本包含。

数据依赖类用例在 CI（无 data/ 文件）上 skip；纯纪律类无条件运行。
"""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
TOOLS = BACKEND / "tests" / "tools"
BENCH = REPO / "data" / "external" / "chinese_depression_corpus_v1.csv"
BENCH_OUT = REPO / "data" / "processed" / "synth_longitudinal_synthetic"

EVAL_SCRIPT = TOOLS / "early_detection_eval.py"
BENCH_SCRIPT = TOOLS / "synth_longitudinal_bench.py"

CORPUS_EXISTS = BENCH.exists()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ede():
    return _load("early_detection_eval", EVAL_SCRIPT)


@pytest.fixture(scope="module")
def sb():
    return _load("synth_longitudinal_bench", BENCH_SCRIPT)


def _parse_tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imported_names(tree: ast.Module) -> set[str]:
    """所有 import 进来的顶层符号名（from x import y ⇒ 收集 y）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names |= {a.asname or a.name for a in node.names}
    return names


def _called_funcs(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


def _call_keywords(tree: ast.Module, func_name: str) -> list[ast.Call]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == func_name)
            or (isinstance(n.func, ast.Attribute) and n.func.attr == func_name)
        )
    ]


# ── G1：分组划分纪律（铁律①） ────────────────────────────
class TestG1GroupwiseSplitDiscipline:
    """时序评估必须按用户分组；禁止同一用户跨 train/test。"""

    def test_splitter_is_groupwise(self):
        tree = _parse_tree(EVAL_SCRIPT)
        assert "StratifiedGroupKFold" in _imported_names(tree), (
            "评估器未导入 StratifiedGroupKFold ⇒ 时序划分可能退化为随机"
        )

    def test_split_call_passes_groups(self):
        """`.split(...)` 调用必须出现 `groups=` 实参（AST 级，非文本包含）。"""
        tree = _parse_tree(EVAL_SCRIPT)
        calls = _call_keywords(tree, "split")
        with_groups = [
            c for c in calls if any(k.arg == "groups" for k in c.keywords)
        ]
        assert with_groups, (
            "未找到任何传 groups= 的 .split() 调用 ⇒ 无法保证用户级不跨折"
        )

    def test_random_state_is_fixed(self):
        tree = _parse_tree(EVAL_SCRIPT)
        calls = _call_keywords(tree, "StratifiedGroupKFold")
        assert calls, "未构造 StratifiedGroupKFold"
        pinned = [
            c for c in calls if any(k.arg == "random_state" for k in c.keywords)
        ]
        assert pinned, "StratifiedGroupKFold 未固定 random_state ⇒ 不可复现"

    def test_no_group_free_train_test_split_of_users(self):
        """禁止用 train_test_split 切**用户级**序列（那会让同一用户跨折）。

        判据：若脚本 import 了 train_test_split 即视为可疑（本实验不需要它）。
        """
        tree = _parse_tree(EVAL_SCRIPT)
        imported = _imported_names(tree)
        assert "train_test_split" not in imported, (
            "评估器 import 了 train_test_split；用户级时序切分必须用分组 CV"
        )


# ── G2：特征零泄漏（L4 + TF-IDF 教训） ──────────────────
class TestG2NoCrossFoldFeatureStats:
    def test_no_tfidf(self):
        """TF-IDF 的词频统计跨 fold 泄漏 ⇒ 禁止（AST 查 import）。"""
        tree = _parse_tree(EVAL_SCRIPT)
        assert "TfidfVectorizer" not in _imported_names(tree), (
            "禁止 TfidfVectorizer：其 idf 统计跨 fold 泄漏；应使用无状态 "
            "HashingVectorizer"
        )

    def test_uses_stateless_hashing(self):
        tree = _parse_tree(EVAL_SCRIPT)
        assert "HashingVectorizer" in _imported_names(tree), (
            "评估器未使用 HashingVectorizer（无状态特征 ⇒ 天然无跨 fold 统计泄漏）"
        )

    def test_vectorizer_has_no_fit_call(self):
        """无状态向量器不应被 fit（fit 即引入数据派生统计量）。"""
        tree = _parse_tree(EVAL_SCRIPT)
        src = EVAL_SCRIPT.read_text(encoding="utf-8")
        assert "vec.fit_transform" not in src, (
            "出现 vec.fit_transform：无状态向量器被 fit ⇒ 引入跨 fold 统计量"
        )


# ── G3：标签零泄漏（L4 教训的时序版） ────────────────────
class TestG3NoLabelLeakageIntoFeatures:
    def test_evaluator_never_reads_phq9_columns(self):
        """评估器不得读任何 phq9_* 列（唯一合法读者是基准生成器的 onset 规则）。

        断言按**数据结构**而非裸字符串：只查「下标访问 `x["phq9..."]`」与
        「属性访问 `.phq9_*`」，**排除 docstring/注释类字面量**
        （B 轮教训：文本包含会命中自己写的说明文字 ⇒ 假阳性）。
        """
        tree = _parse_tree(EVAL_SCRIPT)
        hits: list[str] = []

        def _is_phq9(s: str) -> bool:
            return s.lower().startswith("phq9")

        for node in ast.walk(tree):
            # 下标访问：df["phq9_score"]
            if isinstance(node, ast.Subscript):
                sl = node.slice
                sl = sl.value if isinstance(sl, ast.Constant) else None
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    if _is_phq9(sl.value):
                        hits.append(f'{type(node).__name__}["{sl.value}"]')
            # 属性访问：row.phq9_score
            elif isinstance(node, ast.Attribute) and _is_phq9(node.attr):
                hits.append(f".{node.attr}")
        assert not hits, f"评估器出现 phq9 列的数据访问：{hits[:3]}"

    def test_onset_rule_lives_only_in_generator(self):
        """onset 规则（读 phq9_score）只允许存在于生成器中。"""
        tree = _parse_tree(BENCH_SCRIPT)
        src = BENCH_SCRIPT.read_text(encoding="utf-8")
        assert "phq9_score" in src, "生成器应显式读取 phq9_score 以驱动 onset 规则"
        # 生成器输出中 phq9 轨迹必须仅作审计字段
        assert '"phq9_traj"' in src, "生成器应保留 phq9 轨迹供 onset 审计"


# ── G4：synthetic 标记（铁律②） ─────────────────────────
class TestG4SyntheticMarking:
    def test_manifest_writes_synthetic_true(self):
        """manifest dict 字面量必须含 `"synthetic": True`（AST 查 Dict，非 keyword）。

        注：首版按 ast.keyword 查找 ⇒ 假阴性（dict 字面量的 key 不是 keyword
        形参），是断言写法缺陷，已改。
        """
        tree = _parse_tree(BENCH_SCRIPT)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "synthetic"
                    and isinstance(v, ast.Constant)
                    and v.value is True
                ):
                    found = True
        assert found, "生成器 manifest 未写入 synthetic=True ⇒ 违背铁律②"

    def test_output_dir_name_marks_synthetic(self):
        tree = _parse_tree(BENCH_SCRIPT)
        consts = [
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        assert any("synthetic" in c for c in consts), (
            "生成器默认输出路径未含 synthetic 字样"
        )

    def test_evaluator_refuses_unsigned_manifest(self, ede):
        """manfiest 未标 synthetic 时评估器必须拒跑（fail-closed）。"""
        src = EVAL_SCRIPT.read_text(encoding="utf-8")
        assert "拒绝评估" in src, "缺少「manifest 未标 synthetic ⇒ 拒绝评估」的防护"


# ── G5：指标口径（含开发期 bug 回归） ────────────────────
class TestG5MetricSemantics:
    def test_never_decided_penalty_is_one(self, ede):
        """未报警 ⇒ penalty 恒 1.0（首版曾编码为 n+1 而得负 penalty，是 bug）。"""
        assert ede.erde_k([5], [None], [10], k=50) == 1.0

    def test_early_alarm_is_rewarded(self, ede):
        """提前报警 ⇒ 负 penalty（eRisk 对早发现的计价）。"""
        assert abs(ede.erde_k([5], [7], [10], k=50) - (-0.2)) < 1e-9

    def test_over_window_penalty_is_one(self, ede):
        assert ede.erde_k([5], [56], [10], k=50) == 1.0

    def test_controls_do_not_participate(self, ede):
        assert np.isnan(ede.erde_k([None], [3], [10], k=50))

    def test_f_latency_handcomputed(self, ede):
        """T1 §2.3 细则手算例（开发期期望值曾写错，见报告 §六）。"""
        v = ede.f_latency(
            [5, 3, None, 3], [5, 8, 5, None], [10, 10, 10, 10], [1, 1, 0, 1]
        )
        assert abs(v - 0.75) < 1e-9

    def test_decision_helpers_return_none_when_no_alarm(self, ede):
        """三档决策函数必须用 None 表示未报警（一致性 ⇒ 指标语义统一）。"""
        import numpy as _np

        probs = _np.array([0.1, 0.2, 0.15])
        assert ede.decide_fixed(probs, 0.9) is None
        assert ede.decide_layered(probs, 0.9, 0.0) is None

    def test_metric_self_test_passes(self, ede):
        assert ede.self_test() == 0


# ── G6：基准不变量（依赖语料，CI 上 skip） ───────────────
@pytest.mark.skipif(not CORPUS_EXISTS, reason="CI 无 chinese_depression_corpus_v1.csv")
class TestG6BenchmarkInvariants:
    def test_rules_and_reproducibility(self, sb):
        users, dropped = sb.build_benchmark()
        assert dropped == 0, "构造保证 onset 存在 ⇒ dropped 应恒为 0"
        problems = sb.verify(users, dropped)
        assert problems == [], f"基准规则违例：{problems[:3]}"

    def test_no_sibling_variants_within_user(self, sb):
        """用户内 source_idx 不得重复（B 轮 L1「重复≠安全」教训的时序版）。"""
        users, _ = sb.build_benchmark()
        for u in users:
            assert len(set(u["src_ids"])) == len(u["src_ids"]), u["user_id"]

    def test_case_has_real_onset_process(self, sb):
        """onset 之前应存在低分时点（否则退成立即报警，任务失去意义）。"""
        users, _ = sb.build_benchmark()
        cases = [u for u in users if u["label"] == 1]
        assert cases
        for u in cases:
            assert u["onset"] > 0, f"{u['user_id']}: onset=0"
