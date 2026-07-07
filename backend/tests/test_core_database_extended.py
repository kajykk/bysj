"""Extended tests for app/core/database module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.database import AsyncSessionLocal, engine, get_db


class TestDatabaseInit:
    """Test database initialization."""

    @pytest.mark.asyncio
    async def test_init_db(self):
        """TC-COV-012: init_db executes without error."""
        with patch("app.core.database.engine", new=MagicMock()) as mock_engine:
            mock_conn = AsyncMock()
            mock_conn.run_sync = AsyncMock()
            mock_engine.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_conn
            )
            mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

            from app.core.database import init_db

            await init_db()
            mock_engine.begin.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_db(self):
        """TC-COV-013: close_db disposes engine."""
        with patch("app.core.database.engine", new=MagicMock()) as mock_engine:
            mock_engine.dispose = AsyncMock()
            from app.core.database import close_db

            await close_db()
            mock_engine.dispose.assert_called_once()


class TestGetDb:
    """Test get_db dependency."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """TC-COV-014: get_db yields an async session."""
        mock_session = AsyncMock()
        mock_session.close = AsyncMock()

        with patch("app.core.database.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

            gen = get_db()
            session = await gen.__anext__()
            assert session is mock_session

            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass


class TestEngineConfiguration:
    """Test engine configuration."""

    def test_engine_exists(self):
        """TC-COV-015: engine is created."""
        assert engine is not None

    def test_async_session_local_exists(self):
        """TC-COV-016: AsyncSessionLocal is created."""
        assert AsyncSessionLocal is not None
