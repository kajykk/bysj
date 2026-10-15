"""第十三轮第十四批闸门变异验证（4 处接线 + 文档登记 + fail-closed 反向钉）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch14.py

四个变异（全部强：整块/整行删除或整串改名，语义级；子串逃逸式弱变异直接作废）：
- M1 删 core.safe_pickle.joblib_env_guard_unavailable 接线 → 红：locations / 运行时计数器；
- M2 改 core.model_registry_v2.registry_file_unparsable 的 location 字面量 → 红：同上；
- M3 删 P2_11 附录登记行 → 红：locations；
- M4 给已裁定 fail-closed 的 handler 加上接线 → 红：反向钉（这是裁定前提的性质检验，
  与前三者的方向相反：它在**证明反向钉不是摆设**）。

注：与第十二/十三批同口径 —— 磁盘上是 CRLF，但 read_text 通用换行归一为 \n、
write_text 再写回 CRLF，故锚点一律写 \n。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch14Wiring"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch14_result.log"

SPICKLE = REPO / "backend" / "app" / "core" / "safe_pickle.py"
REG = REPO / "backend" / "app" / "core" / "model_registry_v2.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

JOBLIB_WIRING = (
    '            record_silent_degradation('
    '"core.safe_pickle.joblib_env_guard_unavailable")\n'
)
REG_LIT = '"core.model_registry_v2.registry_file_unparsable"'
REG_MUT = '"core.model_registry_v2.registry_file_unparsable_RENAMED"'
DOC_LINE = "    core.model_registry_v2.registry_records_dropped\n"

# 反向钉变异：在已裁定不接线的 fail-closed handler 里偷偷加一条接线
UNPICKLER_ANCHOR = (
    '        logger.error("无法导入 joblib.NumpyUnpickler，反序列化白名单不可用: %s", exc)\n'
)
UNPICKLER_MUT = (
    '        logger.error("无法导入 joblib.NumpyUnpickler，反序列化白名单不可用: %s", exc)\n'
    '        record_silent_degradation("core.safe_pickle.restricted_unpickler_unavailable")\n'
)

EXPECT_RUNTIME_RED = [
    "test_locations_wired_in_code_and_doc",
    "test_four_paths_increment",
]

MUTATIONS = [
    (
        "M1 删 core.safe_pickle.joblib_env_guard_unavailable 接线",
        "强（整块删除，语义级；该行在 except 块末尾，删掉后两者即失联）",
        SPICKLE,
        JOBLIB_WIRING,
        "",
        EXPECT_RUNTIME_RED,
    ),
    (
        "M2 改 core.model_registry_v2.registry_file_unparsable 的 location 字面量",
        "强（整串改名，语义级；含闭合引号，不触发子串逃逸）",
        REG,
        REG_LIT,
        REG_MUT,
        EXPECT_RUNTIME_RED,
    ),
    (
        "M3 删 P2_11 附录登记行",
        "强（整行删除，文档侧半断言）",
        AUDIT,
        DOC_LINE,
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
    (
        "M4 给已裁定 fail-closed 的 handler 加接线",
        "强（反向变异：验证 test_declined_restricted_unpickler_no_wiring 不是摆设）",
        SPICKLE,
        UNPICKLER_ANCHOR,
        UNPICKLER_MUT,
        ["test_declined_restricted_unpickler_no_wiring"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b14mut",
        ],
        cwd=REPO / "backend",
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode == 0, "\n".join(proc.stdout.strip().splitlines()[-16:])


def main() -> int:
    lines: list[str] = []
    ok_all = True
    for name, strength, path, old, new, expect_red in MUTATIONS:
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
        "# 第十三轮第十四批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n"
        "# M4 为反向变异：给已裁定 fail-closed 的 handler 加接线，反向钉必须红。\n\n"
        + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
