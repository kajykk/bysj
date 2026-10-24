"""ROUND_33 路径修复变异见证：新闸门「source 必须是 posix 分隔符」的 RED→GREEN 证明。

背景：ROUND_33 首版 json 的 source 字段在 Windows 上生成（`str(Path)` ⇒ 反斜杠），
Linux CI checkout 下 4 个 calib 单元全部误报「source 不存在」（3 个测试红）。
修复：生成端改 `.as_posix()`，闸门/测试消费端防御性归一化 + 形态钉断。

本脚本对**生成端**做真实变异（as_posix → str），重新生成 json 后跑形态断言，
必须 RED；随后字节级还原并复跑必须 GREEN。子进程全新 pytest，规避模块级状态。
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
GEN = BACKEND / "scripts" / "modeling" / "eval" / "v1_33" / "calibration_analysis.py"
JSON = BACKEND / "scripts" / "modeling" / "eval" / "v1_33" / "calibration_analysis.json"
REPORT = BACKEND.parent / "docs" / "model-evaluation" / "CALIBRATION_REPORT.md"
TEST = "tests/test_p2_59_round33_calibration.py::test_calibration_json_sha_and_positive_rate"
LOG = Path(__file__).with_suffix("").with_name("mutate_round33_pathfix_result.log")


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(BACKEND), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def pytest_node() -> tuple[int, str]:
    return run([str(PY), "-m", "pytest", TEST, "-o",
                "addopts=--strict-markers --import-mode=importlib",
                "-p", "no:cacheprovider", "-q", "--no-header", "-x"])


def main() -> int:
    lines: list[str] = []
    gen_bytes = GEN.read_bytes()
    json_bytes = JSON.read_bytes()
    report_bytes = REPORT.read_bytes()
    ok = True
    try:
        # ---- 变异：生成端退回 str()（Windows 反斜杠） ----
        mutated = gen_bytes.replace(
            b'.relative_to(BACKEND.parent).as_posix()', b'.relative_to(BACKEND.parent))'
        ).replace(b'"source": oof.relative_to(BACKEND.parent))',
                  b'"source": str(oof.relative_to(BACKEND.parent))')
        mutated = mutated.replace(b'"source": physio.relative_to(BACKEND.parent))',
                                  b'"source": str(physio.relative_to(BACKEND.parent))')
        mutated = mutated.replace(b'"source": ood.relative_to(BACKEND.parent))',
                                  b'"source": str(ood.relative_to(BACKEND.parent))')
        mutated = mutated.replace(b'"source": kag.relative_to(BACKEND.parent))',
                                  b'"source": str(kag.relative_to(BACKEND.parent))')
        if mutated == gen_bytes:
            lines.append("!! 变异未命中（替换为空）——脚本与实现脱钩，终止")
            LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return 1
        GEN.write_bytes(mutated)
        rc, out = run([str(PY), str(GEN)])
        lines.append(f"=== M1 生成端退回 str()（反斜杠路径）===")
        lines.append(f"重生成 exit = {rc}")
        has_bs = b"\\\\" in JSON.read_bytes()
        lines.append(f"json 含反斜杠 = {has_bs}")
        rc2, out2 = pytest_node()
        lines.append(f"pytest exit = {rc2}（期望非 0 = RED）")
        lines.extend(l.strip()[:160] for l in out2.splitlines()
                     if any(k in l for k in ("passed", "failed", "AssertionError", "反斜杠")))
        if rc2 == 0 or not has_bs:
            lines.append("!! 变异未被杀死（或未生效）——闸门失效")
            ok = False
        else:
            lines.append("OK：变异被杀死（RED）")
        # ---- 还原（字节级）并复跑 ----
        GEN.write_bytes(gen_bytes)
        rc3, _ = run([str(PY), str(GEN)])
        same = (GEN.read_bytes() == gen_bytes and JSON.read_bytes() == json_bytes
                and REPORT.read_bytes() == report_bytes)
        lines.append("")
        lines.append("=== 还原后 GREEN 对照 ===")
        lines.append(f"重生成 exit = {rc3}；三件字节还原一致 = {same}")
        rc4, out4 = pytest_node()
        lines.append(f"pytest exit = {rc4}（期望 0 = GREEN）")
        lines.extend(l.strip()[:160] for l in out4.splitlines()
                     if any(k in l for k in ("passed", "failed")))
        if rc4 != 0 or not same:
            lines.append("!! 还原后未绿或字节不一致")
            ok = False
        else:
            lines.append("OK：恢复绿")
    finally:
        GEN.write_bytes(gen_bytes)
        JSON.write_bytes(json_bytes)
        REPORT.write_bytes(report_bytes)
    lines.append("")
    lines.append(f"===== 结论：{'全部通过' if ok else '失败'} =====")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-8:]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
