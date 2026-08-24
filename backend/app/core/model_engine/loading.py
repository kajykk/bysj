"""模型加载与缓存层 (LD 层).

本模块从 `app.core.model_engine` 拆分而来 (model_engine 包结构化拆分),
承担 ModelEngine 的模型加载 / LRU 缓存 / adapter 加载 / 文件哈希校验职责:

- 模型文件 SHA256 校验 (`_compute_file_sha256` / `_verify_file_hash`)
- LRU 模型缓存 (`_cache_get` / `_cache_put`, 防 OOM)
- 同步/异步模型加载 (`_load_model` / `_load_model_async`)
- v1.24 score adapter 加载 (`_load_adapter` / `_load_adapter_async`)
- sklearn SimpleImputer 新旧版本兼容补丁 (`_patch_simple_imputer`)

通过 Mixin 多继承模式装配到 ModelEngine:

    class ModelEngine(LoadingMixin, ...):
        ...

依赖关系 (装配后由 ModelEngine 主体提供):
- `self.models` / `self._cache_lock` / `self._cache_maxsize` → ModelEngine.__init__
- `self._cache_evictions` / `self.model_load_stats`          → ModelEngine.__init__
- `self._adapter_cached`                                     → ModelEngine.__init__

向后兼容: 仅需 `from app.core.model_engine import ModelEngine` 即可继续使用,
本模块对调用方完全透明.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

# P1-E 修复：使用 TYPE_CHECKING 避免运行时导入，同时提供精确类型提示
if TYPE_CHECKING:
    from sklearn.pipeline import Pipeline

from app.core.config import BACKEND_DIR, settings
from app.core.model_registry import MODEL_PATHS, is_model_enabled, resolve_model_path

logger = logging.getLogger(__name__)


CHUNK_SIZE = 64 * 1024

_KNOWN_MODEL_HASHES: dict[str, str] = {}

# SEC-AUDIT-06: 生产环境强制 reject (模型文件完整性不可妥协: 哈希不匹配即拒绝加载),
# 开发/测试环境保留 warn 便于模型迭代 (本地 re-train 未更新侧车时仍可运行)
_HASH_MISMATCH_POLICY: str = "reject" if settings.app_env == "production" else "warn"


def _get_expected_hash(model_id: str, file_path: Path) -> str | None:
    """获取模型预期哈希: 优先注册表 _KNOWN_MODEL_HASHES, 其次读取同目录 .sha256 侧车文件.

    SEC-AUDIT-06: 侧车文件是真实的完整性锚点 (由训练/打包脚本经
    app.utils.checksum.write_sha256_sidecar 生成, 兼容 sha256sum 格式
    "<hash>  <filename>"). 即使注册表为空, 侧车存在时仍执行强校验.
    """
    if model_id in _KNOWN_MODEL_HASHES:
        return _KNOWN_MODEL_HASHES[model_id]
    sidecar = file_path.with_suffix(file_path.suffix + ".sha256")
    if sidecar.exists():
        try:
            first_line = sidecar.read_text(encoding="utf-8").strip().splitlines()[0]
            return first_line.split()[0]
        except (OSError, UnicodeDecodeError, IndexError) as exc:
            logger.warning("无法解析侧车校验文件 %s: %s", sidecar, exc)
    return None


def _verify_file_hash(model_id: str, file_path: Path, computed_hash: str) -> None:
    expected = _get_expected_hash(model_id, file_path)
    if expected is None:
        logger.info(
            "Model %s: no known hash on record (computed=%s). "
            "Add .sha256 sidecar next to the model file "
            "(sha256sum %s > %s) for strict verification.",
            model_id,
            computed_hash,
            file_path.name,
            f"{file_path.name}.sha256",
        )
        return
    if computed_hash != expected:
        msg = (
            f"Model {model_id} hash mismatch! "
            f"expected={expected} computed={computed_hash}. "
            f"File may have been tampered with."
        )
        if _HASH_MISMATCH_POLICY == "reject":
            raise ValueError(msg)
        logger.critical(msg)
    else:
        logger.info("Model %s hash verified: %s", model_id, computed_hash)


def _compute_file_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


class LoadingMixin:
    """模型加载与 LRU 缓存方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 ModelEngine.__init__ 提供的
    models LRU 字典 / 缓存锁 / 加载统计等实例属性.
    """

    def preload(self) -> None:
        for model_id in self.PRELOAD_IDS:
            try:
                self._load_model(model_id)
                logger.info("Preloaded model %s", model_id)
            except FileNotFoundError as exc:
                logger.warning(
                    "Model file not found for %s (recoverable, will fall back): %s",
                    model_id,
                    exc,
                )
            except ImportError as exc:
                logger.warning(
                    "Optional dependency missing for %s (recoverable): %s",
                    model_id,
                    exc,
                )
            except PermissionError as exc:
                logger.critical(
                    "Permission denied loading %s (NON-RECOVERABLE): %s. " "Check file permissions and process user.",
                    model_id,
                    exc,
                )
            except OSError as exc:
                logger.critical(
                    "Disk/system error loading %s (NON-RECOVERABLE): %s. " "Check disk space and hardware status.",
                    model_id,
                    exc,
                )
            except Exception as exc:
                logger.warning("Failed to preload model %s (recoverable): %s", model_id, exc)

    def _abs_path(self, rel_path: str) -> Path:
        raw = Path(rel_path)
        if raw.is_absolute():
            return raw

        candidate_paths: list[Path] = []
        candidate_paths.append(raw)

        model_dir = Path(settings.model_dir)
        if raw.parts and raw.parts[0] == "models":
            candidate_paths.append(model_dir.parent / raw)
        else:
            candidate_paths.append(model_dir / raw)

        backend_root = Path(__file__).resolve().parents[3]
        candidate_paths.append(backend_root / raw)
        if raw.parts and raw.parts[0] == "models":
            candidate_paths.append(backend_root / raw)
        else:
            candidate_paths.append(backend_root / "models" / raw)

        for p in candidate_paths:
            if p.exists():
                return p

        return candidate_paths[1]

    def _load_adapter(self) -> Any:
        try:
            adapter_dir = Path(__file__).resolve().parents[3] / "models" / "v1.24_adapter"
            adapter_pkl = adapter_dir / "score_adapter.pkl"
            adapter_config = adapter_dir / "score_adapter_config.json"

            # S-02 (V4 ML 优化): 优先加载 .pkl，回退到 config.json 动态构建
            # 这样即使 .pkl 文件缺失，adapter 仍能从 config.json 工作
            if adapter_pkl.exists():
                # ML-005 修复：使用安全加载器（路径校验 + 大小校验 + 审计日志）
                from app.core.safe_pickle import safe_joblib_load

                models_root = Path(__file__).resolve().parents[3] / "models"
                adapter = safe_joblib_load(
                    adapter_pkl,
                    trusted_root=models_root,
                    model_id="v1.24_adapter",
                )
                logger.info(
                    "v1.24 adapter loaded from pkl (version=%s)",
                    getattr(adapter, "version", "unknown"),
                )
                return adapter

            if adapter_config.exists():
                # S-02: 从 config.json 动态构建 ScoreAdapter
                import json

                from app.core.score_adapter import ScoreAdapter as _ScoreAdapter

                with open(adapter_config, "r", encoding="utf-8") as f:
                    config = json.load(f)
                adapter = _ScoreAdapter(config)
                logger.info(
                    "v1.24 adapter loaded from config.json (version=%s)",
                    getattr(adapter, "version", "unknown"),
                )
                return adapter

            logger.debug(
                "v1.24 adapter not found (neither pkl nor config.json at %s)",
                adapter_dir,
            )
            return None
        except Exception as exc:
            logger.warning("Failed to load v1.24 adapter: %s", exc)
            return None

    # ── RES-P0-001 修复: LRU 缓存操作方法 ──
    # _load_model 通过 asyncio.to_thread 在线程池中执行, 多个 predict 并发时
    # 可能同时访问 self.models, 因此所有缓存操作需在 _cache_lock 内完成.

    def _cache_get(self, model_id: str) -> Any:
        """LRU 缓存读取: 命中时移到末尾 (MRU), 未命中返回 None."""
        with self._cache_lock:
            if model_id not in self.models:
                return None
            self.models.move_to_end(model_id)
            return self.models[model_id]

    def _cache_put(self, model_id: str, model: Any) -> None:
        """LRU 缓存写入: 存入并移到末尾 (MRU), 超过 maxsize 时弹出最旧 (LRU).

        maxsize=0 时禁用 LRU (仅用于测试), 无限缓存保持向后兼容.
        """
        if model is None:
            return
        with self._cache_lock:
            self.models[model_id] = model
            self.models.move_to_end(model_id)
            # maxsize=0 禁用淘汰 (测试用)
            if self._cache_maxsize > 0:
                while len(self.models) > self._cache_maxsize:
                    evicted_id, _ = self.models.popitem(last=False)
                    self._cache_evictions += 1
                    logger.info(
                        "LRU cache evicted model %s (size=%d, maxsize=%d, evictions=%d)",
                        evicted_id,
                        len(self.models),
                        self._cache_maxsize,
                        self._cache_evictions,
                    )

    def _load_model(self, model_id: str) -> Any:
        # RES-P0-001: 使用 LRU 缓存读取
        cached = self._cache_get(model_id)
        if cached is not None:
            stats = self.model_load_stats[model_id]
            stats["cache_hits"] = int(stats["cache_hits"]) + 1
            return cached

        if model_id not in MODEL_PATHS:
            raise FileNotFoundError(f"Unknown model_id: {model_id}")
        if not is_model_enabled(model_id):
            raise FileNotFoundError(f"Model disabled: {model_id}")

        model_path = self._abs_path(resolve_model_path(model_id))
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        started = perf_counter()
        if model_path.suffix == ".pkl":
            # P0-S1 修复：使用 safe_joblib_load 替代直接 joblib.load，启用路径白名单防止路径遍历
            # safe_joblib_load 内部完成：路径校验、大小校验、哈希计算、joblib.load
            # 此处保留 _verify_file_hash 用于与模型注册表的预期哈希比对（额外完整性层）
            try:
                file_hash = _compute_file_sha256(model_path)
                _verify_file_hash(model_id, model_path, file_hash)
                logger.info("Loading model %s (hash=%s)", model_id, file_hash)
                from app.core.safe_pickle import safe_joblib_load

                # 模型文件可能位于项目根 models/ 或 backend/models/ 两个位置。
                # _abs_path 会返回第一个存在的候选路径，因此 trusted_root 需要动态确定
                # 以匹配实际文件所在目录，否则路径白名单校验会误拒合法文件。
                resolved = model_path.resolve()
                config_root = Path(settings.model_dir).resolve()
                if not resolved.is_relative_to(config_root):
                    # 文件不在配置的 model_dir 下，回退到 BACKEND_DIR/models
                    trusted_root = BACKEND_DIR / "models"
                else:
                    trusted_root = config_root
                model = safe_joblib_load(
                    model_path,
                    trusted_root=trusted_root,
                    model_id=model_id,
                    expected_hash=file_hash,
                    # H-04 修复：传入预计算的哈希，避免 safe_joblib_load 内部重复计算
                    precomputed_hash=file_hash,
                )
            except Exception as exc:
                raise ValueError(f"Failed to load model {model_id}: corrupted or invalid file") from exc
        elif model_path.suffix == ".keras":
            import tensorflow as tf

            try:
                file_hash = _compute_file_sha256(model_path)
                _verify_file_hash(model_id, model_path, file_hash)
                logger.info("Loading Keras model %s (hash=%s)", model_id, file_hash)
                model = tf.keras.models.load_model(model_path)
            except (TypeError, ValueError) as exc:
                message = str(exc)
                if "quantization_config" not in message and "Could not locate class" not in message:
                    raise
                # C-Core-2 修复：改用 custom_objects 传递兼容 Dense 子类，
                # 避免修改全局 Dense.from_config（原实现即使加 _keras_load_lock 仍有并发风险：
                # 若 load_model 内部触发其他线程的模型加载，会用到被修改的 from_config）。
                from keras.src.layers.core.dense import Dense

                class _CompatDense(Dense):
                    @classmethod
                    def from_config(cls, config):
                        config = dict(config)
                        config.pop("quantization_config", None)
                        return super().from_config(config)

                logger.warning(
                    "Loading Keras model %s with compat Dense (quantization_config)",
                    model_id,
                )
                try:
                    model = tf.keras.models.load_model(model_path, custom_objects={"Dense": _CompatDense})
                except Exception as e:
                    logger.warning("Keras model load failed: %s", e)
                    return None
        elif model_path.is_dir():
            # 阶段三: 支持 M2 BERT feature extraction + LogReg 部署模式
            config_file = model_path / "config.json"
            if config_file.exists():
                import json as _json

                with open(config_file, "r", encoding="utf-8") as f:
                    bundle_config = _json.load(f)
                if bundle_config.get("model_type") == "bert_feature_extraction":
                    # M2 部署模式: 冻结 BERT + LogReg 分类头
                    # SEC-AUDIT-06: 使用 safe_joblib_load 替代裸 pickle.load
                    # (路径白名单 + 大小上限 + SHA256 哈希校验, 防 pickle RCE)
                    from transformers import AutoModel, AutoTokenizer

                    from app.core.safe_pickle import safe_joblib_load

                    bert_name = bundle_config["bert_model_name"]
                    logger.info("Loading BERT (feature extraction) %s", bert_name)
                    # ISS-13 (B615): 显式固定 Hub 下载 revision, 避免供应链漂移
                    tokenizer = AutoTokenizer.from_pretrained(bert_name, revision=settings.model_bert_revision)  # nosec B615
                    bert_model = AutoModel.from_pretrained(bert_name, revision=settings.model_bert_revision)  # nosec B615
                    bert_model.eval()
                    classifier_path = model_path / "classifier.pkl"
                    scaler_path = model_path / "scaler.pkl"
                    classifier_hash = _compute_file_sha256(classifier_path)
                    scaler_hash = _compute_file_sha256(scaler_path)
                    _verify_file_hash(f"{model_id}:classifier", classifier_path, classifier_hash)
                    _verify_file_hash(f"{model_id}:scaler", scaler_path, scaler_hash)
                    classifier = safe_joblib_load(
                        classifier_path,
                        trusted_root=model_path,
                        model_id=f"{model_id}:classifier",
                        expected_hash=classifier_hash,
                        precomputed_hash=classifier_hash,
                    )
                    scaler = safe_joblib_load(
                        scaler_path,
                        trusted_root=model_path,
                        model_id=f"{model_id}:scaler",
                        expected_hash=scaler_hash,
                        precomputed_hash=scaler_hash,
                    )
                    model = {
                        "tokenizer": tokenizer,
                        "bert_model": bert_model,
                        "classifier": classifier,
                        "scaler": scaler,
                        "threshold": bundle_config["threshold"],
                        "max_seq_len": bundle_config.get("max_seq_len", 256),
                        "mode": "feature_extraction",
                    }
                else:
                    from transformers import AutoModelForSequenceClassification, AutoTokenizer

                    tokenizer = AutoTokenizer.from_pretrained(model_path)  # nosec B615
                    bert_model = AutoModelForSequenceClassification.from_pretrained(model_path)  # nosec B615
                    model = {"tokenizer": tokenizer, "model": bert_model}
            else:
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                tokenizer = AutoTokenizer.from_pretrained(model_path)  # nosec B615  (本地目录, 非 Hub 下载)
                bert_model = AutoModelForSequenceClassification.from_pretrained(model_path)  # nosec B615
                model = {"tokenizer": tokenizer, "model": bert_model}
        else:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(model_path)  # nosec B615  (本地路径加载)
            bert_model = AutoModelForSequenceClassification.from_pretrained(model_path)  # nosec B615
            model = {"tokenizer": tokenizer, "model": bert_model}

        elapsed_ms = (perf_counter() - started) * 1000.0
        stats = self.model_load_stats[model_id]
        stats["loads"] = int(stats["loads"]) + 1
        stats["last_load_ms"] = elapsed_ms
        if not stats["first_load_ms"]:
            stats["first_load_ms"] = elapsed_ms
        # RES-P0-001: 使用 LRU 缓存写入 (超限自动淘汰最旧模型)
        self._cache_put(model_id, model)
        logger.info("Loaded model %s in %.2f ms", model_id, elapsed_ms)
        return model

    async def _load_model_async(self, model_id: str) -> Any:
        """P1-1: 异步加载模型, 缓存命中时直接返回, 缓存未命中时在线程池加载.

        避免首次加载 (如 BERT/Keras 模型) 阻塞事件循环.
        缓存命中 (常见场景) 无线程调度开销.
        """
        # RES-P0-001: 使用 LRU 缓存读取 (命中时移到 MRU)
        cached = self._cache_get(model_id)
        if cached is not None:
            stats = self.model_load_stats[model_id]
            stats["cache_hits"] = int(stats["cache_hits"]) + 1
            return cached
        return await asyncio.to_thread(self._load_model, model_id)

    async def _load_adapter_async(self) -> Any:
        """P1-1: 异步加载 v1.24 adapter, 带缓存避免重复 I/O."""
        if self._adapter_cached is not None:
            return self._adapter_cached
        self._adapter_cached = await asyncio.to_thread(self._load_adapter)
        return self._adapter_cached

    @staticmethod
    def _patch_simple_imputer(model: Pipeline) -> None:
        """修复旧版 sklearn 训练的 SimpleImputer 在新版 sklearn (>=1.3.0) 下的兼容性。

        S-02 修复：原逻辑反了——只在 hasattr(step, "_fill_dtype") 时设为 None，
        但 sklearn 1.8.0 的 SimpleImputer.transform 仍引用 self._fill_dtype，
        旧模型 pickle 加载后该属性不存在，导致 AttributeError。
        正确做法：缺失 _fill_dtype 时从 _fit_dtype 复制（两者语义一致）。
        """
        from sklearn.impute import SimpleImputer

        if hasattr(model, "named_steps") and "preprocessor" in model.named_steps:
            preprocessor = model.named_steps["preprocessor"]
            if hasattr(preprocessor, "transformers_"):
                for _, transformer, _ in preprocessor.transformers_:
                    if transformer == "drop" or transformer == "passthrough":
                        continue
                    if hasattr(transformer, "named_steps"):
                        for step_name, step in transformer.named_steps.items():
                            if not isinstance(step, SimpleImputer):
                                continue
                            try:
                                # sklearn >= 1.3.0: 旧模型 pickle 缺失 _fill_dtype，
                                # 从 _fit_dtype 复制以恢复 transform 兼容性
                                if not hasattr(step, "_fill_dtype") and hasattr(step, "_fit_dtype"):
                                    step._fill_dtype = step._fit_dtype  # type: ignore[attr-defined]
                                    logger.debug(
                                        "SimpleImputer[%s]: patched _fill_dtype=%s (from _fit_dtype)",
                                        step_name,
                                        step._fill_dtype,
                                    )
                            except Exception:
                                # M-L 修复：记录 sklearn 兼容性补丁失败，避免静默掩盖问题
                                logger.debug(
                                    "model_engine: SimpleImputer _fill_dtype patch failed",
                                    exc_info=True,
                                )
                                if not hasattr(step, "_fill_dtype") and hasattr(step, "_fit_dtype"):
                                    step._fill_dtype = step._fit_dtype  # type: ignore[attr-defined]
