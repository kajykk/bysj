"""第十三轮第一批新闸门变异验证：删接线 / 改 location / 删文档登记，逐一红→恢复绿。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch1.py

铁律（第十三轮提示词新增）：变异先审强度再看红绿——子串逃逸式弱变异直接作废。
本脚本三个变异都是**语义级**（整句删除 / 整个 location 字面量更换 / 整行文档
登记删除），不玩"改一个字符但旧串仍是新串子串"的逃逸。

每个变异跑两轮：
  RED  —— 变异在位时，指定闸门必须红（含期望的失败测试名）；
  GREEN—— 还原后必须全绿。
任一环节不达标 → 退出码非 0，结论作废。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # backend/tests/tools/ → 仓库根
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch1_result.log"

VALIDATION = REPO / "backend" / "app" / "api" / "v1" / "validation.py"
CACHE = REPO / "backend" / "app" / "core" / "cache.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

# (变异名, 强度自评, 文件, 原文, 变异文, 期望红的测试名子串)
MUTATIONS = [
    (
        "M1 删 validation.get 整个接线语句",
        "强（整句删除，语义级）",
        VALIDATION,
        """                # P2-35：读路径降级 —— 任务可能创建在其它实例/Redis，回退本进程
                # 内存后查不到即返回 None，用户侧呈现"任务不存在"假象，必须计数。
                record_silent_degradation(
                    "api.validation.job_store.get.redis_fallback"
                )
""",
        "",
        [
            "test_locations_wired_in_code_and_doc",
            "test_read_path_fallback_increments_counter",
            "test_batch6_bucket_counts_pinned",
        ],
    ),
    (
        "M2 改 cache 共享客户端 location 字面量",
        "强（整个 location 标识更换，非同串子串）",
        CACHE,
        'record_silent_degradation("core.cache.redis_client_init_failed")',
        'record_silent_degradation("core.cache.redis_client_init_error")',
        [
            "test_locations_wired_in_code_and_doc",
            "test_cache_client_init_failure_increments_counter",
        ],
    ),
    (
        "M3 删审计文档一条 location 登记行",
        "强（整行删除，文档侧半断言）",
        AUDIT,
        "    core.cache.redis_pubsub_client_init_failed\n",
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY),
            "-m",
            "pytest",
            GATE,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
            "--basetemp=p2_11_r13mut",
        ],
        cwd=REPO / "backend",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tail = "\n".join(proc.stdout.strip().splitlines()[-12:])
    return proc.returncode == 0, tail


def main() -> int:
    lines: list[str] = []
    ok_all = True
    for name, strength, path, old, new, expect_red in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        assert old in original, f"{name}: 原文未找到（锚点失效，结论作废）"
        # 变异在位 → 必须红，且红在期望的测试上
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        red, red_tail = run_gate()
        # 还原 → 必须绿
        path.write_text(original, encoding="utf-8")
        green, green_tail = run_gate()

        # red=True 表示 returncode==0（通过）；变异态必须不通过、还原态必须通过
        red_hits = [t for t in expect_red if t in red_tail]
        verdict = (
            "RED-OK/GREEN-OK"
            if ((not red) and green and len(red_hits) == len(expect_red))
            else "作废"
        )
        if verdict == "作废":
            ok_all = False
        lines.append(
            f"== {name}\n   强度自评：{strength}\n   变异态 returncode=0? {red}（应为 False）\n"
            f"   期望红的测试命中：{len(red_hits)}/{len(expect_red)} {red_hits}\n"
            f"   还原态 returncode=0? {green}（应为 True）\n   判定：{verdict}\n"
            f"   --- 变异态输出尾部 ---\n{red_tail}\n   --- 还原态输出尾部 ---\n{green_tail}\n"
        )
        print(lines[-1])
    LOG.write_text(
        "# 第十三轮第一批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
