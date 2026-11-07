r"""ROUND_35 收尾（仓库内可复现版）：为 7 例「本轮引入失败」的修复闸门做真实变异见证。

铁律：
  - 变异与测试禁并发；每个变异用字节快照 + try/finally 还原，sha256 校验；
  - 末臂还原后跑全部 7 个 gate，必须 GREEN；
  - 每次变异只跑它对应的 gate，记录实际 FAILED 集合，不得只凭 rc。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
OUT = Path(__file__).resolve().with_name("mutate_round35_ab_result.log")
ADDONS = (
    "addopts=--strict-markers --import-mode=importlib "
    "--ignore=functional_test.py --ignore-glob=test_result*.txt --ignore=test_final.txt"
)

UP = "backend/app/api/v1/user_upload.py"
FS = "backend/app/services/file_security_service.py"
PROBE = REPO / "frontend/src/components/__Round35OrphanProbe.vue"

SEC = "tests/test_sec_p2_003_stab_p2_009_sec_p2_005.py"
P11 = "tests/test_p2_11_round11.py"

G_UPLOAD_FILE = f"{SEC}::TestUploadApiIntegration::test_upload_file_endpoint_calls_process_uploaded_file"
G_UPLOAD_BATCH = f"{SEC}::TestUploadApiIntegration::test_upload_batch_endpoint_calls_process_uploaded_file"
G_ORPHAN_COUNT = f"{P11}::TestOrphanComponentRatchet::test_orphan_count_not_increased"
G_ORPHAN_LIST = f"{P11}::TestOrphanComponentRatchet::test_orphan_list_synced_with_audit_doc"
G_BUCKET = f"{P11}::TestP235SilentDegradationRatchet::test_batch6_bucket_counts_pinned"
G_WIRING_CAND = f"{P11}::TestP235Round13Batch33Wiring::test_candidates_present_and_enclosing_func"
G_WIRING_ONLY = f"{P11}::TestP235Round13Batch33Wiring::test_wiring_only_at_validate_mime_type"

ALL_GATES = [
    G_UPLOAD_FILE, G_UPLOAD_BATCH, G_ORPHAN_COUNT, G_ORPHAN_LIST,
    G_BUCKET, G_WIRING_CAND, G_WIRING_ONLY,
]


def run_pytest(nodeids: list[str]) -> tuple[int, set[str], str]:
    cmd = [
        str(PY), "-m", "pytest", "-o", ADDONS, "-p", "no:cacheprovider",
        "-q", "--tb=no", *nodeids,
    ]
    proc = subprocess.run(
        cmd, cwd=str(BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=900,
    )
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    failed = {
        line[7:].split(" - ", 1)[0].strip()
        for line in text.splitlines()
        if line.startswith("FAILED ")
    }
    return proc.returncode, failed, text


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


log: list[str] = []


def record(line: str) -> None:
    log.append(line)
    print(line, flush=True)


def mutated_source(name: str, rel: str, old: str, new: str, gates: list[str]) -> bool:
    """源码字节替换型变异。返回该变异是否被至少一个 gate 杀掉。"""
    p = REPO / rel
    original = p.read_bytes()
    assert original.count(old.encode("utf-8")) == 1, f"{name}: 锚点不唯一"
    mutated = original.replace(old.encode("utf-8"), new.encode("utf-8"), 1)
    assert mutated != original, f"{name}: 变异未改变字节"
    killed = False
    try:
        p.write_bytes(mutated)
        _rc, failed, _text = run_pytest(gates)
        killed = bool(failed)
        record(f"{name}: {'RED (killed)' if killed else '*** NOT KILLED ***'} "
               f"failed={sorted(failed)}")
    finally:
        p.write_bytes(original)
        assert p.read_bytes() == original, f"{name}: 字节还原失败"
        record(f"{name}: restored sha256={sha(original)}")
    return killed


results: list[tuple[str, bool]] = []

# M1：断掉公共上传管线对安全扫描函数的引用 -> 两条上传 AST 闸门都应红
results.append(("M1 upload chain", mutated_source(
    "M1 upload chain", UP,
    "            process_uploaded_file, save_path, category\n",
    "            _round35_disabled_scan, save_path, category\n",
    [G_UPLOAD_FILE, G_UPLOAD_BATCH],
)))

# M2：把 MIME 校验 handler 整体前移一行 -> 行号基线闸门应红
results.append(("M2 handler line drift", mutated_source(
    "M2 handler line drift", UP,
    "    except (magic.MagicException, OSError) as exc:\n",
    "\n    except (magic.MagicException, OSError) as exc:\n",
    [G_WIRING_CAND, G_WIRING_ONLY],
)))

# M3：移除 M-08 新增的临时文件清理 except handler -> 桶计数应回到 X=118
results.append(("M3 bucket handler removed", mutated_source(
    "M3 bucket handler removed", FS,
    "        try:\n"
    "            tmp_path.unlink(missing_ok=True)\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n",
    "        tmp_path.unlink(missing_ok=True)\n",
    [G_BUCKET],
)))

# M4：新增一个无任何引用方的组件 -> 孤儿棘轮（计数 + 清单）应红
PROBE_CONTENT = b"<!-- ROUND_35 mutation witness: temporary orphan component -->\n<template><div /></template>\n"
assert not PROBE.exists(), "探针文件已存在，先清理"
killed_m4 = False
try:
    PROBE.write_bytes(PROBE_CONTENT)
    _rc, failed, _text = run_pytest([G_ORPHAN_COUNT, G_ORPHAN_LIST])
    killed_m4 = bool(failed)
    record(f"M4 new orphan: {'RED (killed)' if killed_m4 else '*** NOT KILLED ***'} "
           f"failed={sorted(failed)}")
finally:
    if PROBE.exists():
        PROBE.unlink()
    assert not PROBE.exists(), "M4: 探针文件未清理"
    record("M4: probe removed")
results.append(("M4 new orphan", killed_m4))

# 末臂：全部还原后 7 个 gate 必须 GREEN
rc, failed, text = run_pytest(ALL_GATES)
final_green = rc == 0 and not failed
summary = [l for l in text.splitlines() if "passed" in l or "failed" in l]
record(f"FINAL ARM: rc={rc} failed={sorted(failed)} summary={summary[-1:]}")
record(f"FINAL ARM: {'GREEN' if final_green else '*** RED ***'}")

killed = sum(1 for _, k in results if k)
record("-" * 72)
for name, k in results:
    record(f"  {'KILLED' if k else 'MISSED'}  {name}")
record(f"RESULT: {'PASS' if killed == len(results) and final_green else 'FAIL'} "
       f"({killed}/{len(results)} RED, restored byte-identical, final "
       f"{'GREEN' if final_green else 'RED'})")
OUT.write_text("\n".join(log) + "\n", encoding="utf-8")
