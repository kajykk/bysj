"""Tests for database module."""

from __future__ import annotations

import pytest

from app.core.database import AsyncSessionLocal, close_db, engine, get_db, init_db


class TestDatabase:
    """Test database functions."""

    @pytest.mark.asyncio
    async def test_init_db(self):
        """TC-COV-DB-001: init_db runs without error."""
        await init_db()

    @pytest.mark.asyncio
    async def test_close_db(self):
        """TC-COV-DB-002: close_db runs without error."""
        await close_db()

    @pytest.mark.asyncio
    async def test_get_db(self):
        """TC-COV-DB-003: get_db yields a session."""
        async for session in get_db():
            assert session is not None
            break

    def test_engine_created(self):
        """TC-COV-DB-004: Engine is created."""
        assert engine is not None

    def test_async_session_local(self):
        """TC-COV-DB-005: AsyncSessionLocal is created."""
        assert AsyncSessionLocal is not None
