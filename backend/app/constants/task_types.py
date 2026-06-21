from __future__ import annotations

from pathlib import Path
import json

TASK_TYPES: tuple[str, ...] = tuple(json.loads(Path(__file__).resolve().parents[3].joinpath('common', 'task-types.json').read_text(encoding='utf-8')))
TASK_TYPE_SET: frozenset[str] = frozenset(TASK_TYPES)
