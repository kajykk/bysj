"""ROUND_18 · T3（审查报告 M6）：验证任务 ``created_by`` 类型漂移。

缺陷原文（§2.2 M6）：写入侧 ``"created_by": str(current_user.id)``，
消费侧 ``job.get("created_by") != str(current_user.id)``，而 Redis 反序列化
``_deserialize_dict`` 把该字段转成 ``int`` ⇒ ``5 != "5"`` 恒真 ⇒ 生产默认的
Redis 模式下，创建者查不到自己的任务，且错误信息是误导性的"任务不存在"。

判据：
1. ``_serialize → _deserialize_dict`` 往返后 ``created_by`` 仍是字符串；
2. 走**真实** ``ValidationJobStore``（create / get / list_jobs），只把外部
   Redis 换成一个内存字典替身 —— 缺陷在序列化边界（真实代码），不在被替换的
   Redis 客户端；
3. 三条消费点判据（详情 / 结果 / 列表）都用端点里同一句
   ``job.get("created_by") != str(user_id)`` 求值，确认不再误判。
"""

from __future__ import annotations

import pytest

from app.api.v1.validation import ValidationJobStore


class _FakeRedis:
    """只实现 ValidationJobStore 用到的方法（Hash + Set 语义）。"""

    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.hashes.setdefault(key, {}).update(mapping)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def sadd(self, key: str, *values: str) -> None:
        self.sets.setdefault(key, set()).update(values)

    async def srem(self, key: str, *values: str) -> None:
        self.sets.get(key, set()).difference_update(values)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))

    async def delete(self, key: str) -> None:
        self.hashes.pop(key, None)


def _job_payload(user_id: int) -> dict:
    """与 ``/validation/run`` 写入的字段同形（created_by 是 str）。"""
    return {
        "id": "job-r18-1",
        "status": "queued",
        "model_version": "v1",
        "dataset_path": "/tmp/data.csv",
        "baseline_version": None,
        "baseline_dataset_path": None,
        "created_by": str(user_id),
        "created_at": "2026-10-20T00:00:00+00:00",
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "progress": "0",
    }


def test_deserialize_keeps_created_by_as_str():
    payload = _job_payload(5)
    raw = {k: ValidationJobStore._serialize(v) for k, v in payload.items()}

    back = ValidationJobStore._deserialize_dict(raw)

    assert back["created_by"] == "5"
    assert back["created_by"] == str(5)
    # 端点里的判据（! = 即"不是我的任务"）必须为 False
    assert (back["created_by"] != str(5)) is False


def test_deserialize_decodes_created_by_bytes():
    """``decode_responses=False`` 的客户端会回 bytes，同样按字符串处理。"""
    back = ValidationJobStore._deserialize_dict({"created_by": b"9"})
    assert back["created_by"] == "9"


@pytest.mark.asyncio
async def test_redis_mode_job_stays_visible_to_its_creator(monkeypatch):
    """Redis 模式下：刚创建的任务，创建者能在详情与列表里查到。"""
    store = ValidationJobStore()
    fake = _FakeRedis()

    async def _get_redis():
        return fake

    monkeypatch.setattr(store, "_get_redis", _get_redis)

    payload = _job_payload(7)
    await store.create(payload["id"], payload)

    detail = await store.get(payload["id"])
    assert detail is not None
    # 详情端点 / 结果端点共用的判据
    assert (detail.get("created_by") != str(7)) is False

    listed = await store.list_jobs()
    mine = [job for job in listed if job.get("created_by") == str(7)]
    assert [job["id"] for job in mine] == [payload["id"]]
    # 反向对照：别的用户看这条任务仍然是"不存在"（越权防护未被削弱）
    assert (detail.get("created_by") != str(8)) is True
