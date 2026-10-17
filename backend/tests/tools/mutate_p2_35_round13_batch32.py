"""P2-35 第三十二批变异验证（1 接线批，5 条变异）。

验证对象：本批新增的判据是否**真能翻转**（不是换个同样假绿的写法）。

M1 删 `_load_json` 的 `record_silent_degradation` 调用
   → location 字面量钉 + 块级钉必须红（本批唯一的接线点）
M2 给 `celery_breaker` 的 `except ImportError: pass` 接线
   → 块级反向钉必须红（不可达路径接线即假设施）
M3 把 `_load_json` 的 except 改成 `raise`（破坏「损坏 ⇒ None」的同形性）
   → E3 运行时断言必须红（这是接线判据本身的反证）
M4 把 `user_data_service` 某处脏数据 handler 的 `pass` 改成 `break`
   → E2 混合输入必须红（单脏值用例分不出 continue/break，见第二十九批 M3 事故）
M5 删 P2_13「一之三十三」节标题
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
MH = BACKEND / "app" / "api" / "v1" / "metrics_helpers.py"
CB = BACKEND / "app" / "core" / "celery_breaker.py"
UDS = BACKEND / "app" / "services" / "user_data_service.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch32Wiring",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b32mut",
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
    print("P2-35 第三十二批变异验证（metrics_helpers._load_json 接线批）")
    print("=" * 72)

    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿—— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：删掉 _load_json 的接线调用
    m1_old = '            record_silent_degradation("api.metrics_helpers.load_json")\n'
    m1_new = "            # MUTATION: 接线被删\n"
    mutate("M1 删 _load_json 的接线", MH, m1_old, m1_new)

    # M2：给 celery_breaker 的 kombu ImportError 接线（不可达路径假设施）
    m2_old = (
        "    try:\n"
        "        from kombu.exceptions import OperationalError as KombuOperationalError\n"
        "\n"
        "        exceptions.append(KombuOperationalError)\n"
        "    except ImportError:\n"
        "        pass\n"
    )
    m2_new = (
        "    try:\n"
        "        from kombu.exceptions import OperationalError as KombuOperationalError\n"
        "\n"
        "        exceptions.append(KombuOperationalError)\n"
        "    except ImportError:\n"
        "        # MUTATION: 给不可达路径接线\n"
        "        record_silent_degradation(\"core.celery_breaker.kombu_missing\")\n"
    )
    mutate("M2 给 celery_breaker 的 ImportError 接线", CB, m2_old, m2_new)

    # M3：破坏「损坏产物 ⇒ 返回 None」的同形性
    m3_old = (
        "        except (OSError, json.JSONDecodeError) as exc:\n"
        "            logger.warning(\"读取指标产物失败: %s error=%s\", path, exc)\n"
    )
    m3_new = (
        "        except (OSError, json.JSONDecodeError) as exc:\n"
        "            logger.warning(\"读取指标产物失败: %s error=%s\", path, exc)\n"
        "            raise  # MUTATION: 不再静默同形\n"
    )
    mutate("M3 _load_json 改为向外抛（破坏同形性）", MH, m3_old, m3_new)

    # M4：脏数据 handler 的 pass → break
    m4_old = (
        "                    except (TypeError, ValueError):\n"
        "                        pass\n"
        "            elif key == \"heart_rate\":\n"
    )
    m4_new = (
        "                    except (TypeError, ValueError):\n"
        "                        break  # MUTATION: 一个脏字段掐掉整个循环\n"
        "            elif key == \"heart_rate\":\n"
    )
    mutate("M4 user_data_service 脏数据 pass → break", UDS, m4_old, m4_new)

    # M5：删 P2_13 第三十二批节标题
    m5_old = "## 一之三十三、#35 X 桶第三十二批："
    m5_new = "## 一之三十三（MUTATION 已删标题前缀）、#35 X 桶第三十二批："
    mutate("M5 删 P2_13 第三十二批节标题", DOC13, m5_old, m5_new)

    print("=" * 72)
    print("五条变异全部 RED-OK / GREEN-OK")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
