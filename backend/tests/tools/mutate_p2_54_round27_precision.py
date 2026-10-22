#!/usr/bin/env python
"""ROUND_27（A 摊）变异见证：精度是否真的进入计算。

要证明的不是「脚本能跑」，而是**提交的 csv 精细值确实参与指标计算**——
否则 `--report-only` 这条复算路径就是恒真的（无论 csv 怎么改，数字都不变）。

四组：

M1  1 ulp 扰动（最接近阈值的样本 ±1 ulp）——预期**无指标变化**
    （排序不变、阈值不跨 ⇒ 指标离散不变；诚实记录「1 ulp 不可区分」）
M2  **跨阈值的最小可表达改动**：把该样本设为 0.5 的前一个 double
    （0.49999999999999994）⇒ 该样本从「判正」翻成「判负」⇒ 混淆矩阵必变
M3  **对照臂**：把 csv 重新格式化为 6 位小数（模拟 ROUND_26 形态），
    对同一行做同样的「设为 0.49999999999999994」——写入后会被舍入成
    `0.500000` ⇒ 读回 0.5 ⇒ 判正 ⇒ **指标不变**
    ⇒ M2 与 M3 的差异证明「精度确实进入计算」，门槛非恒真
M4  6 位 csv 全量复算 ⇒ CI 端点回到 ROUND_26 的旧值
    （量化「6 位舍入 + 行序」造成的偏差）

纪律：字节快照 + try/finally 还原；末尾用 `--report-only` 复算，
确认产物与提交版逐字节一致（final_clean）。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "modeling" / "eval" / "v1_29" / "01_reproducible_eval.py"
CSV = BACKEND / "models" / "artifacts" / "physiological_optimized" / "test_predictions.csv"
EVAL_JSON = BACKEND.parent / "docs" / "model-evaluation" / "physio_v2_current_data_eval.json"
REPORT_MD = BACKEND.parent / "docs" / "model-evaluation" / "PHYSIO_V2_EVAL_REPORT.md"
LOG = Path(__file__).with_name("mutate_p2_54_round27_precision_result.log")

PY = sys.executable
MUTATION_ROW = 30  # 最接近 0.5 的样本（0.500027248629116）
BELOW_HALF = repr(float(np.nextafter(0.5, -np.inf)))  # 0.49999999999999994

_lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    _lines.append(msg)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_report_only() -> None:
    r = subprocess.run(
        [PY, str(SCRIPT), "--report-only"], cwd=BACKEND, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr


def metrics_snapshot() -> dict:
    d = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    return {
        "TP": d["meta"]["TP"],
        "FP": d["meta"]["FP"],
        "FN": d["meta"]["FN"],
        "TN": d["meta"]["TN"],
        "f1": d["f1"]["point"],
        "f1_ci": d["f1"]["ci95"],
        "rec_ci": d["rec"]["ci95"],
        "auc": d["roc_auc"]["point"],
        "auc_ci": d["roc_auc"]["ci95"],
    }


def read_rows() -> list[list[str]]:
    text = CSV.read_text(encoding="utf-8").strip().splitlines()
    return [ln.split(",") for ln in text[1:]]


def write_rows(rows: list[list[str]], fmt: str = "{:.17g}") -> None:
    lines = ["sample_id,row_index,y_true,y_score,y_pred,y_score_refit_scaler"]
    for r in rows:
        lines.append(
            f"{r[0]},{r[1]},{r[2]},{fmt.format(float(r[3]))},{r[4]},{fmt.format(float(r[5]))}"
        )
    CSV.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    log("# ROUND_27 A 摊变异见证 — 精度是否进入计算")
    log(f"# 目标样本 idx={MUTATION_ROW}；跨阈值目标值 = {BELOW_HALF}（0.5 的前一个 double）")
    log("")

    orig = {p: p.read_bytes() for p in (CSV, EVAL_JSON, REPORT_MD)}
    ok = {"m1": False, "m2": False, "m3": False, "m4": False, "m5": False}
    try:
        run_report_only()
        base = metrics_snapshot()
        base_sha = sha(EVAL_JSON)
        log(f"[baseline] f1={base['f1']} ci={base['f1_ci']}")
        log(f"           TP/FP/FN/TN={base['TP']}/{base['FP']}/{base['FN']}/{base['TN']}  json_sha={base_sha[:16]}")

        # ---- M1: 1 ulp ----
        rows = read_rows()
        v = float(rows[MUTATION_ROW][3])
        rows[MUTATION_ROW][3] = repr(float(np.nextafter(v, np.inf)))
        write_rows(rows)
        run_report_only()
        m1 = metrics_snapshot()
        same = (
            (m1["TP"], m1["FP"], m1["FN"], m1["TN"]) == (base["TP"], base["FP"], base["FN"], base["TN"])
            and m1["f1"] == base["f1"]
            and m1["f1_ci"] == base["f1_ci"]
            and m1["auc_ci"] == base["auc_ci"]
        )
        ok["m1"] = same
        log(f"[M1] 1 ulp 扰动：{'指标不变（1 ulp 不可区分，如实记录）' if same else '指标发生变化'}")

        # ---- M2: 跨阈值（全精度 csv）----
        rows = read_rows()
        rows[MUTATION_ROW][3] = BELOW_HALF
        write_rows(rows)
        run_report_only()
        m2 = metrics_snapshot()
        changed = (
            (m2["TP"], m2["FP"], m2["FN"], m2["TN"]) != (base["TP"], base["FP"], base["FN"], base["TN"])
        )
        ok["m2"] = changed
        log(
            f"[M2] 全精度 csv 上设为 {BELOW_HALF}："
            f"TP/FP/FN/TN {base['TP']}/{base['FP']}/{base['FN']}/{base['TN']} -> "
            f"{m2['TP']}/{m2['FP']}/{m2['FN']}/{m2['TN']}；f1 {base['f1']} -> {m2['f1']}"
        )

        # ---- M3: 6 位 csv 上同样操作（对照臂）----
        rows = read_rows()
        rows[MUTATION_ROW][3] = BELOW_HALF
        write_rows(rows, fmt="{:.6f}")  # 会被舍入成 0.500000
        run_report_only()
        m3 = metrics_snapshot()
        unchanged_vs_base = (
            (m3["TP"], m3["FP"], m3["FN"], m3["TN"]) == (base["TP"], base["FP"], base["FN"], base["TN"])
            and m3["f1"] == base["f1"]
        )
        ok["m3"] = unchanged_vs_base
        log(
            f"[M3] 6 位 csv 上同样设为 {BELOW_HALF}：写入后读回 0.500000 ⇒ "
            f"TP/FP/FN/TN {m3['TP']}/{m3['FP']}/{m3['FN']}/{m3['TN']}（"
            f"{'与基线相同 ⇒ 对照成立：6 位舍入吞掉了跨阈值的精细差别' if unchanged_vs_base else '意外变化'}）"
        )

        # ---- M4: 6 位 csv 复算 ⇒ 精度对 bootstrap CI 是否敏感 ----
        write_rows(read_rows(), fmt="{:.6f}")
        run_report_only()
        m4 = metrics_snapshot()
        ci_same = m4["f1_ci"] == base["f1_ci"] and m4["auc_ci"] == base["auc_ci"]
        ok["m4"] = ci_same
        log(
            f"[M4] 6 位 csv 复算：f1 ci {base['f1_ci']} -> {m4['f1_ci']}；"
            f"auc ci {base['auc_ci']} -> {m4['auc_ci']}\n"
            f"       ⇒ {'CI 不变 ⇒ 本数据下 6 位舍入未改变任何排序位置（精度对 CI 不敏感）' if ci_same else 'CI 变化'}"
        )

        # ---- M5: 按 split 的 tei 顺序重排 ⇒ 应复现 ROUND_26 的旧 CI ----
        import importlib.util

        spec = importlib.util.spec_from_file_location("ev", SCRIPT)
        ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ev)
        df = ev.load_depresjon_data()
        yy = df["depression_label"].values.astype(np.int64)
        _tri, _vai, tei = ev.split_indices(yy)
        order = {int(idx): pos for pos, idx in enumerate(tei)}
        rows = read_rows()
        rows.sort(key=lambda r: order[int(r[1])])
        write_rows(rows)  # 全精度，仅改行序
        run_report_only()
        m5 = metrics_snapshot()
        old_ci = [0.638282, 0.843137]
        reproduces_old = m5["f1_ci"] == old_ci
        ok["m5"] = reproduces_old
        log(
            f"[M5] 全精度 + tei 顺序重排：f1 ci {m5['f1_ci']}"
            f"（ROUND_26 旧值 {old_ci}）\n"
            f"       ⇒ {'复现旧值 ⇒ CI 偏差的根因是**行序**，不是精度' if reproduces_old else '未复现（需进一步归因）'}"
        )
    finally:
        for p, b in orig.items():
            p.write_bytes(b)
        run_report_only()
        restored = all(sha(p) == hashlib.sha256(b).hexdigest() for p, b in orig.items())
        log("")
        log(f"[restore] {'CLEAN（三产物与快照逐字节一致）' if restored else 'RESIDUAL'}")
        log(f"[summary] M1={'OK' if ok['m1'] else 'FAIL'} M2={'OK' if ok['m2'] else 'FAIL'} "
            f"M3={'OK' if ok['m3'] else 'FAIL'} M4={'OK' if ok['m4'] else 'FAIL'} M5={'OK' if ok['m5'] else 'FAIL'}")
        passed = all(ok.values()) and restored
        log(f"[exit] {'PASS' if passed else 'FAIL'}")
        LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
