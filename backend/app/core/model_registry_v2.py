"""
Model Registry V2 - Production-grade model governance system.

Features:
- Model lifecycle management (candidate -> staging -> production -> retired)
- Fallback chain management
- Performance threshold monitoring
- Training configuration tracking
- Version control with semver

Usage:
    from app.core.model_registry_v2 import ModelRegistryV2, ModelStatus

    registry = ModelRegistryV2()
    registry.register_model(
        model_id="physiological_xgboost",
        name="Physiological XGBoost",
        version="v1.0.0",
        model_type="xgboost",
        status=ModelStatus.CANDIDATE,
        fallback_id="physiological_risk_model",
        artifact_path="models/artifacts/physiological/xgboost_model.pkl",
        metrics={"f1_score": 0.81, "precision": 0.79, "recall": 0.83},
        training_config={"random_state": 42, "n_estimators": 200},
    )
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.degradation import record_silent_degradation

logger = logging.getLogger(__name__)

# AUDIT-2026-10-08 (P2-registry-atomic)：注册表的并发与写盘原子性。
#
# 为什么是**模块级**锁而不是实例级：``get_registry()`` 返回的是全局单例，
# 它同时被三类线程访问 ——
#   1. 推理线程：``model_registry.resolve_model_path`` (L331) 每次解析模型路径
#      都会查 V2 注册表
#   2. 训练线程：``model_training.py`` 的 ``register_training_artifact``
#   3. 后台线程：``registry_auto_rollback`` / ``shadow_comparison_service``
# 实例级锁保护不了「两个线程同时首次调用 get_registry() 各建一个实例」的竞态。
#
# 为什么用 RLock 而不是 Lock：公开方法（如 ``promote_model``）内部会调
# ``get_model``，可重入避免自锁。这点很关键 —— 推理侧
# ``model_registry.py:341`` 把注册表查询包在 ``except Exception`` 里静默降级到
# 静态路径，一旦死锁不会报错，只会表现为「训练产物永远不生效」，极难排查。
_REGISTRY_LOCK = threading.RLock()


def _serialized(func):
    """串行化注册表的**复合写操作**（read-modify-write）。

    只装饰写方法，不装饰 ``get_model`` 等纯读方法 —— 理由：
    - 纯读是单个 dict 操作，GIL 下本身原子，不会读到损坏结构；
    - ``get_model`` 位于推理热路径（``model_registry.resolve_model_path``
      每次解析模型路径都会调用），给它加锁只会增加阻塞面，而它并不产生
      「读到写了一半」的风险 —— 真正会交错的是两个**写**操作（一个 register
      改到一半被另一个 promote 覆盖），那个已由本装饰器消除。
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _REGISTRY_LOCK:
            return func(*args, **kwargs)

    return wrapper


class ModelStatus(Enum):
    """Model lifecycle statuses."""

    CANDIDATE = "candidate"
    STAGING = "staging"
    PRODUCTION = "production"
    RETIRED = "retired"


class ModelType(Enum):
    """Supported model types."""

    XGBOOST = "xgboost"
    LIGHTGBM = "lightgbm"
    MLP = "mlp"
    CATBOOST = "catboost"
    LOGISTIC_REGRESSION = "logistic_regression"


@dataclass
class ModelRecord:
    """A single model record in the registry."""

    model_id: str
    name: str
    version: str
    model_type: ModelType
    status: ModelStatus
    fallback_id: str | None
    performance_threshold: dict[str, float]
    metrics: dict[str, float]
    artifact_path: str
    training_config: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "model_type": self.model_type.value,
            "status": self.status.value,
            "fallback_id": self.fallback_id,
            "performance_threshold": self.performance_threshold,
            "metrics": self.metrics,
            "artifact_path": self.artifact_path,
            "training_config": self.training_config,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRecord:
        return cls(
            model_id=data["model_id"],
            name=data["name"],
            version=data["version"],
            model_type=ModelType(data["model_type"]),
            status=ModelStatus(data["status"]),
            fallback_id=data.get("fallback_id"),
            performance_threshold=data.get("performance_threshold", {}),
            metrics=data.get("metrics", {}),
            artifact_path=data["artifact_path"],
            training_config=data.get("training_config", {}),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )


class ModelRegistryV2:
    """Production-grade model registry with lifecycle management."""

    def __init__(self, registry_path: str | None = None) -> None:
        self.registry: dict[str, ModelRecord] = {}
        self.registry_path = registry_path or "models/registry/model_registry_v2.json"
        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from disk."""
        path = Path(self.registry_path)
        if not path.exists():
            return
        with _REGISTRY_LOCK:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            # M-Core-14 修复：扩大异常捕获范围，避免未知异常导致启动崩溃
            except (json.JSONDecodeError, KeyError, OSError, ValueError) as exc:
                # AUDIT-2026-10-08 (P2-registry-atomic)：损坏文件必须**旁路**，
                # 不能留在原地。
                #
                # 原实现只 warning 就让 registry 保持为空，而损坏文件仍在
                # registry_path 上 —— 下一次任意写操作会用空表覆盖它，
                # 损坏内容连同里面的训练资产记录一起**永久消失**，连人工恢复
                # 的机会都没有。实测：5 条记录经一次写坏 + 一次写入后归零。
                #
                # 旁路为 .corrupt-<时间戳> 后，进程仍以空表继续（推理侧有
                # except 降级，不能让它启动失败），但原件保留可事后取回。
                logger.error(
                    "注册表文件 %s 无法解析（%s），已旁路备份并**以空表启动**；所有训练产物记录需从备份恢复后重新注册",
                    path,
                    exc,
                )
                self._quarantine_corrupt_file(path)
                # 空表启动与「全新注册表」同形：调用方看到的都是一台没有历史产物的
                # registry，训练资产的丢失不会体现在任何接口返回值上。
                record_silent_degradation("core.model_registry_v2.registry_file_unparsable")
                return

            try:
                for model_id, record_data in data.get("models", {}).items():
                    self.registry[model_id] = ModelRecord.from_dict(record_data)
            except (KeyError, ValueError, TypeError) as exc:
                # 文件本身是合法 JSON，但某条记录结构坏了。
                # 与上面同理：旁路原件，避免被下一次写入静默覆盖。
                logger.error(
                    "注册表文件 %s 中存在损坏记录（%s），已旁路备份；已加载 %d 条，其余丢弃",
                    path,
                    exc,
                    len(self.registry),
                )
                self._quarantine_corrupt_file(path)
                # 部分加载同样与正常态同形：registry 非空且能用，只是少了几条，
                # 没有任何返回值能表明「本应有更多记录」。
                record_silent_degradation("core.model_registry_v2.registry_records_dropped")
                return

            logger.info("Loaded %d models from registry", len(self.registry))

    @staticmethod
    def _quarantine_corrupt_file(path: Path) -> None:
        """把损坏的注册表文件改名旁路，保留现场供人工恢复。

        失败只记录不抛出：旁路是**尽力而为**的兜底，绝不能因为备份失败
        就让进程起不来 —— 注册表加载失败本身已有空表降级路径。
        """
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            os.replace(path, backup)
        except OSError as exc:
            logger.error("无法旁路损坏的注册表文件 %s -> %s: %s", path, backup, exc)
        else:
            logger.error("损坏文件已旁路至 %s，请人工核对后恢复", backup)

    def _save_registry(self) -> None:
        """原子写盘：先写同目录临时文件，再 ``os.replace`` 覆盖。

        AUDIT-2026-10-08 (P2-registry-atomic)：原实现 ``open(path, "w")`` 会
        **先 truncate 已有文件再写入**，中间态是「半截 JSON」。实测（用抛
        OSError 的假 ``json.dump`` 模拟磁盘满 / 进程被杀）：写一半时磁盘上
        留下 30 字节的半截内容，而 ``_load_registry`` 捕获 JSONDecodeError 后
        只 warning 并继续，registry 变空 —— **下一次任意写操作就把空表写回
        磁盘**，5 条训练资产永久丢失。模型文件还在磁盘上，但注册表里查不到，
        永远不会再被激活（``resolve_model_path`` 只认 PRODUCTION 记录）。

        原子写彻底消除了这个中间态：``os.replace`` 在同一文件系统下是原子的，
        并发读方要么看到旧文件、要么看到新文件，不存在「读到一半」的可能。

        另：序列化放在**打开文件之前**完成，让序列化异常（如不可序列化的
        metrics 值）既不留 tmp 垃圾，也不触碰已有文件。
        """
        path = Path(self.registry_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "2.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "models": {
                model_id: record.to_dict() for model_id, record in self.registry.items()
            },
        }
        try:
            payload = json.dumps(data, indent=2, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            # 序列化失败：已有磁盘文件完全不受影响，直接抛出由调用方回滚内存
            logger.error("注册表序列化失败，未触碰磁盘文件 %s: %s", path, exc)
            raise

        # tmp 必须落在**同一目录**：os.replace 跨文件系统会退化成
        # copy+unlink，那就不再原子了。
        tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                # 先落盘再替换：否则极端断电下可能 replace 了一个内容还在
                # 页缓存里的文件。
                os.fsync(f.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            # 已有文件未受影响（os.replace 尚未执行），只需清掉半成品。
            with contextlib.suppress(OSError):
                os.close(tmp_fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise

        # 注：这里**不**对父目录做 fsync。目录项未持久化时，重启后可能看到
        # 旧文件或新文件 —— 两者都是完整合法的 JSON，不会出现半截文件，
        # 对注册表这种「整体替换」的写模式是可接受的取舍；而 Windows 上
        # 打开目录 fd 本身就不被支持。

    def register_model(
        self,
        model_id: str,
        name: str,
        version: str,
        model_type: ModelType,
        status: ModelStatus = ModelStatus.CANDIDATE,
        fallback_id: str | None = None,
        performance_threshold: dict[str, float] | None = None,
        metrics: dict[str, float] | None = None,
        artifact_path: str = "",
        training_config: dict[str, Any] | None = None,
    ) -> ModelRecord:
        """Register a new model or update an existing one."""
        # AUDIT-2026-10-08 (P2-registry-atomic)：read-modify-write 全程串行。
        # 实测 8 线程 × 20 次注册只落盘 100/160 —— 并发 ``open(path, "w")``
        # 在 Windows 上直接 PermissionError（独占打开），训练产物已存盘但
        # 注册失败，模型永远不会被激活。
        return self._register_model_locked(
            model_id=model_id,
            name=name,
            version=version,
            model_type=model_type,
            status=status,
            fallback_id=fallback_id,
            performance_threshold=performance_threshold,
            metrics=metrics,
            artifact_path=artifact_path,
            training_config=training_config,
        )

    @_serialized
    def _register_model_locked(
        self,
        model_id: str,
        name: str,
        version: str,
        model_type: ModelType,
        status: ModelStatus = ModelStatus.CANDIDATE,
        fallback_id: str | None = None,
        performance_threshold: dict[str, float] | None = None,
        metrics: dict[str, float] | None = None,
        artifact_path: str = "",
        training_config: dict[str, Any] | None = None,
    ) -> ModelRecord:
        now = datetime.now(timezone.utc).isoformat()

        if model_id in self.registry:
            # Update existing model
            # M-07 修复：保存旧状态，磁盘写入失败时回滚内存状态
            record = self.registry[model_id]
            old_snapshot = {
                "name": record.name,
                "version": record.version,
                "model_type": record.model_type,
                "status": record.status,
                "fallback_id": record.fallback_id,
                "performance_threshold": record.performance_threshold,
                "metrics": record.metrics,
                "artifact_path": record.artifact_path,
                "training_config": record.training_config,
                "updated_at": record.updated_at,
            }
            record.name = name
            record.version = version
            record.model_type = model_type
            record.status = status
            record.fallback_id = fallback_id
            record.performance_threshold = performance_threshold or {}
            record.metrics = metrics or {}
            record.artifact_path = artifact_path
            record.training_config = training_config or {}
            record.updated_at = now
            try:
                self._save_registry()
            except Exception as exc:
                # 磁盘写入失败，回滚内存状态
                record.name = old_snapshot["name"]
                record.version = old_snapshot["version"]
                record.model_type = old_snapshot["model_type"]
                record.status = old_snapshot["status"]
                record.fallback_id = old_snapshot["fallback_id"]
                record.performance_threshold = old_snapshot["performance_threshold"]
                record.metrics = old_snapshot["metrics"]
                record.artifact_path = old_snapshot["artifact_path"]
                record.training_config = old_snapshot["training_config"]
                record.updated_at = old_snapshot["updated_at"]
                logger.error("Failed to persist model update %s: %s", model_id, exc)
                raise
            logger.info("Updated model %s to version %s", model_id, version)
        else:
            # Create new model record
            record = ModelRecord(
                model_id=model_id,
                name=name,
                version=version,
                model_type=model_type,
                status=status,
                fallback_id=fallback_id,
                performance_threshold=performance_threshold or {},
                metrics=metrics or {},
                artifact_path=artifact_path,
                training_config=training_config or {},
                created_at=now,
                updated_at=now,
            )
            # 先加入内存 registry，再保存到磁盘；保存失败时回滚内存状态。
            # 原实现顺序相反，导致 _save_registry 遍历 self.registry 时新记录尚未入表，
            # 写入文件的 "models" 字段为空，重启后加载不出新建模型。
            self.registry[model_id] = record
            try:
                self._save_registry()
            except Exception as exc:
                # 磁盘写入失败，回滚内存 registry
                del self.registry[model_id]
                logger.error("Failed to persist new model %s: %s", model_id, exc)
                raise
            logger.info("Registered new model %s (version %s)", model_id, version)

        return record

    def get_model(self, model_id: str) -> ModelRecord | None:
        """Get a model record by ID."""
        return self.registry.get(model_id)

    def get_models_by_status(self, status: ModelStatus) -> list[ModelRecord]:
        """Get all models with a specific status."""
        return [record for record in self.registry.values() if record.status == status]

    def get_production_models(self) -> list[ModelRecord]:
        """Get all production models."""
        return self.get_models_by_status(ModelStatus.PRODUCTION)

    def promote_model(
        self, model_id: str, new_status: ModelStatus
    ) -> ModelRecord | None:
        """Promote or demote a model to a new status."""
        # AUDIT-2026-10-08 (P2-registry-atomic)：状态流转是典型的
        # read-modify-write（读 status → 校验合法转移 → 改 → 落盘）。
        # 实测两个线程并发 CANDIDATE→STAGING：第二个读到已被改过的
        # staging，判定 "staging -> staging" 非法而返回 None —— 调用方
        # （activate_training_model）据此认为激活失败，但实际状态已生效，
        # 于是上层会重试或报警，产生幽灵失败。
        return self._promote_model_locked(model_id, new_status)

    @_serialized
    def _promote_model_locked(self, model_id: str, new_status: ModelStatus) -> ModelRecord | None:
        record = self.registry.get(model_id)
        if not record:
            logger.error("Model %s not found", model_id)
            return None

        # Validate status transitions
        valid_transitions = {
            ModelStatus.CANDIDATE: [ModelStatus.STAGING],
            ModelStatus.STAGING: [ModelStatus.PRODUCTION, ModelStatus.CANDIDATE],
            ModelStatus.PRODUCTION: [ModelStatus.RETIRED, ModelStatus.STAGING],
            ModelStatus.RETIRED: [],
        }

        if new_status not in valid_transitions.get(record.status, []):
            logger.error(
                "Invalid status transition: %s -> %s",
                record.status.value,
                new_status.value,
            )
            return None

        # M-07 修复：先保存旧状态，磁盘写入失败时回滚内存状态，保持一致性
        old_status = record.status
        old_updated_at = record.updated_at
        record.status = new_status
        record.updated_at = datetime.now(timezone.utc).isoformat()
        try:
            self._save_registry()
        except Exception as exc:
            # 磁盘写入失败，回滚内存状态
            record.status = old_status
            record.updated_at = old_updated_at
            logger.error(
                "Failed to persist model promotion %s -> %s: %s",
                model_id,
                new_status.value,
                exc,
            )
            return None

        logger.info("Model %s promoted to %s", model_id, new_status.value)
        return record

    def get_fallback_chain(self, model_id: str) -> list[str]:
        """Get the fallback chain for a model."""
        chain = []
        visited = set()
        current = model_id

        while current and current not in visited:
            visited.add(current)
            chain.append(current)
            record = self.registry.get(current)
            if not record:
                break
            current = record.fallback_id

        return chain

    def check_performance_regression(
        self, model_id: str, current_metrics: dict[str, float]
    ) -> dict[str, Any]:
        """Check if current metrics indicate performance regression."""
        record = self.registry.get(model_id)
        if not record:
            return {"error": f"Model {model_id} not found"}

        threshold = record.performance_threshold
        if not threshold:
            return {"regression_detected": False, "reason": "No threshold configured"}

        regressions = []
        for metric, threshold_value in threshold.items():
            current_value = current_metrics.get(metric)
            if current_value is None:
                continue

            # H-Core-6 修复：对所有 metric 执行回归检查（原实现仅检查 f1_score，
            # 导致 precision/recall/auc 等指标的性能回归被静默忽略）
            if current_value < threshold_value:
                regressions.append(
                    {
                        "metric": metric,
                        "current": current_value,
                        "threshold": threshold_value,
                        "drop": threshold_value - current_value,
                    }
                )

        return {
            "regression_detected": len(regressions) > 0,
            "regressions": regressions,
            "model_id": model_id,
        }

    def list_models(self) -> list[dict[str, Any]]:
        """List all models in the registry."""
        return [record.to_dict() for record in self.registry.values()]

    def validate_artifact_exists(self, model_id: str) -> bool:
        """Check if the model artifact file exists."""
        record = self.registry.get(model_id)
        if not record:
            return False

        path = Path(record.artifact_path)
        if not path.is_absolute():
            # Try relative to project root
            project_root = Path(__file__).resolve().parents[3]
            path = project_root / path

        return path.exists()


# Global registry instance
_registry_instance: ModelRegistryV2 | None = None


def get_registry() -> ModelRegistryV2:
    """Get the global registry instance."""
    # AUDIT-2026-10-08 (P2-registry-atomic)：双重检查加锁。
    # 原实现是裸的 if-None-then-create：两个线程同时首次调用会各建一个实例，
    # 各自 ``_load_registry`` 到不同的内存快照，后赋值的那个胜出 —— 前者
    # 期间完成的任何注册都会被无声丢弃（``_registry_instance`` 被整体换掉）。
    global _registry_instance
    if _registry_instance is None:
        with _REGISTRY_LOCK:
            if _registry_instance is None:
                _registry_instance = ModelRegistryV2()
    return _registry_instance


@_serialized
def register_training_artifact(
    model_id: str,
    artifact_path: str,
    *,
    version: str = "v1",
    metrics: dict[str, float] | None = None,
    training_config: dict[str, Any] | None = None,
    model_type: ModelType = ModelType.LOGISTIC_REGRESSION,
    fallback_id: str | None = None,
) -> ModelRecord:
    """注册训练产物为候选模型 (CANDIDATE).

    训练任务在产物保存成功后调用: 产物进入注册表, 便于后续激活上线.

    AUDIT-2026-10-08 (P2-registry-atomic)：整个调用串行化（见 ``_serialized``）。
    """
    return get_registry().register_model(
        model_id=model_id,
        name=model_id,
        version=version,
        model_type=model_type,
        status=ModelStatus.CANDIDATE,
        fallback_id=fallback_id,
        metrics=metrics or {},
        artifact_path=artifact_path,
        training_config=training_config or {},
    )


@_serialized
def activate_training_model(model_id: str) -> ModelRecord | None:
    """将 CANDIDATE 训练产物提升为 PRODUCTION, 使其接入推理链.

    返回提升后的记录; 找不到模型或转换不合法时返回 None.

    AUDIT-2026-10-08 (P2-registry-atomic)：CANDIDATE→STAGING→PRODUCTION 是
    **两级**提升，级与级之间若被另一个线程插入（比如并发回退），会出现
    「提升成功但返回 None」这类幽灵失败。整个调用串行化。
    """
    registry = get_registry()
    record = registry.get_model(model_id)
    if record is None:
        logger.error("activate_training_model: model %s not found", model_id)
        return None

    # CANDIDATE -> STAGING -> PRODUCTION 逐级提升, 任一级失败即中止
    for interim in (
        ModelStatus.STAGING if record.status == ModelStatus.CANDIDATE else None,
        ModelStatus.PRODUCTION,
    ):
        if interim is None:
            continue
        current = registry.get_model(model_id)
        if current is None:
            return None
        if current.status == ModelStatus.PRODUCTION:
            break
        if current.status == interim:
            continue
        promoted = registry.promote_model(model_id, interim)
        if promoted is None:
            return None
    return registry.get_model(model_id)


@_serialized
def rollback_training_model(model_id: str) -> ModelRecord | None:
    """将 PRODUCTION 训练产物降级为 CANDIDATE, 推理链回退静态模型.

    自动回退 (R2) 与人工回退共用. PRODUCTION -> STAGING -> CANDIDATE
    逐级降级; 已是 STAGING/CANDIDATE/缺失时返回 None (无需回退).

    AUDIT-2026-10-08 (P2-registry-atomic)：与 activate_training_model 同理，
    两级降级整体串行化，避免与并发激活互相插入。
    """
    registry = get_registry()
    record = registry.get_model(model_id)
    if record is None:
        logger.error("rollback_training_model: model %s not found", model_id)
        return None

    # PRODUCTION -> STAGING -> CANDIDATE 逐级降级
    for interim in (
        ModelStatus.STAGING if record.status == ModelStatus.PRODUCTION else None,
        ModelStatus.CANDIDATE,
    ):
        if interim is None:
            continue
        current = registry.get_model(model_id)
        if current is None:
            return None
        if current.status == ModelStatus.CANDIDATE:
            break
        if current.status == interim:
            continue
        demoted = registry.promote_model(model_id, interim)
        if demoted is None:
            return None
    return registry.get_model(model_id)
