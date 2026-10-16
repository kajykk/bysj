"""第十三轮第十九批闸门变异验证（纯裁定批：0 接线 + 13 条不接线反向钉）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch19.py

本批是纯裁定批（无 location 接线），变异目标从「删接线」换成「证明反向钉
能抓住三类破坏」：
- M1 给 _cleanup_uploads_dir_impl 的单文件 except 误加 record_silent_degradation
  → 红：test_declined_func_level_not_wired（证明「未接线」断言非恒真）；
- M2 改 _get_expected_hash 的侧车告警文本（锚点漂移）→ 红：同一条的锚点断言；
- M3 删 P2_13「一之二十」节标题行 → 红：test_doc_registered_batch19。

注：与第十二~十八批同口径 —— 磁盘上是 CRLF，但 read_text 通用换行归一为 \n、
write_text 再写回 CRLF，故锚点一律写 \n。所有锚点均断言「恰好命中 1 处」。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch19Declined"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch19_result.log"

SCHED = REPO / "backend" / "app" / "tasks" / "scheduler.py"
LOADING = REPO / "backend" / "app" / "core" / "model_engine" / "loading.py"
AUDIT13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

# M1：误接线（在 _cleanup_uploads_dir_impl 的单文件 except 里加一行计数）
M1_OLD = (
    "            except OSError as exc:\n"
    '                logger.debug("skip file %s: %s", file_path, exc)\n'
)
M1_NEW = (
    "            except OSError as exc:\n"
    '                record_silent_degradation("tasks.scheduler.probe_wrong_wiring")\n'
    '                logger.debug("skip file %s: %s", file_path, exc)\n'
)
# M2：锚点文本漂移（侧车告警改词）
M2_OLD = "无法解析侧车校验文件"
M2_NEW = "无法解析侧车校验档案"
# M3：删「一之二十」节标题行
M3_OLD = "## 一之二十、#35 X 桶第十九批：纯裁定批（0 接线，W=95 / X=120 不变，13 条不接线）\n"
M3_NEW = ""

MUTATIONS = [
    (
        "M1 给 _cleanup_uploads_dir_impl 误加 record_silent_degradation",
        "强（整行插入，语义级；直接违反「未接线」裁定）",
        SCHED,
        M1_OLD,
        M1_NEW,
        ["test_declined_func_level_not_wired"],
    ),
    (
        "M2 改 _get_expected_hash 的侧车告警文本（锚点漂移）",
        "强（整串替换，语义级；锚点消失即闸门失效）",
        LOADING,
        M2_OLD,
        M2_NEW,
        ["test_declared_placeholder_never_matches"],
    ),
    (
        "M3 删 P2_13「一之二十」节标题行",
        "强（整行删除，文档登记半断言）",
        AUDIT13,
        M3_OLD,
        M3_NEW,
        ["test_doc_registered_batch19"],
    ),
]

# M2 期望红的测试名（func 级反向钉跑 _get_expected_hash 时锚点必失）；
# 用占位符在下方 run 前替换，避免手写名字与实现漂移。
EXPECT_M2 = "test_declined_func_level_not_wired"


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b19mut",
        ],
        cwd=REPO / "backend",
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode == 0, "\n".join(proc.stdout.strip().splitlines()[-16:])


def main() -> int:
    lines: list[str] = []
    ok_all = True
    for name, strength, path, old, new, expect_red in MUTATIONS:
        if expect_red == ["test_declared_placeholder_never_matches"]:
            expect_red = [EXPECT_M2]
        original = path.read_text(encoding="utf-8")
        assert old in original, f"{name}: 原文未找到（锚点失效，结论作废）"
        assert original.count(old) == 1, (
            f"{name}: 锚点命中 {original.count(old)} 处，期望 1（锚点漂移 = 结论作废）"
        )
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        passed, red_tail = run_gate()
        path.write_text(original, encoding="utf-8")
        green, green_tail = run_gate()
        red_hits = [t for t in expect_red if t in red_tail]
        verdict = (
            "RED-OK/GREEN-OK"
            if ((not passed) and green and len(red_hits) == len(expect_red))
            else "作废"
        )
        if verdict == "作废":
            ok_all = False
        lines.append(
            f"== {name}\n   强度自评：{strength}\n   变异态 returncode==0? {passed}（应为 False）\n"
            f"   期望红的测试命中：{len(red_hits)}/{len(expect_red)} {red_hits}\n"
            f"   还原态 returncode==0? {green}（应为 True）\n   判定：{verdict}\n"
            f"   --- 变异态输出尾部 ---\n{red_tail}\n   --- 还原态输出尾部 ---\n{green_tail}\n"
        )
        print(lines[-1])
    LOG.write_text(
        "# 第十三轮第十九批（#35 纯裁定批）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
