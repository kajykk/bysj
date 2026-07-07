from __future__ import annotations

import logging
from logging.config import fileConfig
from urllib.parse import urlparse, urlunparse

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import Base

config = context.config
sync_db_url = settings.database_url
if "+asyncpg" in sync_db_url:
    sync_db_url = sync_db_url.replace("+asyncpg", "+psycopg2")
if "+aiosqlite" in sync_db_url:
    sync_db_url = sync_db_url.replace("+aiosqlite", "")
config.set_main_option("sqlalchemy.url", sync_db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ISS-049 修复：对数据库 URL 做脱敏处理，防止含凭据的 URL 被日志记录
# 仅用于日志显示，不影响实际连接（实际 URL 已通过 config.set_main_option 设置）
logger = logging.getLogger("alembic.env")


def _mask_db_url(url: str) -> str:
    """脱敏数据库 URL，将 password 部分替换为 ***，仅用于日志显示.

    示例:
        postgresql://user:secret@host:5432/db
        → postgresql://user:***@host:5432/db
    """
    try:
        parsed = urlparse(url)
        if parsed.password is None:
            return url
        # 重建 URL，将 password 替换为 ***
        masked_netloc = parsed.hostname or ""
        if parsed.port:
            masked_netloc = f"{masked_netloc}:{parsed.port}"
        if parsed.username:
            masked_netloc = f"{parsed.username}:***@{masked_netloc}"
        return urlunparse(parsed._replace(netloc=masked_netloc))
    except Exception:
        # 解析失败时返回占位符，避免泄露原始 URL
        return "<unparseable-db-url>"


logger.info("Alembic using database URL: %s", _mask_db_url(sync_db_url))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
