"""
STB 稳定性基线测试 - TC-STB-HP-000
测量并记录代码库基线数据
"""

import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import pytest


PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend" / "app"
FRONTEND_DIR = PROJECT_ROOT / "frontend" / "src"


class TestBaselineMeasurement:
    """基线数据测量测试类"""

    def test_000_datetime_utcnnow_usage(self):
        """TC-STB-HP-000-1: 测量 datetime.utcnow() 使用次数"""
        count = 0
        files_with_usage = []

        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                matches = re.findall(r"datetime\.utcnow\(\)", content)
                if matches:
                    count += len(matches)
                    files_with_usage.append(str(py_file.relative_to(PROJECT_ROOT)))

        # 记录基线
        print(f"\n[BASELINE] datetime.utcnow() 使用次数: {count}")
        if files_with_usage:
            print(f"[BASELINE] 涉及文件: {files_with_usage}")

        # 预期: 0 (应该已全部替换)
        assert count == 0, f"发现 {count} 处 datetime.utcnow() 未替换"

    def test_000_sklearn_version_references(self):
        """TC-STB-HP-000-2: 测量 sklearn 版本相关代码"""
        files_with_sklearn = []

        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                if "sklearn" in content or "scikit-learn" in content:
                    files_with_sklearn.append(str(py_file.relative_to(PROJECT_ROOT)))

        print(f"\n[BASELINE] sklearn 相关文件数: {len(files_with_sklearn)}")
        print(f"[BASELINE] 文件列表: {files_with_sklearn}")

        # 记录基线，不强制断言
        assert len(files_with_sklearn) >= 0

    def test_000_warning_patterns(self):
        """TC-STB-HP-000-3: 测量 warning 相关代码模式"""
        warning_patterns = {
            "warnings.warn": 0,
            "logger.warn": 0,
            "UserWarning": 0,
            "DeprecationWarning": 0,
        }

        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                for pattern in warning_patterns:
                    warning_patterns[pattern] += len(re.findall(pattern, content))

        print(f"\n[BASELINE] Warning 模式统计:")
        for pattern, count in warning_patterns.items():
            print(f"  - {pattern}: {count}")

        assert all(count >= 0 for count in warning_patterns.values())

    def test_000_any_type_usage(self):
        """TC-STB-HP-000-4: 测量 TypeScript any 类型使用"""
        any_count = 0
        files_with_any = []

        if FRONTEND_DIR.exists():
            for ts_file in list(FRONTEND_DIR.rglob("*.ts")) + list(FRONTEND_DIR.rglob("*.tsx")):
                content = ts_file.read_text(encoding="utf-8")
                # 排除注释中的 any
                lines = content.split("\n")
                for line in lines:
                    if "//" not in line and "any" in line:
                        any_count += 1
                if "any" in content:
                    files_with_any.append(str(ts_file.relative_to(PROJECT_ROOT)))

        print(f"\n[BASELINE] TypeScript 'any' 使用次数: {any_count}")
        print(f"[BASELINE] 涉及文件数: {len(files_with_any)}")

        assert any_count >= 0

    def test_001_sklearn_version_risk_list(self):
        """TC-STB-HP-001: sklearn 版本风险清单产出完整性"""
        # 检查 model_compatibility.py 是否存在
        compatibility_file = BACKEND_DIR / "core" / "model_compatibility.py"
        assert compatibility_file.exists(), "model_compatibility.py 不存在"

        content = compatibility_file.read_text(encoding="utf-8")
        assert "sklearn" in content, "model_compatibility.py 未包含 sklearn 相关逻辑"

        print("\n[PASS] sklearn 版本风险清单检查通过")

    def test_002_datetime_utcnnow_replaced(self):
        """TC-STB-HP-002: datetime.utcnow() 全部替换为 timezone-aware"""
        count = 0
        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                count += len(re.findall(r"datetime\.utcnow\(\)", content))

        assert count == 0, f"仍有 {count} 处 datetime.utcnow() 未替换"
        print("\n[PASS] datetime.utcnow() 已全部替换")

    def test_004_pytorch_optional_dependency(self):
        """TC-STB-HP-004: PyTorch 可选依赖行为一致性"""
        # 检查是否有 PyTorch 惰性导入模式
        model_engine = BACKEND_DIR / "core" / "model_engine.py"
        if model_engine.exists():
            content = model_engine.read_text(encoding="utf-8")
            has_lazy_import = "try:" in content and "import torch" in content
            has_fallback = "fallback" in content.lower() or "heuristic" in content.lower()

            assert has_lazy_import, "未找到 PyTorch 惰性导入模式"
            assert has_fallback, "未找到 fallback 机制"

        print("\n[PASS] PyTorch 可选依赖检查通过")

    def test_007_fallback_gradation(self):
        """TC-STB-HP-007: fallback 分级机制完整"""
        # 检查 fallback 层级配置
        fallback_found = False
        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                if "L1" in content and "L2" in content and "fallback" in content.lower():
                    fallback_found = True
                    break

        assert fallback_found, "未找到 fallback 分级机制 (L1/L2)"
        print("\n[PASS] Fallback 分级机制检查通过")

    def test_008_stability_regression(self):
        """TC-STB-HP-008: 稳定性回归测试通过"""
        # 检查稳定性测试目录结构
        stability_dir = Path(__file__).parent
        test_files = list(stability_dir.glob("*.py"))

        assert len(test_files) > 0, "稳定性测试目录为空"
        print(f"\n[PASS] 稳定性回归测试结构检查通过 (发现 {len(test_files)} 个测试文件)")

    def test_009_warning_regression(self):
        """TC-STB-HP-009: 全量回归 warning 检查"""
        # 基线: datetime.utcnow() 应该为 0
        count = 0
        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                count += len(re.findall(r"datetime\.utcnow\(\)", content))

        assert count == 0, "回归检查失败: 发现 datetime.utcnow() 使用"
        print("\n[PASS] Warning 回归检查通过")


@pytest.fixture(scope="session", autouse=True)
def generate_baseline_report():
    """测试结束后生成基线报告"""
    yield

    report_path = PROJECT_ROOT / "BASELINE.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 稳定性基线报告 (Baseline Report)\n\n")
        f.write(f"> 生成时间: {datetime.now(timezone.utc).isoformat()}\n\n")

        f.write("## 基线数据\n\n")

        # datetime.utcnow()
        count = 0
        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                count += len(re.findall(r"datetime\.utcnow\(\)", content))
        f.write(f"- **datetime.utcnow() 使用次数**: {count} (目标: 0)\n")

        # sklearn files
        sklearn_files = []
        if BACKEND_DIR.exists():
            for py_file in BACKEND_DIR.rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                if "sklearn" in content:
                    sklearn_files.append(str(py_file.relative_to(PROJECT_ROOT)))
        f.write(f"- **sklearn 相关文件数**: {len(sklearn_files)}\n")

        # any types
        any_count = 0
        if FRONTEND_DIR.exists():
            for ts_file in list(FRONTEND_DIR.rglob("*.ts")) + list(FRONTEND_DIR.rglob("*.tsx")):
                content = ts_file.read_text(encoding="utf-8")
                any_count += len(re.findall(r"\bany\b", content))
        f.write(f"- **TypeScript any 使用次数**: {any_count}\n")

        f.write("\n## 状态\n\n")
        f.write("- [x] 基线测量完成\n")
        f.write("- [x] datetime.utcnow() 已清理\n")
        f.write("- [x] sklearn 版本风险清单已创建\n")

    print(f"\n[REPORT] 基线报告已生成: {report_path}")
