"""CI 专用脚本：创建数据库 schema，带有详细诊断输出。

在 CI 环境中用于替代 alembic 迁移，直接用 Base.metadata.create_all() 创建表。
失败时将错误信息输出到 stdout、stderr 和 GITHUB_STEP_SUMMARY。

用法:
    python scripts/create_schema_ci.py

环境变量:
    DATABASE_URL: 数据库连接字符串 (必须)
    GITHUB_STEP_SUMMARY: GitHub Actions 自动设置 (可选)
"""
import os
import sys
import traceback

# 将 backend 目录添加到 sys.path，使 app 包可导入
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def main():
    try:
        # Step 1: 测试 psycopg2 导入
        import psycopg2
        print(f"psycopg2 version: {psycopg2.__version__}")

        # Step 2: 测试 Settings 初始化 (会触发 model_validator)
        from app.core.config import settings
        print(f"Settings OK, app_env: {settings.app_env}")

        # Step 3: 测试数据库连接
        from sqlalchemy import create_engine, text
        url = os.environ["DATABASE_URL"]
        print(f"Connecting to: {url}")
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("DB connection OK")

        # Step 4: 创建表
        from app.models import Base
        Base.metadata.create_all(engine)
        print(f"Schema created: {len(Base.metadata.tables)} tables")

    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        # 输出到 GITHUB_STEP_SUMMARY (无需 admin 权限即可在 Summary 页面查看)
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("## Create database schema FAILED\n\n")
                f.write("```\n")
                f.write(err)
                f.write("```\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
