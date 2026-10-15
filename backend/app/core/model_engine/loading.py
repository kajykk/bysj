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
from app.core.degradation import record_silent_degradation
from app.core.model_registry import MODEL_PATHS, is_model_enabled, resolve_model_path

logger = logging.getLogger(__name__)


CHUNK_SIZE = 64 * 1024

_KNOWN_MODEL_HASHES: dict[str, str] = {}

# SEC-AUDIT-06: 生产环境强制 reject (模型文件完整性不可妥协: 哈希不匹配即拒绝加载),
# 开发/测试环境保留 warn 便于模型迭代 (本地 re-train 未更新侧车时仍可运行)
#
# AUDIT-2026-10-01：staging 归入 strict。
# 理由：staging 通常是生产的镜像环境，若这里放行哈希不匹配，
# 「生产会拒绝」这个保证在预发布阶段就得不到验证 —— 要等真的上生产才第一次发现侧车陈旧。
_HASH_MISMATCH_ENVS_STRICT: frozenset[str] = frozenset({"production", "staging"})
_HASH_MISMATCH_POLICY: str = (
    "reject" if settings.app_env.lower() in _HASH_MISMATCH_ENVS_STRICT else "warn"
)


def _get_expected_hash(model_id: str, file_path: Path) -> str | None:
    """获取模型预期哈希: 优先注册表 _KNOWN_MODEL_HASHES, 其次读取同目录 .sha256 侧车文件.

    SEC-AUDIT-06: 侧车文件是真实的完整性锚点 (由训练/打包脚本经
    app.utils.checksum.write_sha256_sidecar 生成, 兼容 sha256sum 格式
    "<hash>  <filename>"). 即使注册表为空, 侧车存在时仍执行强校验.

    AUDIT-2026-10-08 (P0-6): 侧车**存在但内容不可解析**此前与「侧车不存在」
    一起返回 None, 两种完全不同的状况被压成同一个结果:
    - 不存在 → 可能从未生成, 属配置遗漏
    - 存在但解析失败 → 锚点已损坏, 属完整性事故
    现返回 tuple, 让调用方能区分并对后者显式告警。
    """
    if model_id in _KNOWN_MODEL_HASHES:
        return _KNOWN_MODEL_HASHES[model_id], "registry"
    sidecar = file_path.with_suffix(file_path.suffix + ".sha256")
    if sidecar.exists():
        try:
            first_line = sidecar.read_text(encoding="utf-8").strip().splitlines()[0]
            value = first_line.split()[0]
        except (OSError, UnicodeDecodeError, IndexError) as exc:
            logger.warning("无法解析侧车校验文件 %s: %s", sidecar, exc)
            return None, f"unreadable_sidecar:{sidecar.name}"
        # AUDIT-2026-10-08: 侧车内容必须是 64 位十六进制。轻量校验在此做,
        # 避免拿 "abc" 这种垃圾值去和真实哈希比对 —— 那样只会恒 mismatch,
        # 把配置错误伪装成「文件被篡改」的告警, 误导排查方向。
        if len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value):
            logger.error("侧车 %s 内容不是合法 sha256（长度=%d），视为无锚点", sidecar, len(value))
            return None, f"malformed_sidecar:{sidecar.name}"
        return value.lower(), "sidecar"
    return None, "absent"


def _verify_file_hash(model_id: str, file_path: Path, computed_hash: str) -> None:
    """比对模型文件哈希。锚点缺失时按 `_HASH_MISSATCH_POLICY` 决定告警或拒绝。

    AUDIT-2026-10-08 (P0-6): 原实现在锚点缺失时只 `logger.info` 后 return ——
    意味着**生产环境模型完整性完全没有被校验**，且发生在每次模型加载，
    日志里混在 info 级别里不会有人看见。这与本项目 P0-3/P0-5 修的是同一类
    病：防线看起来存在，实际不生效。

    实测底数（本机全量扫描 27 个注册模型）：真实存在的模型工件**全部**有侧车
    锚点（唯一例外 `mmpsy_lite_calibrator_meta` 是 .json 元数据，既不经
    `_verify_file_hash` 加载也无安全含义）。因此把无锚点从「静默 info」
    升级为「生产环境 ERROR + 指标」**不会打破现有部署**，却能在侧车被
    人工删除 / 重建模型后忘更新时立刻暴露。

    处置分级（保持 fail-safe 但不制造现网事故）：
    - 锚点存在且不匹配 → 原逻辑：strict 环境 raise，非 strict 记 CRITICAL
    - 锚点缺失/损坏 → ERROR 记录 + `_incr_model_fallback` 打点；
      若配置了 `_REQUIRE_INTEGRITY_ANCHOR` 则同样 raise（供后续收紧）
    """
    expected, source = _get_expected_hash(model_id, file_path)

    if expected is None:
        message = (
            f"Model {model_id} 无完整性锚点（来源={source}，computed={computed_hash}）。"
            f"请在模型文件旁生成侧车：sha256sum {file_path.name} > "
            f"{file_path.name}.sha256"
        )
        # 无论环境一律 ERROR：这不是「开发期正常现象」——锚点缺失意味着
        # 「文件是否被替换」这个问题在本进程里无法回答, 静默 info 会让它
        # 永远不被发现。strict 环境进一步直接拒绝加载。
        logger.error(message)
        _incr_model_fallback(model_id, f"integrity_anchor_missing:{source}")
        if _HASH_MISMATCH_POLICY == "reject":
            raise ValueError(
                f"Model {model_id} 缺少完整性锚点（{source}），当前环境要求强校验，拒绝加载。"
                f"生成方法：sha256sum {file_path.name} > {file_path.name}.sha256"
            )
        return

    if computed_hash != expected:
        msg = (
            f"Model {model_id} hash mismatch! "
            f"expected={expected} computed={computed_hash} (来源={source}). "
            f"File may have been tampered with."
        )
        if _HASH_MISMATCH_POLICY == "reject":
            raise ValueError(msg)
        logger.critical(msg)
    else:
        logger.info("Model %s hash verified: %s (来源=%s)", model_id, computed_hash, source)


def _compute_file_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def audit_model_integrity_anchors() -> dict[str, Any]:
    """启动时审计所有**实际存在**的模型工件是否具备完整性锚点。

    AUDIT-2026-10-08 (P0-6): 补上「启动时审计缺失侧车」这一环。

    为什么需要它：`_verify_file_hash` 只在**模型被加载时**才触发，而模型是懒加载
    的 —— 进程可以正常启动、健康检查全绿、直到某次请求命中那个缺侧车的模型
    才出事。启动审计把「防线是空的」这件事提前到部署时刻暴露。

    只审计「文件确实存在且将被加载」的模型：注册表里有条目但文件不存在是
    正常状态（可选模型未部署），报成缺失锚点会产生大量噪音，掩盖真问题。

    Returns:
        含 ``ok`` / ``missing_anchors`` / ``checked`` / ``skipped`` 的审计摘要，
        供启动自检与测试断言使用。不抛异常 —— 审计不该阻断启动。
    """
    missing: list[dict[str, str]] = []
    checked = 0
    skipped = 0

    # 必须复用 LoadingMixin._abs_path 本身（而非另写一份路径解析）——
    # 候选路径优先级（settings.model_dir 优先、backend_root 次之、CWD 垫底）
    # 决定实际加载哪个文件。审计若用不同解析逻辑, 就会出现
    # 「审计说锚点 OK、实际加载的却是另一个文件」这种最坏情况。
    # 用 __new__ 绕过 __init__：审计不应触发模型预加载与缓存初始化。
    probe = LoadingMixin.__new__(LoadingMixin)

    for model_id in sorted(MODEL_PATHS):
        try:
            if not is_model_enabled(model_id):
                skipped += 1
                continue
            file_path = probe._abs_path(resolve_model_path(model_id))
        except Exception as exc:  # noqa: PERF203 — 逐项隔离，单个失败不中断审计
            logger.warning("完整性审计: 模型 %s 路径解析失败 %s", model_id, exc)
            # P2-35 第七批：该模型随后被 skipped，不仅不进 missing 清单，调用方
            # （preload）还丢弃了整个 summary 返回值——它就这样静默逃过完整性审计
            #（锚点是否存在从此无人再问），必须计数。
            record_silent_degradation("core.model_engine.loading.audit_path_resolve_failed")
            skipped += 1
            continue

        if not file_path or not file_path.exists():
            skipped += 1
            continue

        # 只有走反序列化/推理的工件才需要锚点。纯 .json 元数据不经
        # _verify_file_hash 加载，纳入统计只会制造噪音。
        if file_path.suffix not in (".pkl", ".keras", ".h5", ".joblib", ".pt", ".pth"):
            skipped += 1
            continue

        checked += 1
        expected, source = _get_expected_hash(model_id, file_path)
        if expected is None:
            missing.append({"model_id": model_id, "path": str(file_path), "reason": source})

    summary: dict[str, Any] = {
        "ok": not missing,
        "checked": checked,
        "skipped": skipped,
        "missing_anchors": missing,
    }

    if missing:
        logger.error(
            "模型完整性审计失败：%d/%d 个已部署模型缺少哈希锚点，无法校验是否被篡改：%s",
            len(missing),
            checked,
            ", ".join(f"{m['model_id']}({m['reason']})" for m in missing),
        )
        for m in missing:
            _incr_model_fallback(m["model_id"], f"integrity_anchor_missing:{m['reason']}")
    else:
        logger.info("模型完整性审计通过：%d 个已部署模型均具备哈希锚点（%d 个跳过）", checked, skipped)

    return summary


def _incr_model_fallback(model: str, reason: str) -> None:
    """P0 (2026-09-24): 记录一次模型降级事件。

    降级此前只写日志，Grafana 无法感知"模型其实没在工作"。此处统一递增
    `model_fallback_total{model,reason}`，失败本身不影响调用方流程。
    """
    try:
        from app.core.metrics import model_fallback_total

        model_fallback_total.inc(model=model, reason=reason)
    except Exception:
        # AUDIT-2026-10-05: 级别从 debug 提到 warning。理由同上——
        # 指标递增失败时 Grafana 的降级率曲线会**变平**(运维看到"降级率 0%"),
        # 若日志同时静默则"模型正在静默降级"与"指标链路已断"两种情况都不可见。
        # 降级路径本身已在调用方打 error 日志, 此处 warning 补齐指标侧盲区。
        logger.warning(
            "model_fallback_total inc failed (model=%s reason=%s)",
            model,
            reason,
            exc_info=True,
        )


class LoadingMixin:
    """模型加载与 LRU 缓存方法集合.

    这些方法通过 Mixin 装配到 ModelEngine, 依赖 ModelEngine.__init__ 提供的
    models LRU 字典 / 缓存锁 / 加载统计等实例属性.
    """

    def preload(self) -> None:
        # AUDIT-2026-10-08 (P0-6)：预热前先做一次完整性锚点审计。
        # preload 已存在于启动路径, 因此这里是最自然的接入点——模型加载是懒的,
        # 若等到某个请求命中缺锚点的模型才发现问题, 那时健康检查早已全绿。
        audit_model_integrity_anchors()

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
                # P2-35 第二批：权重缺失走 fallback = 静默降级（预热时无任何外部信号）
                record_silent_degradation("core.model_engine.loading.preload.missing_file")
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
                # P2-35 第二批：同上（未知异常同样落到 fallback）
                record_silent_degradation("core.model_engine.loading.preload.failed")

    def _abs_path(self, rel_path: str) -> Path:
        raw = Path(rel_path)
        if raw.is_absolute():
            return raw

        # P0 修复 (2026-09-24): 候选路径优先级重排 —— 显式配置与后端内置
        # 目录优先，CWD 相对路径垫底。
        # 背景：仓库根存在陈旧的训练期影子 models/（如 models/text 下的旧版
        # 双语模型），从仓库根启动时 raw（CWD 相对）会先命中影子文件，
        # 导致生产模型被静默替换为不可反序列化的旧产物。
        #
        # P0 修复补全 (2026-10-09): 上面这条修复**没有真正生效**。默认
        # settings.model_dir == "models" 是相对路径，于是
        # `Path("models").parent` == `Path(".")`，导致候选 1 的
        # `model_dir.parent / raw` 退化为 CWD 相对路径、并被排在最前面 ——
        # 与注释声明的「CWD 垫底」恰好相反。实测（两种 CWD 对照）：
        #   CWD=仓库根   models/keras/*_best.keras -> 命中仓库根影子（2026-02，未入库）
        #   CWD=backend  同三个路径                -> MISSING（回退启发式）
        # 即同一份代码、同一份 registry，fusion 是否用 TF 权重取决于启动目录。
        # 另外 models/physiological/* 只在仓库根存在，漂移面比 keras 更大。
        # 部署侧权威源是 backend/models/（backend/Dockerfile:197
        # `COPY models/ /app/models/`，compose 挂 ./backend/models 且
        # MODEL_DIR=/app/models 为绝对路径），故相对路径一律以 backend_root 为锚。
        backend_root = Path(__file__).resolve().parents[3]

        model_dir = Path(settings.model_dir)
        if not model_dir.is_absolute():
            model_dir = backend_root / model_dir

        candidate_paths: list[Path] = []
        if raw.parts and raw.parts[0] == "models":
            candidate_paths.append(model_dir.parent / raw)
        else:
            candidate_paths.append(model_dir / raw)

        candidate_paths.append(backend_root / raw)
        if raw.parts and raw.parts[0] != "models":
            candidate_paths.append(backend_root / "models" / raw)

        for p in candidate_paths:
            if p.exists():
                return p

        # 不再保留 "CWD 相对" 兜底（原实现在末尾追加 raw）。
        # 理由：它是训练期影子目录（仓库根 models/）唯一的加载入口；保留它，
        # 同一份 registry 在 CWD=仓库根 与 CWD=backend 下会解析到不同年代、
        # 且未纳入版本控制的权重（实测见上）。心理健康场景下，用不可复现的
        # 陈旧权重参与风险判定，比"明确缺失→回退启发式"更危险。
        # 部署侧 MODEL_DIR 为绝对路径且 backend/models 是唯一权威源，此改动
        # 不影响生产解析结果（/app/models 命中路径不变）。
        logger.warning(
            "Model %s not found under model_dir=%s nor backend_root=%s; "
            "falling back to heuristic/statistical path. "
            "(CWD-relative resolution is intentionally disabled to avoid "
            "silently loading untracked training leftovers.)",
            rel_path,
            model_dir,
            backend_root,
        )
        return candidate_paths[0]

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
                try:
                    # P0 修复 (2026-09-24): score_adapter.pkl 系训练脚本上下文
                    # （__main__.ScoreAdapter）直接 pickle，unpickle 时需先在
                    # __main__ 注册同名类别名，否则 AttributeError。
                    import sys as _sys

                    from app.core.score_adapter import ScoreAdapter as _ScoreAdapterForPickle

                    _main = _sys.modules.get("__main__")
                    if _main is not None and not hasattr(_main, "ScoreAdapter"):
                        _main.ScoreAdapter = _ScoreAdapterForPickle  # type: ignore[attr-defined]
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
                except Exception as pkl_exc:
                    # pkl 反序列化失败时不直接放弃，继续走 config.json 动态构建
                    logger.warning(
                        "v1.24 adapter pkl load failed, falling back to config.json: %s",
                        pkl_exc,
                    )
                    # P2-35 第二批：pkl→config.json 回退 = 静默降级（行为等价但来源不同）
                    record_silent_degradation("core.model_engine.loading.adapter.pkl_fallback")

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
            _incr_model_fallback("v1.24_adapter", "load_failed")
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
            # P0-S1 修复：使用 safe_joblib_load 替代直接 joblib.load
            # AUDIT-2026-10-01 (P0-2)：safe_joblib_load 现在还带**反序列化类白名单**
            #   （只放行 numpy/sklearn/joblib/... 等预期模块），把"pickle 任意代码执行"
            #   降级为"加载失败"。路径/大小/哈希管的是"加载的是不是预期文件"，
            #   白名单管的才是"文件内容会不会执行任意代码"，二者不可互相替代。
            # 完整性锚点说明（AUDIT-2026-10-01 更正）：
            #   `_verify_file_hash` 才是**真实锚点校验**——它内部经 `_get_expected_hash`
            #   取注册表或 `.sha256` 侧车的哈希再比对，生产环境 mismatch 即 raise。
            #   下面传给 safe_joblib_load 的 `expected_hash` 与 `precomputed_hash`
            #   取自同一文件的同一次计算结果（expected == precomputed），
            #   因此那一层比对恒真、**不构成额外保护**；保留它只是为了满足
            #   `require_hash=True` 的语义（否则会要求每个工件都有侧车）。
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
                    # 注意：此处的 expected_hash 与 precomputed_hash 同源（都来自上面的
                    # file_hash），因此这一层比对恒真、不是完整性保护——真正的锚点比对在
                    # `_verify_file_hash`。保留原样以维持 require_hash 语义，不做行为变更。
                    expected_hash=file_hash,
                    # H-04 修复：传入预计算的哈希，避免 safe_joblib_load 内部重复计算
                    precomputed_hash=file_hash,
                )
            except Exception as exc:
                _incr_model_fallback(model_id, "load_failed")
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
                    # P2-35 第七批：到这里本函数直接 return None，调用方按“没有这个
                    # 模型”走 fallback。Keras 二次加载也失败 = 该分数通道彻底缺席，
                    # 却和“从未配置”无法区分，必须计数。
                    record_silent_degradation("core.model_engine.loading.keras_compat_load_failed")
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
                    # P-HANG 修复：优先本地缓存 (local_files_only)，命中则零网络开销；
                    # 无缓存时再回退 Hub 下载。慢网络下 Hub 重试曾导致测试无超时 hung 住
                    #（见 pytest.ini timeout 熔断），此顺序保证有缓存的机器永不触网。
                    try:
                        tokenizer = AutoTokenizer.from_pretrained(
                            bert_name, revision=settings.model_bert_revision, local_files_only=True
                        )  # nosec B615
                        bert_model = AutoModel.from_pretrained(
                            bert_name, revision=settings.model_bert_revision, local_files_only=True
                        )  # nosec B615
                    except OSError:
                        logger.info("BERT %s 无本地缓存，回退 Hub 下载", bert_name)
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
                                # OPT-P3-001：原 except 分支重复执行与 try 内相同的赋值
                                # （首次失败后条件不变、结果必然相同），属无效重试，已移除
                                logger.debug(
                                    "model_engine: SimpleImputer _fill_dtype patch failed",
                                    exc_info=True,
                                )
