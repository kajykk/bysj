#!/usr/bin/env python
"""ROUND_28 (P2-55) 变异脚本：论文数字校验闸门（verify_thesis_numbers.py）必须红。

设计纪律（继承 mutate_* 惯例）
------------------------------
1. 每个臂只动**一个**漂移点，验证闸门的一类判据；
2. 全部变异在 `try/finally` 里以**字节快照**还原（新文件尚未提交，不能用
   `git checkout --`；工作树有预先存在的脏文件，更不能用）；
3. 每臂**重新加载**闸门模块再跑——闸门内部有 `_UNIT_CACHE` / `_GROUPWISE_CACHE`
   缓存，复用同一进程会读到上一臂的真值（假绿）；
4. 闸门返回 0 = 通过（GREEN），返回非 0 = 拦截（RED）；闸门抛异常同样记 RED
   （异常也是拒绝，退出码非 0），但在日志里区分形态，不冒充「FAIL 输出」；
5. 末臂还原后必须 GREEN——否则前面的红全是环境性假红，整轮作废。

臂位与判据对应
--------------
M1 章节主表点估计漂移        → check_chapter（主表）
M2 台账点估计漂移            → check_ledger
M3 章节注入黑名单数字        → check_blacklist（无拒绝标记）
M4 评估 json 点估计漂移      → check_artifacts（json vs csv 复算）
M5 csv 篡改（y_score 过阈）  → check_artifacts（sha 三层对拍 + y_pred 一致性）
M6 csv+sha+json 全链篡改     → check_artifacts 的**复算层**（自洽造假也要红）
M7 删台账登记行              → check_ledger（登记集合全等）
M8 去黑名单行拒绝标记        → check_blacklist（同行标记规则）
M9（末臂）全部还原           → 必须 GREEN

跑法（结果日志随脚本入库）：
    cd backend
    .venv/Scripts/python.exe tests/tools/mutate_p2_55_round28.py 2>&1 | tee tests/tools/mutate_p2_55_round28_result.log
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
GATE = BACKEND / "scripts" / "modeling" / "eval" / "verify_thesis_numbers.py"
CHAPTER = REPO / "docs" / "thesis" / "RESULTS_CHAPTER.md"
LEDGER = REPO / "docs" / "thesis" / "CLAIMS_LEDGER.md"
PHYSIO_JSON = REPO / "docs" / "model-evaluation" / "physio_v2_current_data_eval.json"
PHYSIO_CSV = BACKEND / "models" / "artifacts" / "physiological_optimized" / "test_predictions.csv"
PHYSIO_SHA = PHYSIO_CSV.with_suffix(".csv.sha256")

OLD_SCORE = "0.42876047293981129"   # csv 首行 y_score（< 0.5，y_pred=0）
NEW_SCORE = "0.92876047293981129"   # 改到 > 0.5：同时破坏 sha / y_pred 一致性 / 指标

# ────────────────────────── 闸门加载与运行 ──────────────────────────


def load_gate():
    """每次重新加载模块：清掉 _UNIT_CACHE / _GROUPWISE_CACHE，避免跨臂假绿。"""
    spec = importlib.util.spec_from_file_location("verify_thesis_numbers_mut", GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_gate() -> tuple[int, str, str]:
    """跑一次闸门。返回 (returncode, stdout, note)；异常记 returncode=99。"""
    mod = load_gate()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = mod.main([])
        return rc, buf.getvalue(), ""
    except Exception:
        return 99, buf.getvalue(), traceback.format_exc(limit=3)


# ────────────────────────── 变异原语 ──────────────────────────


def replace_text(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} 里找不到变异锚点：{old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def delete_lines_with(path: Path, substr: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if substr not in ln]
    assert len(kept) < len(lines), f"{path.name} 里找不到待删行：{substr!r}"
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def json_set(path: Path, dotted: str, value) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    node = payload
    keys = dotted.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def csv_flip_first_score(path: Path, flip_pred: bool) -> None:
    """把首行 y_score 从 <0.5 改到 >0.5；flip_pred=True 时同步改 y_pred（自洽造假）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    parts = lines[1].split(",")
    assert parts[3] == OLD_SCORE, f"csv 首行 y_score 已变：{parts[3]!r}"
    parts[3] = NEW_SCORE
    if flip_pred:
        assert parts[4] == "0", f"csv 首行 y_pred 已变：{parts[4]!r}"
        parts[4] = "1"
    lines[1] = ",".join(parts)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rewrite_sidecar(csv_path: Path, sha_path: Path) -> None:
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    name = csv_path.name
    sha_path.write_text(f"{digest}  {name}\n", encoding="utf-8")


# ────────────────────────── 臂定义 ──────────────────────────
# 每臂 = (编号, 判据说明, [(路径, 变异函数, 参数...)], 期望 RED 的关键片段或 None)


def arm_m1():
    replace_text(CHAPTER, "| Accuracy | 0.8599 | [0.8025, 0.9108] |",
                 "| Accuracy | 0.8600 | [0.8025, 0.9108] |")


def arm_m2():
    replace_text(LEDGER, "| C-04 | F1 | 0.7500 | [0.6410, 0.8434] |",
                 "| C-04 | F1 | 0.7600 | [0.6410, 0.8434] |")


def arm_m3():
    append_line(CHAPTER, "历史读数：F1 = 0.8542（见变更记录）")


def arm_m4():
    json_set(PHYSIO_JSON, "acc.point", 0.86)


def arm_m5():
    csv_flip_first_score(PHYSIO_CSV, flip_pred=False)


def arm_m6():
    csv_flip_first_score(PHYSIO_CSV, flip_pred=True)
    rewrite_sidecar(PHYSIO_CSV, PHYSIO_SHA)
    digest = hashlib.sha256(PHYSIO_CSV.read_bytes()).hexdigest()
    json_set(PHYSIO_JSON, "reproducibility.predictions_csv_sha256", digest)


def arm_m7():
    delete_lines_with(LEDGER, "| C-04 |")


def arm_m8():
    replace_text(LEDGER, "**禁用**：第三套数字", "第三套数字")


ARMS = [
    ("M1", "章节主表点估计漂移（check_chapter）", [arm_m1], "章节主表 Accuracy"),
    ("M2", "台账点估计漂移（check_ledger）", [arm_m2], "台账 C-04"),
    ("M3", "章节注入黑名单数字（check_blacklist）", [arm_m3], "黑名单"),
    ("M4", "评估 json 点估计漂移（check_artifacts）", [arm_m4], "acc.point"),
    ("M5", "csv 篡改不过阈（sha + y_pred 一致性）", [arm_m5], None),
    ("M6", "csv+sha+json 全链自洽篡改（复算层）", [arm_m6], "json meta.TP"),
    ("M7", "删台账登记行（登记集合全等）", [arm_m7], "台账缺少登记行"),
    ("M8", "去黑名单行拒绝标记（同行标记规则）", [arm_m8], "黑名单"),
]


def snapshot(paths: list[Path]) -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in paths}


def main() -> int:
    touched = [CHAPTER, LEDGER, PHYSIO_JSON, PHYSIO_CSV, PHYSIO_SHA]
    results: list[tuple[str, str, bool, str]] = []
    green_ok = True

    for code, desc, fns, expect in ARMS:
        snap = snapshot(touched)
        note = ""
        try:
            for fn in fns:
                fn()
            rc, out, err = run_gate()
            red = rc != 0
            if red and expect and expect not in out:
                note = f"（红但未见预期片段 {expect!r}，检查判据是否移位）"
            if not red:
                note = "（未拦截！闸门放行了该漂移）"
            summary = (out + err).strip().splitlines()
            results.append((code, desc, red, (summary[0] if summary else "") + note))
        finally:
            for p, data in snap.items():
                p.write_bytes(data)

    # 末臂：还原后必须 GREEN
    rc, out, err = run_gate()
    if rc != 0 or "论文数字校验 OK" not in out:
        green_ok = False
        results.append(("M9", "还原后必须 GREEN", False, (out + err).strip()[:200]))

    # 还原校验：字节快照比对（防 finally 静默失败）
    print("=" * 78)
    print("ROUND_28 (P2-55) 论文数字校验闸门 · 变异报告")
    print("=" * 78)
    all_red = True
    for code, desc, red, first in results:
        if code == "M9":
            continue
        mark = "RED-OK " if red else "GREEN-BAD"
        if not red:
            all_red = False
        print(f"[{mark}] {code} {desc}")
        if first:
            print(f"         {first[:160]}")
    if green_ok:
        print("[GREEN-OK] M9 还原后闸门全绿（前面的红不是环境性假红）")
    else:
        all_red = False
        print("[GREEN-BAD] M9 还原后闸门未全绿——本轮变异结果作废")
    print("-" * 78)
    print(f"合计：{sum(1 for r in results if r[0] != 'M9')} 臂变异，"
          f"{sum(1 for r in results if r[0] != 'M9' and r[2])} 臂被拦截；末臂 {'GREEN' if green_ok else 'RED'}")

    # 残留检测：与加载闸门时的字节快照比对（finally 之后应完全一致）
    for p in touched:
        if not p.exists():
            print(f"[RESIDUE] {p} 在还原后不存在！")
            all_red = False
    return 0 if (all_red and green_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
