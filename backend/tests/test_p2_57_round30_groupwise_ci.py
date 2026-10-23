"""ROUND_30：文本模态 groupwise 跨被试 CI 产物的测试接入。

职责（不重复 groupwise_ci.py 与闸门的复算，只做「存在 + 自洽 + 入库」）：
1. groupwise_ci.json 必须存在、可解析，且 method 明写「按 group 重采样」（防退化成按行）；
2. 其 oof_csv_sha256 必须与已提交 OOF csv 的 sha256 相等（防产物与数据脱钩）；
3. n_groups / n_rows / positive_rate 与 OOF csv 实测一致；
4. 四个指标点估计与 v1_27/groupwise_eval_results.json 的 groupwise 块一致（4 位小数）。
真复算权威在 verify_thesis_numbers.py（子进程，test_p2_55 已断言 rc=0）。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
CI_JSON = BACKEND / "scripts" / "modeling" / "eval" / "v1_30" / "groupwise_ci.json"
OOF_CSV = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_oof_predictions.csv"
GW_EVAL_JSON = BACKEND / "scripts" / "modeling" / "v1_27" / "groupwise_eval_results.json"


def _oof_rows() -> list[list[str]]:
    return [ln.split(",") for ln in OOF_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]]


def test_groupwise_ci_json_exists_and_method() -> None:
    assert CI_JSON.exists(), f"缺少 {CI_JSON}"
    payload = json.loads(CI_JSON.read_text(encoding="utf-8"))
    assert "group-level bootstrap" in payload["method"]
    assert "non-" not in payload["method"].lower()
    assert payload["metrics"].keys() >= {"f1", "roc_auc", "rec", "prec"}


def test_groupwise_ci_oof_sha_matches() -> None:
    payload = json.loads(CI_JSON.read_text(encoding="utf-8"))
    # 行尾不敏感哈希（CRLF→LF），与 groupwise_ci.py / verify 一致
    actual = hashlib.sha256(OOF_CSV.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert payload["oof_csv_sha256"] == actual, (
        f"groupwise_ci.json 的 oof sha 与当前 csv 不符：{payload['oof_csv_sha256']} vs {actual}"
    )


def test_groupwise_ci_counts_match_oof() -> None:
    payload = json.loads(CI_JSON.read_text(encoding="utf-8"))
    rows = _oof_rows()
    y = [int(r[0]) for r in rows]
    groups = {r[1] for r in rows}
    assert payload["n_rows"] == len(rows), (payload["n_rows"], len(rows))
    assert payload["n_groups"] == len(groups), (payload["n_groups"], len(groups))
    assert abs(payload["positive_rate"] - round(sum(y) / len(y), 4)) < 1e-9


def test_groupwise_ci_points_match_eval_json() -> None:
    ci = json.loads(CI_JSON.read_text(encoding="utf-8"))["metrics"]
    ev = json.loads(GW_EVAL_JSON.read_text(encoding="utf-8"))["groupwise_leakage_free"]
    pairs = {"f1": "f1", "roc_auc": "roc_auc", "rec": "recall", "prec": "precision"}
    for ck, ek in pairs.items():
        assert abs(ci[ck]["point"] - float(ev[ek])) < 5e-4, (
            f"{ck} 点估计与 groupwise_eval_results.json 不符：{ci[ck]['point']} vs {ev[ek]}"
        )


def test_groupwise_ci_json_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(CI_JSON)],
        cwd=REPO, capture_output=True, text=True, timeout=120,
    )
    assert tracked.returncode == 0, f"groupwise_ci.json 未入库：{tracked.stderr}"