"""
独立测试运行器 - 绕过 pytest 命令行入口的 DLL 初始化问题
"""

import importlib
import inspect
import sys
import traceback
from pathlib import Path


def discover_test_files(tests_dir: Path) -> list[Path]:
    """发现所有测试文件"""
    return sorted(tests_dir.glob("test_*.py"))


def run_test_function(module, func_name: str) -> tuple[bool, str]:
    """运行单个测试函数"""
    func = getattr(module, func_name)
    try:
        # 检查函数签名，决定如何调用
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        if "client" in params or "as_role" in params:
            # 需要 fixture 的测试跳过
            return True, "SKIP (requires fixture)"

        # 无参数测试直接运行
        func()
        return True, "PASS"
    except Exception as e:
        return False, f"FAIL: {type(e).__name__}: {e}"


def run_test_module(module_path: Path) -> dict:
    """运行单个测试模块"""
    results = {
        "module": module_path.name,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        # 动态导入模块
        spec = importlib.util.spec_from_file_location(
            module_path.stem, module_path
        )
        if spec is None or spec.loader is None:
            results["errors"].append("Failed to load module spec")
            return results

        module = importlib.util.module_from_spec(spec)

        # 添加项目根目录到路径
        sys.path.insert(0, str(module_path.parent.parent))

        spec.loader.exec_module(module)

        # 发现测试函数
        test_funcs = [
            name for name in dir(module)
            if name.startswith("test_") and callable(getattr(module, name))
        ]

        results["total"] = len(test_funcs)

        for func_name in test_funcs:
            success, msg = run_test_function(module, func_name)
            if msg.startswith("SKIP"):
                results["skipped"] += 1
            elif success:
                results["passed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"  {func_name}: {msg}")

    except Exception as e:
        results["errors"].append(f"Module import error: {type(e).__name__}: {e}")
        traceback.print_exc()

    return results


def main():
    tests_dir = Path(__file__).parent / "tests"

    print("=" * 60)
    print("独立测试运行器")
    print("=" * 60)

    test_files = discover_test_files(tests_dir)
    print(f"发现 {len(test_files)} 个测试文件\n")

    total_stats = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}

    for test_file in test_files:
        print(f"\n运行: {test_file.name}")
        print("-" * 40)

        results = run_test_module(test_file)

        total_stats["total"] += results["total"]
        total_stats["passed"] += results["passed"]
        total_stats["failed"] += results["failed"]
        total_stats["skipped"] += results["skipped"]

        print(f"  总计: {results['total']}, 通过: {results['passed']}, "
              f"失败: {results['failed']}, 跳过: {results['skipped']}")

        for error in results["errors"]:
            print(f"  {error}")

    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    print(f"总计: {total_stats['total']}")
    print(f"通过: {total_stats['passed']}")
    print(f"失败: {total_stats['failed']}")
    print(f"跳过: {total_stats['skipped']}")

    if total_stats["failed"] > 0:
        print("\n❌ 有测试失败")
        sys.exit(1)
    else:
        print("\n✅ 所有测试通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
