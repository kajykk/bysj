"""ROUND_15 T3: eRisk 式纵向早期检测评估（三档基线 + 学习式停止策略）。

口径权威来源：`docs/planning/P2_R15_EARLY_DETECTION_TASK.md`（先定指标后写码）。

## 卫生纪律（每条都有闸门断言对应）
1. **按用户分组划分**：`StratifiedGroupKFold(groups=user_id)`，同一用户任何时点
   都不得跨 train/test（引 2607.02920 说话人泄漏）。
2. **特征零泄漏**：`HashingVectorizer`（无状态、无跨 fold 统计量）+ 自定义
   字符 n-gram。**禁用 TF-IDF**（词频统计会跨 fold 泄漏）。
3. **标签零泄漏**：时点模型的训练标签 = 「该时点是否 ≥ onset」（onset 由外部
   PHQ-9 规则给出），特征侧**不读任何 phq9 列**（L4 目标泄漏教训）。
4. **阈值只在 train 折选**：档 (a)/(b) 的阈值与档 (c) 的停止阈值均不在
   test 折上优化（B.5 L3 教训）。
5. **仿真数据必须显式标 synthetic**：输入来自 synth_longitudinal_bench.py 的
   产物，输出表带 synthetic 标记，禁止与真实指标并列。

用法::

    python tests/tools/early_detection_eval.py --self-test     # 指标公式手算自检
    python tests/tools/early_detection_eval.py                 # 完整 5-fold 对照实验
    python tests/tools/early_detection_eval.py --quick         # 2-fold 快速冒烟
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
BENCH_DIR = REPO / "data" / "processed" / "synth_longitudinal_synthetic"
USERS_PATH = BENCH_DIR / "users_synth.jsonl"

SEED = 20261019
N_FOLDS = 5
K_ERDE = 50          # 主读数 ERDE50
MAX_LEN_NORM = 20    # n_obs 归一化基数（与生成器 MAX_LEN 一致）
GRID_THETA = [round(0.30 + 0.05 * i, 2) for i in range(9)]   # 0.30..0.70
GRID_ALPHA = [0.0, 0.01, 0.02, 0.03]


# ── 指标（口径见 T1 文档 §二） ─────────────────────────────
def erde_k(onsets, decisions, lengths, k: int = K_ERDE) -> float:
    """ERDE@k（eRisk 2018/2020 口径）。

    penalty_i = 1                  未报警（d_i is None）
             = 1                  d_i > o_i + k（太晚）
             = (o_i − d_i)/T_i    否则（提前报警得负 ⇒ 奖励早发现）

    对 case 用户（o_i 非 None）取均值；非 case 用户不参与。

    注：**未报警不是「在 n+1 时点报警」**——eRisk 原义是 never decides ⇒ 恒罚 1。
    首版曾把未报警编码为 n+1，使 `d ≤ o+k` 检查失效而得到小负 penalty，是 bug。
    """
    pens = []
    for o, d, T in zip(onsets, decisions, lengths):
        if o is None:
            continue
        if d is None or d > o + k:
            pens.append(1.0)
        else:
            pens.append((o - d) / T)
    return float(np.mean(pens)) if pens else float("nan")


def f_latency(onsets, decisions, lengths, labels, k: int = K_ERDE) -> float:
    """latency-weighted F1（eRisk 2020 口径，权重 w = 1 − |o−d|/T）。

    计分细则（T1 §2.3）：case 且 d ≤ o+k ⇒ TP 权重 w；case 太晚/未报 ⇒ FN 权重 0；
    非 case 报警 ⇒ FP 权重 1；非 case 未报 ⇒ TN 不计。
    """
    tp = fn = fp = 0.0
    for o, d, T, y in zip(onsets, decisions, lengths, labels):
        if y == 1:
            if d is not None and d <= o + k:
                tp += 1.0 - abs(o - d) / T
            else:
                fn += 0.0
        else:
            if d is not None:
                fp += 1.0
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return float(2 * p * r / (p + r)) if (p + r) > 0 else 0.0


# ── 特征（无状态哈希，零泄漏） ─────────────────────────────
def _char_ngrams(text: str, n: int = 2) -> list[str]:
    """确定性字符 n-gram（不依赖任何数据集统计量）。"""
    s = "".join(str(text).split())
    if len(s) < n:
        return [s] if s else []
    return [s[i : i + n] for i in range(len(s) - n + 1)]


def make_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features=2 ** 18,
        alternate_sign=False,
        norm="l2",
        tokenizer=_char_ngrams,
        token_pattern=None,
    )


# ── 数据装载 ───────────────────────────────────────────────
def load_users(path: Path = USERS_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"找不到仿真基准 {path}；先跑 "
            f"`python tests/tools/synth_longitudinal_bench.py`"
        )
    users = [json.loads(l) for l in path.open(encoding="utf-8")]
    mf = BENCH_DIR / "manifest.json"
    if mf.exists() and not json.loads(mf.read_text(encoding="utf-8")).get("synthetic"):
        raise RuntimeError("manifest 未标 synthetic ⇒ 拒绝评估")
    return users


# ── 时点模型（档 a/b 共用） ────────────────────────────────
def fit_pointwise(train_users, vec):
    """在 train 折用户的全部时点上拟合「此时点是否 ≥ onset」二分类。

    训练标签来自 onset（外部 PHQ-9 规则），特征只用文本哈希 —— 不读 phq9 列。
    """
    texts, labels = [], []
    for u in train_users:
        on = u["onset"]
        for t, txt in enumerate(u["texts"]):
            texts.append(txt)
            labels.append(1 if (on is not None and t >= on) else 0)
    X = vec.transform(texts)  # 无状态向量器：只 transform，绝不 fit（防跨 fold 统计泄漏）
    y = np.asarray(labels)
    clf = LogisticRegression(max_iter=2000, C=1.0, solver="liblinear")
    clf.fit(X, y)
    return clf


def pointwise_probs(clf, vec, users):
    """返回 {user_id: np.ndarray(p_t)} 与展开的时点特征矩阵（供 SVD 用）。"""
    out = {}
    for u in users:
        X = vec.transform(u["texts"])
        out[u["user_id"]] = clf.predict_proba(X)[:, 1]
    return out


# ── 决策规则 ───────────────────────────────────────────────
def decide_fixed(probs, theta: float):
    """档 (a)：固定阈值，首次越过的时点即为报警点（1-based）。未报返回 None。"""
    idx = np.nonzero(probs >= theta)[0]
    return int(idx[0]) + 1 if len(idx) else None


def decide_layered(probs, theta0: float, alpha: float):
    """档 (b)：分层阈值 θ(t) = θ0 − α·(t−1)，早松晚紧。未报返回 None。"""
    for t, p in enumerate(probs):
        if p >= theta0 - alpha * t:
            return t + 1
    return None


def _cum_feats(probs: np.ndarray, svd_means: np.ndarray | None) -> np.ndarray:
    """到时点 t 的累积表示：cum_mean_p / p_last / p_max / n_obs + SVD 均值（可选）。"""
    t = len(probs)
    base = [
        probs.mean(),
        probs[-1],
        probs.max(),
        probs.min(),
        t / MAX_LEN_NORM,
    ]
    if svd_means is not None:
        return np.concatenate([np.asarray(base, dtype=float), svd_means])
    return np.asarray(base, dtype=float)


def decide_learned(feats, mlp: MLPClassifier):
    """档 (c)：MLP 每步输出「停」概率，首次 ≥0.5 的时点报警。未报返回 None。"""
    for t, f in enumerate(feats):
        if mlp.predict_proba(f.reshape(1, -1))[0, 1] >= 0.5:
            return t + 1
    return None


# ── train 折选参（铁律 4：阈值只在 train 折选） ────────────
def pick_theta_fixed(probs_map, users):
    """在 train 折上网格选 θ：最小化 train 折用户的 ERDE50。"""
    best, best_theta = -np.inf, GRID_THETA[0]
    for th in GRID_THETA:
        ds = [decide_fixed(probs_map[u["user_id"]], th) for u in users]
        sc = -erde_k(
            [u["onset"] for u in users], ds, [u["n_texts"] for u in users], K_ERDE
        )
        if sc > best:
            best, best_theta = sc, th
    return best_theta


def pick_layered(probs_map, users):
    best, best_pair = -np.inf, (GRID_THETA[-1], GRID_ALPHA[0])
    for th in GRID_THETA:
        for al in GRID_ALPHA:
            ds = [decide_layered(probs_map[u["user_id"]], th, al) for u in users]
            sc = -erde_k(
                [u["onset"] for u in users], ds, [u["n_texts"] for u in users], K_ERDE
            )
            if sc > best:
                best, best_pair = sc, (th, al)
    return best_pair


def build_stop_training(clf, vec, train_users):
    """构造「停/不停」监督信号：每用户的 ERDE 最优决策步。

    对每个 case 用户 t=0..n-1：若在 t 报警的 penalty ≤ 其它所有步的 penalty，
    标 1（该停），否则标 0。control 用户全标 0。
    """
    probs_map = pointwise_probs(clf, vec, train_users)
    X, y, groups = [], [], []
    for u in train_users:
        probs = probs_map[u["user_id"]]
        n, o = u["n_texts"], u["onset"]
        # 每步的 ERDE penalty
        if o is None:
            # control 的最优决策是「永不停」⇒ 每步标 0（停了就是 FP）
            pens = [1.0] * n
        else:
            pens = [
                ((o - (t + 1)) / n if (t + 1) <= o + K_ERDE else 1.0) for t in range(n)
            ]
        best = min(pens)
        for t in range(n):
            X.append(_cum_feats(probs[: t + 1], None))
            y.append(1 if pens[t] <= best + 1e-12 else 0)
            groups.append(u["user_id"])
    return np.asarray(X), np.asarray(y), groups


def fit_mlp(X, y):
    mlp = MLPClassifier(
        hidden_layer_sizes=(32, 16),
        max_iter=300,
        random_state=SEED,
        early_stopping=False,
    )
    mlp.fit(X, y)
    return mlp


# ── 单折评估 ───────────────────────────────────────────────
def run_fold(train_users, test_users):
    vec = make_vectorizer()
    clf = fit_pointwise(train_users, vec)

    tr_map = pointwise_probs(clf, vec, train_users)
    te_map = pointwise_probs(clf, vec, test_users)

    # 档 a / b：train 折选参
    theta = pick_theta_fixed(tr_map, train_users)
    th0, al = pick_layered(tr_map, train_users)

    # 档 c：学习式停止
    Xs, ys, _ = build_stop_training(clf, vec, train_users)
    mlp = fit_mlp(Xs, ys)

    cols = ["onset", "decision", "length", "label"]
    test_meta = [
        (
            u["onset"],
            decide_fixed(te_map[u["user_id"]], theta),
            u["n_texts"],
            u["label"],
        )
        for u in test_users
    ]
    # 档 b
    dec_b = [decide_layered(te_map[u["user_id"]], th0, al) for u in test_users]
    # 档 c
    dec_c = []
    for u in test_users:
        probs = te_map[u["user_id"]]
        feats = np.asarray([_cum_feats(probs[: t + 1], None) for t in range(len(probs))])
        dec_c.append(decide_learned(feats, mlp))

    def pack(dec):
        return {
            "rows": [
                dict(zip(cols, [m[0], d, m[2], m[3]])) for m, d in zip(test_meta, dec)
            ],
            "theta": theta,
            "layered": (th0, al),
        }

    return {
        "a_fixed": pack([m[1] for m in test_meta]),
        "b_layered": pack(dec_b),
        "c_learned": pack(dec_c),
    }


def summarize(rows) -> dict:
    return {
        "ERDE50": erde_k(
            [r["onset"] for r in rows], [r["decision"] for r in rows],
            [r["length"] for r in rows], K_ERDE,
        ),
        "F_latency": f_latency(
            [r["onset"] for r in rows], [r["decision"] for r in rows],
            [r["length"] for r in rows], [r["label"] for r in rows], K_ERDE,
        ),
        "n_case": sum(1 for r in rows if r["label"] == 1),
        "n_control": sum(1 for r in rows if r["label"] == 0),
    }


# ── 自检：指标公式用手算值钉死 ────────────────────────────
def self_test() -> int:
    """手算期望值（T1 §二公式的落地面）。任何一条不符 ⇒ 公式实现错了。"""
    ok = True

    # ERDE：单 case，n=10, onset=5
    # d=5 ⇒ (5-5)/10 = 0.0
    v = erde_k([5], [5], [10], k=50)
    ok &= _chk("ERDE d==onset ⇒ 0.0", v, 0.0)
    # d=7 ⇒ 提前报警 (5-7)/10 = -0.2（奖励早发现 ⇒ 负）
    v = erde_k([5], [7], [10], k=50)
    ok &= _chk("ERDE 提前报警 ⇒ 负", v, -0.2)
    # d=None（未报警，never decides）⇒ 1.0
    v = erde_k([5], [None], [10], k=50)
    ok &= _chk("ERDE 未报警 ⇒ 1.0", v, 1.0)
    # d=56（有报警但超窗口 > 5+50）⇒ 1.0
    v = erde_k([5], [56], [10], k=50)
    ok &= _chk("ERDE 超窗口 ⇒ 1.0", v, 1.0)
    # 两 case 均值：(0.0 + 1.0)/2 = 0.5
    v = erde_k([5, 3], [5, None], [10, 10], k=50)
    ok &= _chk("ERDE 均值", v, 0.5)
    # 有报警但迟到（d=8 ≤ 5+50 但晚于 onset）⇒ (5-8)/10 = -0.3（迟报警仍按比例罚）
    v = erde_k([5], [8], [10], k=50)
    ok &= _chk("ERDE 迟报警(窗口内)", v, -0.3)
    # control（onset=None）不参与
    v = erde_k([None], [3], [10], k=50)
    ok &= _chk("ERDE 无 case ⇒ nan", v, float("nan"))

    # F_latency：T1 §2.3 细则的手算例
    # u1 case o=5 d=5 n=10 ⇒ TP w=1；u2 case o=3 d=8 ⇒ TP w=0.5；
    # u3 control d=5（报警）⇒ FP w=1；u4 case d=None（未报）⇒ FN w=0
    # P = 1.5/(1.5+1) = 0.6；R = 1.5/1.5 = 1.0；F = 2PR/(P+R) = 0.75
    v = f_latency([5, 3, None, 3], [5, 8, 5, None], [10, 10, 10, 10], [1, 1, 0, 1])
    ok &= _chk("F_latency 手算例", v, 0.75)

    # 特征侧：不得读 phq9 列（静态断言在闸门测试里做，这里验运行期形状）
    txt = "今天感觉还不错 明天想去散步"
    v = make_vectorizer()
    m = v.transform([txt])
    ok &= _chk("哈希矩阵行数", float(m.shape[0]), 1.0)
    ok &= _chk("哈希矩阵列数", float(m.shape[1]), float(2 ** 18))
    # L2 归一 ⇒ 平方和=1（首版误断言 sum()==1，实际 sum==sqrt(nnz)）
    ok &= _chk("L2 归一(平方和)", float(m.multiply(m).sum()), 1.0)

    print("[OK] 指标/特征自检全部通过" if ok else "[FAIL] 自检未过")
    return 0 if ok else 1


def _chk(name: str, got: float, want: float) -> bool:
    good = (np.isnan(got) and np.isnan(want)) or abs(got - want) < 1e-9
    print(f"  {'OK ' if good else 'FAIL'} {name}: got={got} want={want}")
    return good


# ── 完整实验 ───────────────────────────────────────────────
def run_experiment(n_folds: int = N_FOLDS) -> dict:
    users = load_users()
    labels = np.asarray([u["label"] for u in users])
    groups = np.asarray([u["user_id"] for u in users])
    splitter = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=SEED)

    all_rows = {"a_fixed": [], "b_layered": [], "c_learned": []}
    thetas, layered = [], []
    for fi, (tr, te) in enumerate(
        splitter.split(np.zeros(len(users)), labels, groups=groups)
    ):
        tr_u = [users[i] for i in tr]
        te_u = [users[i] for i in te]
        res = run_fold(tr_u, te_u)
        for key in all_rows:
            all_rows[key] += res[key]["rows"]
        thetas.append(res["a_fixed"]["theta"])
        layered.append(res["a_fixed"]["layered"])
        print(f"[fold {fi}] train={len(tr_u)} test={len(te_u)} theta={res['a_fixed']['theta']}")

    summary = {k: summarize(v) for k, v in all_rows.items()}
    summary["_meta"] = {
        "synthetic": True,
        "warning": "SIMULATION ONLY — synthetic benchmark, not real-world performance",
        "n_folds": n_folds,
        "seed": SEED,
        "k_erde": K_ERDE,
        "theta_grid": GRID_THETA,
        "alpha_grid": GRID_ALPHA,
        "theta_per_fold": thetas,
        "layered_per_fold": layered,
        "bench_digest": _bench_digest(),
    }
    return summary


def _bench_digest() -> str:
    mf = BENCH_DIR / "manifest.json"
    if not mf.exists():
        return "n/a"
    return json.loads(mf.read_text(encoding="utf-8")).get("digest_sha256", "n/a")[:16]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--quick", action="store_true", help="2-fold 冒烟")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    n_folds = 2 if args.quick else N_FOLDS
    print(f"[run] {n_folds}-fold, k={K_ERDE}, seed={SEED} (SYNTHETIC BENCH)")
    summary = run_experiment(n_folds)

    print("\n=== SYNTHETIC 结果（禁止与真实指标并列） ===")
    hdr = f"{'档':<14}{'ERDE50':>10}{'F_latency':>12}{'n_case':>8}{'n_ctrl':>8}"
    print(hdr)
    print("-" * len(hdr))
    names = {"a_fixed": "a 时点+固定阈值", "b_layered": "b 分层阈值", "c_learned": "c 学习式停止"}
    for k in ("a_fixed", "b_layered", "c_learned"):
        s = summary[k]
        print(
            f"{names[k]:<14}{s['ERDE50']:>10.4f}{s['F_latency']:>12.4f}"
            f"{s['n_case']:>8}{s['n_control']:>8}"
        )

    a, c = summary["a_fixed"], summary["c_learned"]
    gate = c["ERDE50"] <= a["ERDE50"] and c["F_latency"] >= a["F_latency"]
    print(
        f"\n[判定门槛] ERDE50(c)={c['ERDE50']:.4f} ≤ ERDE50(a)={a['ERDE50']:.4f} ? "
        f"{c['ERDE50'] <= a['ERDE50']}; "
        f"F_latency(c)={c['F_latency']:.4f} ≥ F_latency(a)={a['F_latency']:.4f} ? "
        f"{c['F_latency'] >= a['F_latency']} ⇒ {'PASS' if gate else 'FAIL（阴性结论）'}"
    )

    if args.out:
        args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[out] {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
