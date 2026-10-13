"""P2-32 回退对照实验（第八轮）。

#31 的驱动（scripts/rollback_experiments_p2_31.py）只跑 pytest；本轮的
核心反向闸门在前端（vitest），故单独成驱动。

自检（防"验证工具失效伪装成修复有效"）：每个变异轮必须检不出 failed
才判实验无效 —— 与 #31 驱动同纪律。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
# FRONTEND 必须 resolve：未解析的相对路径在 `vitest.cmd` 里会按 cmd 的当前目录
# 再解析一次，导致 vitest 找不到配置文件、以 "no tests" + ReferenceError 收场
# —— 闸门压根没跑到断言，实验失去意义。
FRONTEND = (BACKEND.parent / "frontend").resolve()
PYTEST = BACKEND / ".venv" / "Scripts" / "python.exe"
LOG_PATH = BACKEND / "scripts" / "rollback_p2_32_result.log"

# Windows 下 subprocess 调`npx` 会 FileNotFoundError（WinError 2）——
# npx 是 shell 包装脚本，必须用 node_modules/.bin 下的 .cmd 绝对路径。
VITEST = FRONTEND / "node_modules" / ".bin" / "vitest.cmd"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class Mutation:
    name: str
    file: Path
    old: str
    new: str
    cmd: list[str]
    cwd: Path
    expect_red: list[str]
    note: str


def run(cmd: list[str], cwd: Path) -> tuple[str, int, int, list[str]]:
    """跑命令，返回 (输出, passed, failed, 失败用例名)。

    失败名的两种格式都要认（此前只认 pytest 的 `^FAILED`，漏掉 vitest 的
    ` FAIL  `（两空格 + 大写 FAIL），导致闸门明明红了却被判「实验无效」——
    即「验证工具自身失效伪装成实验有效」的同型坑）：
      - pytest:  `FAILED tests/x.py::test_name`
      - vitest:  ` FAIL  src/x.test.ts > suite > test_name`
    以及 vitest 逐用例列表里的 `× name` 行（行尾带 `10ms` 之类时长后缀）。
    """
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace"
    )
    out = _ANSI_RE.sub("", proc.stdout + proc.stderr)
    failed_names = re.findall(r"^FAILED (\S+)", out, re.M)
    # vitest 的 ` FAIL  src/x.test.ts > suite > test_name`：必须捕获**整行**。
    # 用 (\S+) 只会拿到文件路径（被第一个 `>` 截断），丢掉用例名 →
    # 期望用例名匹配不上 → 闸门明明红了却判「实验无效」。
    failed_names += [m.strip() for m in re.findall(r"^\s*FAIL\s+(.+?)\s*$", out, re.M)]
    failed_names += [
        m.strip() for m in re.findall(r"^\s+×\s+(.+?)(?:\s+\d+ms)?$", out, re.M)
    ]
    failed_names = [n for n in failed_names if n]
    m = re.search(r"(\d+) failed", out)
    n_failed = int(m.group(1)) if m else len(failed_names)
    m2 = re.search(r"(\d+) passed", out)
    n_passed = int(m2.group(1)) if m2 else 0
    return out, n_passed, n_failed, failed_names


PROBE_FILE = FRONTEND / "src" / "views" / "user" / "__p2_32_probe.vue"
PROBE_SRC = """<template><div /></template>
<script setup lang="ts">
function badDownload(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}
void badDownload
</script>
"""

MUTATIONS: list[Mutation] = [
    Mutation(
        name="E10 前端新增一份手写下载链路",
        file=PROBE_FILE,
        old="",
        new=PROBE_SRC,
        cmd=[str(VITEST), "run", "src/utils/p2_32_ssot.test.ts"],
        cwd=FRONTEND,
        expect_red=["src/ 下无SSOT"],
        note="绕过 downloadBlob 的新下载链路 → 静态闸门红",
    ),
    Mutation(
        name="E11 downloadBlob 退化为同步 revoke（M-29 缺陷复现）",
        file=FRONTEND / "src" / "utils" / "exportUtils.ts",
        # 只替换 revoke 调用本身，保留 setTimeout 包装以外的函数体 ——
        # 早先写成整块替换导致 `url is not defined`，模块加载即崩，
        # 闸门根本没跑到断言（"no tests"），实验失去意义。
        old="  setTimeout(() => URL.revokeObjectURL(url), 1000)",
        new="  URL.revokeObjectURL(url)",
        cmd=[str(VITEST), "run", "src/utils/p2_32_ssot.test.ts"],
        cwd=FRONTEND,
        expect_red=["必须延迟 revoke"],
        note="SSOT 自身退化为同步 revoke → 行为闸门红（M-29 修复不可退化）",
    ),
]

BACKEND_MUTATIONS: list[Mutation] = [
    Mutation(
        name="E12 后端新增第二份危机词表",
        file=BACKEND / "app" / "core" / "_tmp_ssot_probe.py",
        old="",
        new='CRISIS_KEYWORDS: list[str] = [\n    "想死",\n    "自杀",\n]\n',
        cmd=[
            str(PYTEST),
            "-m",
            "pytest",
            "tests/test_p2_32_ssot.py",
            "-o",
            "addopts=--import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
            "--no-header",
        ],
        cwd=BACKEND,
        expect_red=["test_wordlist_defined_only_in_ssot"],
        note="重复定义危机词表 → SSOT 闸门红（并精确指出文件:行号）",
    ),
]


def run_experiment(mut: Mutation, log: list[str]) -> bool:
    log.append("=" * 78)
    log.append(mut.name)
    log.append(f"  说明: {mut.note}")
    log.append(f"  文件: {mut.file.relative_to(BACKEND.parent).as_posix()}")
    backup: str | None = None
    if mut.file.exists():
        backup = mut.file.read_text(encoding="utf-8")
        # 锚点校验：old 非空却不在文件里 → 变异会被静默跳过（测试当然不红），
        # 驱动却因 "failed==0" 报「实验无效」或误判。必须当场失败并说清。
        if mut.old and mut.old not in backup:
            raise AssertionError(
                f"变异锚点不存在于 {mut.file}：\n  old={mut.old!r}\n"
                "变异会被静默跳过 —— 实验将失去意义。修锚点后重跑。"
            )
        # ⚠️ 必须「替换锚点」，不能 write_text(mut.new) 把整个文件覆盖成片段 ——
        # 那会让文件只剩一行，模块里所有其它符号（url/blob/link…）全部未定义，
        # 测试在import 阶段就崩（ReferenceError + "no tests"），闸门压根没跑到断言。
        mutated = backup.replace(mut.old, mut.new, 1)
    else:
        mut.file.parent.mkdir(parents=True, exist_ok=True)
        mutated = mut.new
    mut.file.write_text(mutated, encoding="utf-8")

    ok = True
    try:
        out, n_pass, n_fail, names = run(mut.cmd, mut.cwd)
        log.append(f"  [变异轮] passed={n_pass} failed={n_fail}")
        # 变异轮失败时留档原始输出片段 —— 失败名解析不出来时，
        # 只有原始输出能说明是「闸门没红」还是「解析器没认出格式」。
        if n_fail:
            tail = [
                ln
                for ln in out.splitlines()
                if any(k in ln for k in ("×", "✓", "FAIL", "Error", "Tests", "Test Files"))
            ]
            log.append("    原始输出(过滤):")
            for ln in tail[:12]:
                log.append(f"      {ln.strip()[:150]}")
        # 自检：变异轮检不出 failed → 闸门测不到该变异 → 实验无效
        if n_fail == 0:
            log.append("  **实验无效：变异轮 0 failed —— 闸门测不到这个变异**")
            ok = False
        else:
            hit = [n for n in names if any(k in n for k in mut.expect_red)]
            for n in hit:
                log.append(f"    RED: {n}")
            if not hit:
                log.append(
                    f"    **实验无效：failed 但非预期用例（期望含 {mut.expect_red}），"
                    f"实际: {names}**"
                )
                ok = False
    finally:
        # 恢复
        if backup is None:
            mut.file.unlink(missing_ok=True)
        else:
            mut.file.write_text(backup, encoding="utf-8")

    out, n_pass, n_fail, _ = run(mut.cmd, mut.cwd)
    log.append(f"  [恢复轮] passed={n_pass} failed={n_fail}")
    if n_fail:
        ok = False
    log.append(f"  => {'PASS' if ok else 'INVALID'}")
    log.append("")
    return ok


def main() -> int:
    log = [
        "# P2-32 回退对照实验日志（第八轮）",
        f"# 运行时间: {datetime.now(timezone.utc).isoformat()}",
        f"# 前端驱动: vitest（#31 驱动只跑 pytest，本轮反向闸门在前端）",
        "",
    ]
    results = []
    for mut in MUTATIONS:
        results.append((mut.name, run_experiment(mut, log)))
    for mut in BACKEND_MUTATIONS:
        results.append((mut.name, run_experiment(mut, log)))

    passed = sum(1 for _, ok in results if ok)
    log.append("=" * 78)
    log.append("汇总")
    for name, ok in results:
        log.append(f"  [{'PASS' if ok else 'INVALID'}] {name}")
    log.append("")
    log.append(f"结论: {passed}/{len(results)} 项通过")
    text = "\n".join(log)
    LOG_PATH.write_text(text, encoding="utf-8")
    print(text[-1200:])
    print(f"\n完整日志: {LOG_PATH}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())