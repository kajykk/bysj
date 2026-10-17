"""P2-35 第三十三批变异验证（1 接线批，7 条变异）。

验证对象：本批新增判据是否**真能翻转**（不是换个同样假绿的写法）。

M1 删 `_validate_mime_type` 的 `record_silent_degradation` 调用
   → location 字面量钉 + 块级钉必须红（本批唯一接线点）
M2 给 `fire_forget_metrics.record_scheduled` 的 handler 接线
   → 块级反向钉必须红（同源失效路径接线即假设施）
M3 location 改 typo（`validate_mime_typo`）
   → 完整字面量钉必须红（第二十六批 `_typo` 型变异的常规复查）
M4 把 `_validate_mime_type` 的降级 `return` 改成 `raise`（fail-open→fail-closed）
   → E1 同形性必须红（接线判据本身的反证）
M5 把 `pdf_job_store._cleanup_expired` 的 `continue` 改成 `break`
   → E4 混合输入必须红（第二十九批 M3 假绿事故：单脏值分不出二者）
M6 删 `email_service._send_smtp` 末尾的 `raise last_exc`
   → E5 必须红（V 型判据：失败必须向上传播）
M7 删 P2_13「一之三十四」节标题
   → 文档登记必须红

纪律：锚点先读实际落盘文本；`mutate()` 用 try/finally 保证**无论 RED 还是
假绿都还原**；日志落盘（须 git add -f）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
UU = BACKEND / "app" / "api" / "v1" / "user_upload.py"
FFM = BACKEND / "app" / "core" / "fire_forget_metrics.py"
PJS = BACKEND / "app" / "services" / "pdf_job_store.py"
MAIL = BACKEND / "app" / "services" / "email_service.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch33Wiring",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b33mut",
]


def run_gate() -> int:
    """跑批次闸门类，返回 returncode（0 = 通过）。"""
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, *TARGETS],
        cwd=BACKEND, capture_output=True, text=True, timeout=1200,
    )
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]
    print("    gate:", tail[-1] if tail else proc.stdout[-200:])
    return proc.returncode


def mutate(label: str, path: pathlib.Path, old: str, new: str) -> None:
    original = path.read_text(encoding="utf-8")
    assert old in original, (
        f"{label}: 锚点不在落盘文本中（先读实际文本再写脚本）: {old[:70]!r}"
    )
    assert original.count(old) == 1, f"{label}: 锚点不唯一（{original.count(old)} 处）"
    print(f"  [{label}] 变异注入…")
    path.write_text(new.join(original.split(old)), encoding="utf-8")
    try:
        rc = run_gate()
        assert rc != 0, f"{label}: 变异态闸门仍绿（returncode=0）—— 断言假绿！"
        print(f"  [{label}] RED-OK（returncode={rc}）")
    finally:
        # 无论 RED/假绿都必须还原：残留变异会污染后续批次的工作树
        path.write_text(original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, f"{label}: 还原态闸门仍红（returncode={rc2}）—— 还原不完整！"
    print(f"  [{label}] GREEN-OK（还原后 returncode=0）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第三十三批变异验证（user_upload._validate_mime_type 接线批）")
    print("=" * 72)

    print("  [baseline] 变异前闸门应为绿…")
    base_rc = run_gate()
    assert base_rc == 0, f"baseline 应为绿，实际 returncode={base_rc}"
    print("  [baseline] GREEN-OK\n")

    # M1：删除本批唯一接线
    mutate(
        "M1 删接线",
        UU,
        '        record_silent_degradation("api.user_upload.validate_mime_type")\n',
        "",
    )

    # M2：给同源失效的可观测设施路径接线（假设施）
    mutate(
        "M2 给 fire_forget 接线",
        FFM,
        '        logger.debug("fire_forget record_scheduled failed: %s", exc)',
        '        logger.debug("fire_forget record_scheduled failed: %s", exc)\n'
        '        from app.core.degradation import record_silent_degradation\n'
        '        record_silent_degradation("core.fire_forget_metrics.record_scheduled")',
    )

    # M3：location typo
    mutate(
        "M3 location typo",
        UU,
        'record_silent_degradation("api.user_upload.validate_mime_type")',
        'record_silent_degradation("api.user_upload.validate_mime_typo")',
    )

    # M4：fail-open → fail-closed（破坏同形性）
    mutate(
        "M4 降级态改抛异常",
        UU,
        '        record_silent_degradation("api.user_upload.validate_mime_type")\n        return',
        '        record_silent_degradation("api.user_upload.validate_mime_type")\n        raise HTTPException(status_code=500, detail="mime check unavailable")',
    )

    # M5：脏数据破坏性中止
    mutate(
        "M5 continue→break",
        PJS,
        "            except (ValueError, TypeError):\n                continue",
        "            except (ValueError, TypeError):\n                break",
    )

    # M6：V 型传播被吞
    mutate(
        "M6 删 raise last_exc",
        MAIL,
        "        if last_exc:\n            raise last_exc",
        "        if last_exc:\n            logger.error('swallowed: %s', last_exc)",
    )

    # M7：删文档节标题
    mutate(
        "M7 删节标题",
        DOC13,
        "## 一之三十四、#35 X 桶第三十三批",
        "## 一之三十四（已删除标题标记）、#35 X 桶第三十三批",
    )

    print("\n7 条变异全部 RED → 还原后 GREEN。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
