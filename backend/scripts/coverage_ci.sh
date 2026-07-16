#!/usr/bin/env bash
# 稳定 CI 全量覆盖率复测 (ISS-02 绝对覆盖% / ISS-08 分支覆盖)
#
# 依赖仓库 pytest.ini 的 addopts（已含 --cov=app --cov-report=term-missing
# --cov-report=xml:coverage.xml --ignore=functional_test.py 与 asyncio_mode=auto）。
# 此处仅把 --cov-fail-under 降到 0，目的是“测量”而非“强制通过”。
#
# 重要：本地 Windows 下 numpy 链模块（validation_engine / risk_service_assessment，
# 经 app.services.__init__ 急切重导出 drift_detector -> numpy）在 coverage 插桩时
# 会确定性 SIGSEGV（C-tracer 与 COVERAGE_CORE=sysmon 均复现，原生库冲突，非代码缺陷）。
# 该问题在 Linux CI 不出现；若个别环境仍复现，可临时排除这两模块或设 COVERAGE_CORE=sysmon。
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pytest --cov-fail-under=0 -q
