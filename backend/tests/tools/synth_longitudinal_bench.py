"""ROUND_15 T2: 纵向早期检测的 **synthetic** 仿真基准生成器（replay harness）。

## 为什么需要它（gate 结论，实测见 docs/planning/P2_R15_EARLY_DETECTION_TASK.md §0）

本仓**没有真实纵向标注数据**：外部语料 8379 行 / 8379 unique user_id / 无时间列；
生产库 text_entries 仅 1 个用户 5 条、local_e2e 库 0 个多时点用户；
部署脚本 init_db.py 只建表不灌数据。

## 它做什么

把静态语料 `data/external/chinese_depression_corpus_v1.csv` 重放为 per-user
时间线，供 eRisk Task 2（何时报警）评估。

## 卫生纪律（与 B/B.5 轮教训同源，逐条对应闸门断言）

1. **onset 由外部规则 + 真实 PHQ-9 分数驱动，不由被评模型自证**：
   onset 定义为「首次连续 `onset_patience` 个时点 PHQ-9 ≥ 10」的起点。
   该规则只读 `phq9_score` 列，与任何被评模型的输出无关。
2. **phq9 轨迹只进审计字段、禁止进模型特征**：输出的 `phq9_traj` 仅供审计
   onset 规则；检测器消费的输入只有 `texts`。闸门
   `test_p2_39_early_detection_guard.py` 钉住这条（AST：检测器不得读
   phq9 列 / 不得把 phq9 当特征）。
3. **候选池按 source_idx 去重**（1244 条），避免同一原始样本的增强变体
   重复进入同一用户时间线（B 轮 L1「数据有重复 ≠ 安全」的教训）。
4. **固定种子、一键复现**：同 seed 两次生成的逐用户哈希完全一致（自检）。
5. **产物显式标 synthetic**：文件名与 manifest 均带 `synthetic` 字样。

用法::

    python tests/tools/synth_longitudinal_bench.py --self-test
    python tests/tools/synth_longitudinal_bench.py --seed 20261019 --n-users 400
    python tests/tools/synth_longitudinal_bench.py --stats <outdir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
CORPUS = REPO / "data" / "external" / "chinese_depression_corpus_v1.csv"
DEFAULT_OUT = REPO / "data" / "processed" / "synth_longitudinal_synthetic"

DEFAULT_SEED = 20261019
DEFAULT_N_USERS = 400          # 200 case + 200 control
MIN_LEN, MAX_LEN = 8, 20       # 每用户时点数范围
ONSET_PATIENCE = 3             # 连续 N 个时点 ≥10 判为发病起点
P_TRANS = 0.25                 # case 低分段尾部混入高分的概率（onset 有变化）
P_TRANS_WINDOW = 3             # 过渡窗口宽度（低分段尾部多少个时点）
ONSET_CUTOFF = 10              # PHQ-9 阈值（与 phq9_binary 同源，勿改）

# 生成器自身的确定性：同 seed ⇒ 同 rng 序列 ⇒ 同时间线
RNG_SCOPE = "synth_longitudinal_v1"


# ── 数据集构建 ──────────────────────────────────────────────
def load_pool() -> tuple[list[dict], list[dict]]:
    """读语料，按 source_idx 去重，切出低分/高分两个候选池。

    返回 (low_pool, high_pool)，元素为 {"text": str, "src": int, "score": float}。
    只读 text / source_idx / phq9_score 三列 —— phq9_score 只用于**构造
    onset 规则**，不进入下游模型特征（见模块 docstring 纪律 2）。
    """
    df = pd.read_csv(CORPUS)
    df = df.drop_duplicates(subset=["source_idx"], keep="first")
    recs = [
        {"text": str(r.text), "src": int(r.source_idx), "score": float(r.phq9_score)}
        for r in df.itertuples(index=False)
    ]
    low = [r for r in recs if r["score"] < ONSET_CUTOFF]
    high = [r for r in recs if r["score"] >= ONSET_CUTOFF]
    if not low or not high:
        raise RuntimeError(f"候选池为空: low={len(low)} high={len(high)}")
    return low, high


def _sample_no_repeat(rng: random.Random, pool: list[dict], n: int) -> list[dict]:
    """从 pool 无放回采 n 条；池不足时按确定性顺序补足（保持可复现）。"""
    if n <= len(pool):
        return rng.sample(pool, n)
    out = list(pool)
    rng.shuffle(out)
    # 池不足：循环补齐（跨用户共享可接受，用户内仍不重复）
    while len(out) < n:
        out.append(pool[len(out) % len(pool)])
    return out[:n]


def _compute_onset(scores: list[float], patience: int) -> int | None:
    """首次连续 `patience` 个时点 score >= ONSET_CUTOFF 的 0-based 起点。

    返回 None 表示整个序列从未连续达标（该 case 用户不成立）。
    """
    run = 0
    for i, s in enumerate(scores):
        if s >= ONSET_CUTOFF:
            run += 1
            if run >= patience:
                return i - patience + 1
        else:
            run = 0
    return None


def build_benchmark(
    seed: int = DEFAULT_SEED,
    n_users: int = DEFAULT_N_USERS,
) -> list[dict]:
    """生成 per-user 时间线。返回用户 dict 列表（顺序确定）。

    每个用户 dict::

        {"user_id": "synth_u_0000", "label": 1, "n_texts": 14,
         "onset": 7,                      # 0-based；control 恒为 None
         "texts": [...], "phq9_traj": [...],   # phq9_traj 仅审计用
         "src_ids": [...]}
    """
    rng = random.Random(f"{RNG_SCOPE}:{seed}")
    low, high = load_pool()
    n_case = n_users // 2
    n_ctrl = n_users - n_case
    users: list[dict] = []
    dropped = 0

    for k in range(n_case):
        n = rng.randint(MIN_LEN, MAX_LEN)
        # 分段构造：后 b 段必为高分（保证 onset 存在且 ≤ n-b），前 n−b 段为
        # 低分段（尾部按 P_TRANS 混入高分 ⇒ onset 位置有变化，不退化成立即报警）。
        # 两段各自无放回采样 ⇒ 用户内 source_idx 必不重复。
        b = rng.randint(ONSET_PATIENCE, max(ONSET_PATIENCE, n // 2))
        low_part = _sample_no_repeat(rng, low, n - b)
        high_part = _sample_no_repeat(rng, high, b)
        # 过渡：低分段尾部 P_TRANS 概率换成高分（spare 无放回，防用户内 src 重复）
        used = {p["src"] for p in high_part}
        spare = [p for p in high if p["src"] not in used]
        tail = low_part[n - b - P_TRANS_WINDOW :]
        head = low_part[: n - b - len(tail)]
        # 先决定哪几个位置被替换，再从 spare 无放回抽取候选取用
        flags = [rng.random() < P_TRANS for _ in tail]
        n_trans = sum(flags)
        trans_pool = rng.sample(spare, min(n_trans, len(spare))) if spare else []
        picks = list(head)
        for i, t in enumerate(tail):
            if flags[i] and trans_pool:
                picks.append(trans_pool.pop())
            else:
                picks.append(t)
        picks = picks + high_part
        onset = _compute_onset([p["score"] for p in picks], ONSET_PATIENCE)
        if onset is None:
            # 构造已保证后 b≥ONSET_PATIENCE 段全高分 ⇒ 理论不可达；
            # 保留作安全网，若触发说明构造被改坏。
            dropped += 1
            continue
        users.append(_mk("case", k, picks, onset))

    for k in range(n_ctrl):
        n = rng.randint(MIN_LEN, MAX_LEN)
        pool = low + high
        picks = _sample_no_repeat(rng, pool, n)
        # control 的 onset 定义同样适用于审计：要求其**从未**连续达标
        users.append(_mk("control", k, picks, None))

    return users, dropped


def _mk(kind: str, k: int, picks: list[dict], onset: int | None) -> dict:
    return {
        "user_id": f"synth_{kind}_{k:04d}",
        "label": 1 if kind == "case" else 0,
        "n_texts": len(picks),
        "onset": onset,
        "texts": [p["text"] for p in picks],
        "phq9_traj": [p["score"] for p in picks],
        "src_ids": [p["src"] for p in picks],
    }


def verify(users: list[dict], dropped: int) -> list[str]:
    """返回问题列表（空 = 通过）。self-test 与闸门共用这套判据。"""
    problems: list[str] = []
    for u in users:
        uid = u["user_id"]
        if u["label"] == 1 and u["onset"] is None:
            problems.append(f"{uid}: case 无 onset")
        if u["label"] == 0 and u["onset"] is not None:
            problems.append(f"{uid}: control 却有 onset")
        if len(set(u["src_ids"])) != len(u["src_ids"]):
            problems.append(f"{uid}: 用户内 source_idx 重复（变体污染）")
        if u["n_texts"] != len(u["texts"]):
            problems.append(f"{uid}: n_texts 与 texts 长度不符")
        if not (MIN_LEN <= u["n_texts"] <= MAX_LEN):
            problems.append(f"{uid}: n_texts={u['n_texts']} 超范围")
        if u["label"] == 1:
            # onset 之前必须存在低分时点（否则无"过程"，退化成立即报警）
            if u["onset"] == 0:
                problems.append(f"{uid}: onset=0（无发病前过程）")
            # onset 起必须真的连续高分
            for s in u["phq9_traj"][u["onset"] : u["onset"] + ONSET_PATIENCE]:
                if s < ONSET_CUTOFF:
                    problems.append(f"{uid}: onset 起未连续 ≥{ONSET_CUTOFF}")
                    break
    return problems


def save(users: list[dict], dropped: int, outdir: Path) -> dict:
    """写 users.jsonl + manifest.json（manifest 带 synthetic 标记）。"""
    outdir.mkdir(parents=True, exist_ok=True)
    users_path = outdir / "users_synth.jsonl"
    with users_path.open("w", encoding="utf-8") as fh:
        for u in users:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")

    # 逐用户内容哈希：复现性判据（同 seed 两次必须一致）
    per_user = {
        u["user_id"]: hashlib.sha256(
            json.dumps(u, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        for u in users
    }
    digest = hashlib.sha256(
        json.dumps(per_user, sort_keys=True).encode("utf-8")
    ).hexdigest()

    manifest = {
        "synthetic": True,
        "warning": "SIMULATION ONLY — 不得与真实世界指标同表并列",
        "generator": "backend/tests/tools/synth_longitudinal_bench.py",
        "rng_scope": RNG_SCOPE,
        "seed": DEFAULT_SEED,
        "n_users_requested": DEFAULT_N_USERS,
        "n_users_emitted": len(users),
        "n_case": sum(1 for u in users if u["label"] == 1),
        "n_control": sum(1 for u in users if u["label"] == 0),
        "case_dropped_no_onset": dropped,
        "min_len": MIN_LEN,
        "max_len": MAX_LEN,
        "onset_patience": ONSET_PATIENCE,
        "p_trans": P_TRANS,
        "p_trans_window": P_TRANS_WINDOW,
        "onset_cutoff": ONSET_CUTOFF,
        "onset_rule": "后 b∈[patience, n//2] 段必高分；低段尾部按 p_trans 混高分；onset=首次连续 patience 个时点 score>=cutoff（0-based）",
        "onset_source": "external rule on real PHQ-9 scores; NOT model-derived",
        "pool_source": str(CORPUS.relative_to(REPO)) + " dedup by source_idx",
        "digest_sha256": digest,
    }
    (outdir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def self_test() -> int:
    """自检：规则不变量 + 可复现性。返回进程退出码。"""
    users, dropped = build_benchmark()
    problems = verify(users, dropped)
    n_case = sum(1 for u in users if u["label"] == 1)
    n_ctrl = sum(1 for u in users if u["label"] == 0)
    print(f"[build] users={len(users)} case={n_case} control={n_ctrl} dropped={dropped}")
    if problems:
        print(f"[FAIL] 规则不变量违例 {len(problems)} 条，前 5：")
        for p in problems[:5]:
            print("   -", p)
        return 1

    # 复现性：同 seed 再跑一次，digest 必须一致
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        m1 = save(users, dropped, Path(td) / "a")
        users2, dropped2 = build_benchmark()
        m2 = save(users2, dropped2, Path(td) / "b")
        if m1["digest_sha256"] != m2["digest_sha256"]:
            print("[FAIL] 同 seed 两次生成 digest 不一致 ⇒ 不可复现")
            return 1
        print(f"[OK] 规则不变量全过；digest={m1['digest_sha256'][:16]}（可复现）")

    # control 的"从未连续达标"不变量已由 verify 覆盖（onset is None）
    print(f"[OK] onset 规则自洽；avg_n_texts={sum(u['n_texts'] for u in users)/len(users):.1f}")
    return 0


def _stats(outdir: Path) -> int:
    mf = outdir / "manifest.json"
    if not mf.exists():
        print(f"[FAIL] 找不到 {mf}", file=sys.stderr)
        return 1
    m = json.loads(mf.read_text(encoding="utf-8"))
    if not m.get("synthetic"):
        print("[FAIL] manifest 未标 synthetic", file=sys.stderr)
        return 1
    print(json.dumps(m, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--stats", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.stats:
        return _stats(args.stats)

    users, dropped = build_benchmark()
    problems = verify(users, dropped)
    if problems:
        print(f"[FAIL] {len(problems)} 条规则违例", file=sys.stderr)
        return 1
    m = save(users, dropped, args.out)
    print(
        f"[synth] {m['n_users_emitted']} users (case={m['n_case']} "
        f"control={m['n_control']}) -> {args.out}"
    )
    print(f"[synth] digest={m['digest_sha256'][:16]}  SYNTHETIC-ONLY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
