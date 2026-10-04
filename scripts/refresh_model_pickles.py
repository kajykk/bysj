"""用当前 sklearn 重新持久化模型工件，消除跨版本反序列化的 InconsistentVersionWarning。

为什么是「重新持久化」而不是「重训」:
    问题定义是「工件由 sklearn 1.7.2 序列化、运行库 1.8.0」的**序列化版本差**，
    不是模型参数过时。重训会用新库重新拟合 -> 改变模型参数与指标（可能更好也可能更差）；
    本脚本只做 load -> 逐位校验 -> re-dump，**参数一字不改**，仅更新序列化元数据。

⚠️ 加载路径陷阱（2026-10-04 实测）:
    `app/core/model_engine/loading.py` 用相对路径 `..\\models\\...`；cwd=backend 时
    `_abs_path` 会**先命中仓库根 models/**，而不是 backend/models。本轮实测运行时
    加载的是根 `models/text/improved_bilingual_*.pkl`（1.7.2 产物），
    而 `backend/models/text/` 下另有尺寸不同、无版本差的副本。
    **体检/重写时必须用 --model-dir 指定到实际被加载的那份**，否则会漏掉真凶。

安全设计:
    1. 每个文件用**独立 subprocess** 检测，避开 Python 的 warning 去重（同一位置同消息
       只报一次）造成的「第一个之后全假阴性」；
    2. 动前备份到 <model-dir>/_archive/pre-redump-<ts>/；
    3. re-dump 前后**逐位比较全部数组属性 + get_params()**，任何一处不等立即还原并中止；
    4. 重写后重新生成 .sha256 侧车（哈希必然变化，否则侧车校验会失败）；
    5. 默认只体检，必须 --apply 才写盘。

用法:
    cd backend
    .venv/Scripts/python.exe ../scripts/refresh_model_pickles.py --model-dir ../models/text
    .venv/Scripts/python.exe ../scripts/refresh_model_pickles.py --model-dir ../models/text --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
DEFAULT_MODEL_DIR = BACKEND / "models"

import joblib  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.base import BaseEstimator  # noqa: E402


def detect_version_diff(path: Path) -> list[str]:
    """在独立子进程中加载, 收集版本差消息（避开 warning 去重造成的假阴性）。"""
    code = (
        "import warnings, joblib, json\n"
        "with warnings.catch_warnings(record=True) as caught:\n"
        "    warnings.simplefilter('always')\n"
        f"    joblib.load(r'{path}')\n"
        "msgs = sorted({str(w.message) for w in caught\n"
        "               if 'InconsistentVersion' in type(w.message).__name__\n"
        "               or 'from version' in str(w.message)})\n"
        "print('__MSGS__' + json.dumps(msgs))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = proc.stdout or ""
    if proc.returncode != 0 or "__MSGS__" not in out:
        raise RuntimeError((proc.stderr or out)[-160:])
    for line in out.splitlines():
        if line.startswith("__MSGS__"):
            return json.loads(line[len("__MSGS__"):])
    return []


def numeric_fingerprint(obj: object) -> dict:
    fp: dict[str, object] = {}
    for attr in dir(obj):
        if attr.startswith("__"):
            continue
        try:
            val = getattr(obj, attr)
        except Exception:
            continue
        if callable(val):
            continue
        if isinstance(val, np.ndarray):
            fp[attr] = ("ndarray", val.dtype.str, val.shape, val.tobytes())
        elif isinstance(val, (int, float, str, bool, bytes, type(None))):
            fp[attr] = ("scalar", repr(val))
        elif isinstance(val, dict) and len(val) <= 2000:
            fp[attr] = ("dict", repr(sorted(val.items(), key=lambda kv: str(kv[0]))))
        elif isinstance(val, (list, tuple)) and len(val) <= 2000:
            fp[attr] = ("seq", repr(list(val)))
    if isinstance(obj, BaseEstimator):
        fp["__params__"] = ("dict", repr(sorted(obj.get_params().items(), key=lambda kv: kv[0])))
    return fp


def compare(fp_a: dict, fp_b: dict) -> list[str]:
    return sorted(k for k in set(fp_a) | set(fp_b) if fp_a.get(k) != fp_b.get(k))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=str, default=str(DEFAULT_MODEL_DIR),
                    help="工件目录（默认 backend/models；实际加载的可能是仓库根 models/，见文件头说明）")
    ap.add_argument("--apply", action="store_true", help="实际重写（默认只体检）")
    args = ap.parse_args()

    root = Path(args.model_dir).resolve()
    sys.path.insert(0, str(BACKEND))
    pkls = [p for p in root.rglob("*.pkl") if "_archive" not in p.parts]
    print(f"扫描 {len(pkls)} 个工件: {root}\n")

    stale, clean, errors = [], [], []
    for p in sorted(pkls):
        rel = str(p.relative_to(root))
        try:
            msgs = detect_version_diff(p)
        except Exception as e:
            errors.append((rel, f"{type(e).__name__}: {str(e)[:70]}"))
            print(f"  [ERROR] {rel}: {type(e).__name__} {str(e)[:70]}")
            continue
        if msgs:
            stale.append(p)
            print(f"  [版本差] {rel}")
            print(f"           {msgs[0][:110]}")
        else:
            clean.append(rel)
    print(f"\n无版本差 {len(clean)} | 有版本差 {len(stale)} | 加载失败 {len(errors)}")

    if not stale:
        print("没有需要重持久化的工件。")
        return
    if not args.apply:
        print("\n[DRY-RUN] 加 --apply 才实际写盘。")
        return

    backup = root / "_archive" / f"pre-redump-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    backup.mkdir(parents=True, exist_ok=True)
    done, failed = [], []
    for p in stale:
        rel = str(p.relative_to(root))
        try:
            obj = joblib.load(p)
            before = numeric_fingerprint(obj)
            shutil.copy2(p, backup / p.name)
            side = p.with_suffix(p.suffix + ".sha256")
            if side.exists():
                shutil.copy2(side, backup / side.name)
            joblib.dump(obj, p)
            obj2 = joblib.load(p)
            diffs = compare(before, numeric_fingerprint(obj2))
            if diffs:
                shutil.copy2(backup / p.name, p)
                failed.append((rel, f"逐位比对不一致 -> 已还原: {diffs[:3]}"))
                continue
            from app.utils.checksum import write_sha256_sidecar

            write_sha256_sidecar(p)
            left = detect_version_diff(p)
            print(f"  [OK] {rel} — 参数逐位一致, 侧车已重生成, "
                  f"{'warning 已消除' if not left else '仍有提示: ' + left[0][:60]}")
            done.append(rel)
        except Exception as e:
            failed.append((rel, f"{type(e).__name__}: {str(e)[:80]}"))
            print(f"  [FAIL] {rel}: {type(e).__name__} {str(e)[:80]}")

    print(f"\n完成 {len(done)} 个；失败 {len(failed)} 个")
    for rel, reason in failed:
        print(f"  FAIL {rel}: {reason}")
    print(f"备份目录: {backup}")


if __name__ == "__main__":
    main()
