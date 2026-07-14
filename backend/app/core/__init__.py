"""Core infrastructure package: config / db / security / middlewares / model engine.

MAINT-P2-003: 显式 __init__.py 让 app.core 成为常规包, 便于 import-linter 静态分析
层级依赖契约 (app.core 不应反向依赖 app.ml / app.services)。
"""
