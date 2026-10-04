"""把数据库中种子账号的密码哈希同步为当前 .env 里的 E2E_*_PASSWORD.

为什么需要它
------------
``app/core/seed.py::_seed_users`` 是 **create-if-absent**：

    for item in desired_users:
        if item["username"] in user_map:
            continue            # seed.py:630-632

因此轮换 ``.env`` 里的 ``E2E_ADMIN_PASSWORD`` 之后，**已存在账号的密码哈希不会
跟着更新**。现象是「明明改了 .env，却还是登录不上」——很容易被误判成「配置没生效」
或「轮换没做成」。

用法
----
    python scripts/rotate_seed_passwords.py            # 默认 dry-run：只报告将要改什么
    python scripts/rotate_seed_passwords.py --apply    # 实际更新并提交

约束
----
- **默认不改任何数据**（沿用本项目对运维脚本的 dry-run 约定）；
- 只处理种子账号（``admin`` + seed 清单里的咨询师 / 普通用户），不做全表更新；
- **不打印任何口令值**。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash, verify_password  # noqa: E402
from app.core.seed import (  # noqa: E402
    _COUNSELOR_SEED_DATA,
    _E2E_ADMIN_PASSWORD,
    _E2E_COUNSELOR_PASSWORD,
    _E2E_USER_PASSWORD,
    _USER_SEED_DATA,
)
from app.models.user import User  # noqa: E402


def _targets() -> dict[str, str]:
    """返回 username -> 期望口令。值只用于比对/写入，不打印。"""
    targets: dict[str, str] = {}
    if _E2E_ADMIN_PASSWORD:
        targets["admin"] = _E2E_ADMIN_PASSWORD
    if _E2E_COUNSELOR_PASSWORD:
        for item in _COUNSELOR_SEED_DATA:
            targets[item["username"]] = _E2E_COUNSELOR_PASSWORD
    if _E2E_USER_PASSWORD:
        for item in _USER_SEED_DATA:
            targets[item["username"]] = _E2E_USER_PASSWORD
    return targets


async def _sync(apply: bool) -> int:
    targets = _targets()
    if not targets:
        print("E2E_*_PASSWORD 未配置 —— 无从同步。请先在 .env 里设置。", file=sys.stderr)
        return 2

    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    already: list[str] = []
    to_update: list[str] = []
    missing: list[str] = []

    try:
        async with session_factory() as db:
            rows = (
                (await db.execute(select(User).where(User.username.in_(list(targets)))))
                .scalars()
                .all()
            )
            by_name = {u.username: u for u in rows}

            for name, password in targets.items():
                user = by_name.get(name)
                if user is None:
                    missing.append(name)
                    continue
                if verify_password(password, user.password_hash):
                    already.append(name)
                    continue
                to_update.append(name)
                if apply:
                    user.password_hash = get_password_hash(password)

            if apply and to_update:
                await db.commit()
    finally:
        await engine.dispose()

    print(f"数据库      : {settings.database_url}")
    print(f"种子账号总数: {len(targets)}")
    print(f"  已是当前口令（跳过）: {len(already)}  {already}")
    print(f"  需要更新            : {len(to_update)}  {to_update}")
    print(f"  数据库中不存在      : {len(missing)}  {missing}")
    if missing:
        print("  （不存在的账号会在下次 seed 时创建，无需手工补）")
    if not apply:
        print()
        print("这是 dry-run，未改动任何数据。加 --apply 才会实际写入。")
    elif to_update:
        print()
        print(f"已更新 {len(to_update)} 个账号的密码哈希。")
    else:
        print()
        print("无需更新。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="同步种子账号密码哈希到当前 .env 的 E2E_*_PASSWORD"
    )
    parser.add_argument(
        "--apply", action="store_true", help="实际写入（默认只做 dry-run 报告）"
    )
    args = parser.parse_args()
    return asyncio.run(_sync(apply=args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
