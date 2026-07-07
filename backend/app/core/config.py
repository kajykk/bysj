import importlib.util
import logging
import secrets
import sys
import warnings
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# P1-E 修复：使用 logger 替代 print()，便于生产环境统一日志收集
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_URL = (
    f"sqlite+aiosqlite:///{(BACKEND_DIR / 'depression_system.db').as_posix()}"
)

# L-API-1 修复：统一发布版本号常量，version.py 和 metrics.py 均引用此常量，避免版本号散落
RELEASE_VERSION = "v1.32-observability-complete"

# Runtime dependency detection (lazy import to avoid DLL init issues on Windows)
_PYTORCH_AVAILABLE: bool | None = None
_TRANSFORMERS_AVAILABLE: bool | None = None
_SKLEARN_VERSION: str | None = None


def _check_pytorch() -> bool:
    global _PYTORCH_AVAILABLE
    if _PYTORCH_AVAILABLE is None:
        if "torch" in sys.modules:
            _PYTORCH_AVAILABLE = True
        else:
            _PYTORCH_AVAILABLE = importlib.util.find_spec("torch") is not None
    return _PYTORCH_AVAILABLE


def _check_transformers() -> bool:
    global _TRANSFORMERS_AVAILABLE
    if _TRANSFORMERS_AVAILABLE is None:
        if "transformers" in sys.modules:
            _TRANSFORMERS_AVAILABLE = True
        else:
            _TRANSFORMERS_AVAILABLE = (
                importlib.util.find_spec("transformers") is not None
            )
    return _TRANSFORMERS_AVAILABLE


def _get_sklearn_version() -> str | None:
    global _SKLEARN_VERSION
    if _SKLEARN_VERSION is None:
        # On Windows, importing sklearn may crash with exit -1073741510
        # due to DLL initialization issues. Skip the import on Windows.
        if sys.platform == "win32":
            _SKLEARN_VERSION = None
        else:
            try:
                import sklearn

                _SKLEARN_VERSION = sklearn.__version__
            except ImportError:
                _SKLEARN_VERSION = None
    return _SKLEARN_VERSION


# Backward-compatible module-level constants
# NOTE: Lazy evaluation to avoid DLL init issues on Windows (e.g. sklearn)
PYTORCH_AVAILABLE = _check_pytorch()
TRANSFORMERS_AVAILABLE = _check_transformers()

# H-Core-5 修复：SKLEARN_VERSION 已迁移为 Settings 类的 @property，
# 并通过模块级 __getattr__ 提供向后兼容的 `from app.core.config import SKLEARN_VERSION` 访问。
_INSECURE_KEYS = {
    "",
    "change-this-to-a-random-secret-key",
    "depression-warning-system-secret-key-2024",
    "CHANGE_ME_generate_with_python_secrets_token_urlsafe_32",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    app_name: str = "Depression Warning System"
    app_version: str = "3.1.0"
    app_env: str = "development"

    database_url: str = DEFAULT_SQLITE_URL
    redis_url: str = "redis://localhost:6379/0"

    # M-L 修复：数据库连接池参数可配置化，适配不同部署环境的负载需求
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # ── STAB-P0-001 修复：数据库熔断器配置 ──
    # 是否启用 DB 熔断器 (关闭后 get_db 不再拦截, 适合测试环境)
    db_circuit_breaker_enabled: bool = True
    # 连续失败次数阈值, 达到后熔断器打开 (拒绝新请求)
    db_failure_threshold: int = 5
    # 熔断器打开后恢复时间 (秒), 经过此时间后进入半开状态
    db_recovery_timeout: int = 30
    # 半开状态允许的最大测试请求数
    db_half_open_max_calls: int = 1

    # ── STAB-P0-002 修复：数据库查询语句级超时 ──
    # PostgreSQL statement_timeout (秒), 0 表示禁用. 慢查询超过此值被自动取消
    # 仅对 PostgreSQL 生效, SQLite 不支持 (忽略此项)
    db_statement_timeout: int = 10

    # ── STAB-P1-002 修复：ML 推理熔断器 + asyncio.wait_for 超时 ──
    # 是否启用 ML 熔断器 (关闭后 predict_* 不再拦截, 适合测试环境)
    ml_circuit_breaker_enabled: bool = True
    # ML 推理连续失败次数阈值, 达到后熔断器打开 (拒绝新请求)
    ml_failure_threshold: int = 5
    # ML 熔断器打开后恢复时间 (秒), 经过此时间后进入半开状态
    ml_recovery_timeout: int = 30
    # ML 半开状态允许的最大测试请求数
    ml_half_open_max_calls: int = 1
    # ML 单次推理超时 (秒), 超过则 asyncio.TimeoutError 并触发熔断器计数
    ml_inference_timeout: int = 5

    # ── STAB-P1-004 修复：SMTP 邮件熔断器 ──
    # 是否启用 SMTP 熔断器 (关闭后邮件发送不再拦截)
    smtp_circuit_breaker_enabled: bool = True
    # SMTP 连续失败次数阈值, 达到后熔断器打开 (快速失败, 不再尝试连接)
    smtp_failure_threshold: int = 5
    # SMTP 熔断器打开后恢复时间 (秒)
    smtp_recovery_timeout: int = 60
    # SMTP 半开状态允许的最大测试请求数
    smtp_half_open_max_calls: int = 1

    # ── STAB-P1-005 修复：Celery broker 熔断器 ──
    # 是否启用 Celery broker 熔断器 (关闭后 check_celery_worker 不再拦截)
    celery_circuit_breaker_enabled: bool = True
    # broker 连续失败次数阈值, 达到后熔断器打开 (健康检查快速失败)
    celery_failure_threshold: int = 5
    # Celery 熔断器打开后恢复时间 (秒)
    celery_recovery_timeout: int = 30
    # Celery 半开状态允许的最大测试请求数
    celery_half_open_max_calls: int = 1

    # M-L 修复：可观测性缓冲区大小可配置化
    observability_pending_logs_maxlen: int = 1000
    # RES-P1-004: 默认值从 10000 降至 1000, 避免死缓冲区占用过多内存
    observability_max_buffer_size: int = 1000

    @model_validator(mode="after")
    def apply_env_defaults(self) -> "Settings":
        # M-Core-1 修复说明：本 validator 中对 self.jwt_secret_key / self.pii_encryption_key
        # 的赋值仅在 Settings 实例化时执行（模块级 `settings = Settings()`），
        # 该过程位于应用启动阶段且为单线程，不存在并发突变。Pydantic v2 的 model_validator
        # (mode="after") 在构造完成前不会暴露实例给其他线程，因此此处突变是安全的。
        if self.app_env.lower() == "production" and self.database_url.startswith(
            "sqlite"
        ):
            raise ValueError(
                "DATABASE_URL must be explicitly set in production (cannot use sqlite)"
            )
        if (
            self.app_env.lower() == "production"
            and self.jwt_secret_key in _INSECURE_KEYS
        ):
            raise ValueError(
                "JWT_SECRET_KEY is required and must be secure in production. "
                'Generate a strong key with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        # SEC-P1-002 修复：生产环境强制密码重置链接使用 HTTPS
        # 原问题: password_reset_base_url 默认 http://localhost:5173/reset-password
        # 生产环境若未配置或配置为 HTTP, 重置链接中的 token 可被中间人攻击窃取
        if (
            self.app_env.lower() == "production"
            and not self.password_reset_base_url.lower().startswith("https://")
        ):
            raise ValueError(
                "PASSWORD_RESET_BASE_URL must use HTTPS in production. "
                "HTTP reset links expose password reset tokens to man-in-the-middle attacks. "
                "Set PASSWORD_RESET_BASE_URL to https://your-domain.com/reset-password in .env."
            )
        if (
            self.jwt_secret_key in _INSECURE_KEYS
            and self.app_env.lower() != "production"
        ):
            self.jwt_secret_key = secrets.token_urlsafe(32)
            warnings.warn(
                "⚠️  JWT_SECRET_KEY was empty/insecure — auto-generated a random key for this session. "
                "Set JWT_SECRET_KEY in .env for persistent tokens across restarts.",
                UserWarning,
                stacklevel=2,
            )
        # C-02 修复：将 PII 密钥的开发环境自动生成迁移到 model_validator，
        # 在 Settings 初始化时完成，避免运行时通过 object.__setattr__ 突变（线程不安全）。
        # 生产环境缺失密钥由下方模块级检查拦截；此处仅处理开发环境。
        # P0-1.2: 开发环境持久化自动生成的密钥到 .pii_key 文件, 避免重启后历史 PII 不可解密
        if not self.pii_encryption_key and self.app_env.lower() != "production":
            pii_key_file = BACKEND_DIR / ".pii_key"
            # 优先从持久化文件加载 (保持重启后密钥一致)
            if pii_key_file.exists():
                try:
                    saved_key = pii_key_file.read_text(encoding="utf-8").strip()
                    if saved_key:
                        self.pii_encryption_key = saved_key
                        logger.info(
                            "PII_ENCRYPTION_KEY loaded from %s (dev persistence)",
                            pii_key_file.name,
                        )
                except OSError:
                    logger.warning(
                        "Failed to read PII key file %s, will generate new key",
                        pii_key_file,
                    )
            # 文件不存在或读取失败: 生成新密钥并持久化
            if not self.pii_encryption_key:
                from cryptography.fernet import Fernet

                self.pii_encryption_key = Fernet.generate_key().decode()
                try:
                    pii_key_file.write_text(self.pii_encryption_key, encoding="utf-8")
                    logger.info("PII key persisted to %s (dev only)", pii_key_file.name)
                except OSError:
                    logger.warning("Failed to persist PII key to %s", pii_key_file)
                warnings.warn(
                    "⚠️  PII_ENCRYPTION_KEY 未配置, 已自动生成并持久化到 .pii_key 文件. "
                    "仅用于本地开发. 生产环境必须显式配置 PII_ENCRYPTION_KEY 环境变量.",
                    UserWarning,
                    stacklevel=2,
                )
        # M-Core-2 修复：CORS 通配符校验移到启动时（model_validator）执行一次，
        # 避免每次请求访问 cors_origins_list 属性时重复校验。
        self._validate_cors_origins()
        return self

    def _validate_cors_origins(self) -> None:
        """启动时校验 CORS 配置：allow_credentials=True 时禁止通配符 '*'。"""
        raw = self.cors_allowed_origins.strip()
        if not raw:
            return
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        if "*" in origins:
            raise ValueError(
                "CORS 配置错误：allow_credentials=True 时不允许使用通配符 '*'。"
                "请显式配置受信域名列表，例如：https://example.com,https://app.example.com"
            )

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 7
    password_reset_token_expire_minutes: int = 30

    # SEC-P1-002 修复：生产环境 (app_env=production) 必须配置 https:// 前缀
    # 默认值仅用于本地开发, 启动时由 apply_env_defaults 校验
    password_reset_base_url: str = "http://localhost:5173/reset-password"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = ""

    model_dir: str = "models"
    enable_seed: bool = False

    structured_model_mode: str = "primary"  # "primary" | "fallback"

    # ── 结构化预测实验性路径开关 ──
    # True (默认): 执行 3 路实验性推理, 提供对比数据
    # False: 跳过实验路径, 减少 CPU 放大 4 倍 (生产环境可选关闭)
    structured_experimental_enabled: bool = True

    # ── RES-P0-001 修复：ModelEngine 模型缓存 LRU 上限 ──
    # 防止 BERT+Keras 等大模型无界累积导致 OOM. 20 足够覆盖 PRELOAD_IDS(10) + 实验性模型
    # 0 表示禁用 LRU (仅用于测试, 生产环境不建议)
    model_cache_maxsize: int = 20

    # ── v1.25 路由配置 ──
    route_feature_coverage_threshold: float = 0.80
    route_lite_min_text_length: int = 20

    # ── v1.26 轻特征模型召回优化配置 ──
    lite_decision_threshold: float = 0.40
    crisis_keywords: list[str] = [
        "想死",
        "自杀",
        "自残",
        "活不下去",
        "不想活",
        "结束生命",
        "死了算了",
        "一死了之",
        "不如死了",
        "死了一了百了",
    ]

    cors_allowed_origins: str = ""

    # P0-S2 修复：受信反向代理 IP 列表（逗号分隔），仅这些 IP 的 X-Forwarded-For 头会被信任
    # 生产环境应配置为 nginx/ALB 的 IP，防止客户端伪造 X-Forwarded-For 绕过限流
    trusted_proxies: str = ""

    # PII 加密密钥 (v1.27): 用于敏感字段 (email/phone/emergency_contact) 加密
    pii_encryption_key: str = ""
    # P2-4: PII 密钥轮换 - 旧密钥列表 (逗号分隔, 仅用于解密回退)
    # 轮换流程: 将旧密钥加入此列表 → 新密钥设为 pii_encryption_key → 运行 scripts/rotate_pii_keys.py
    # 轮换完成后可清除此列表
    # SEC-C: 完整轮换 SOP 见 docs/ops/secrets-rotation-sop.md (4 类 Secrets 生命周期管理)
    pii_previous_keys: str = ""

    # ── RES-P0-002 修复：日志轮转配置 ──
    # 日志目录 (相对于 BACKEND_DIR, 默认 backend/logs/)
    log_dir: str = "logs"
    # 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    log_level: str = "INFO"
    # 单个日志文件最大字节数 (默认 10MB), 超过后触发轮转
    log_max_bytes: int = 10 * 1024 * 1024
    # 保留的备份文件数 (超过后删除最旧的)
    log_backup_count: int = 5
    # 是否启用文件日志 (生产环境建议显式设为 true)
    log_to_file: bool = False
    # 是否启用控制台日志输出 (默认启用, 测试环境可关闭以减少噪音)
    log_console: bool = True

    # Sentry 配置
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1

    # ── v1.37 Grafana 仪表盘配置 ──
    # Grafana Service Account Token (用于 JSON Datasource 调用后端 /grafana/* 时的鉴权)
    # 留空 (None) 表示禁用 SA 鉴权路径, 仅允许 admin JWT 鉴权
    grafana_service_token: str | None = None

    # ── CRIT-006/007 修复：告警 Webhook 和 Metrics 端点鉴权 ──
    # AlertManager Webhook 共享密钥（留空时仅允许开发环境访问）
    alertmanager_webhook_secret: str = ""
    # Prometheus /metrics 端点访问令牌（留空时仅允许开发环境访问）
    metrics_access_token: str = ""

    # ── SEC-002/003 修复：Refresh Token httpOnly Cookie 配置 ──
    # 阶段1：后端双轨模式，同时支持 JSON body 和 Cookie 传递 refresh_token
    # Cookie 名称
    refresh_cookie_name: str = "refresh_token"
    # Cookie 路径（限制为 /api/v1/auth 以缩小范围）
    refresh_cookie_path: str = "/api/v1/auth"
    # 是否启用 Cookie 模式（开发环境可关闭以简化调试）
    refresh_cookie_enabled: bool = True

    # ── SEC-P1-005 修复：异常访问检测 ──
    # 周期扫描 OperationLog, 检测高频/非工作时间/异地/横向越权访问
    # 关联 alert_rules.py AR-303~AR-306 + tasks/anomaly_detection.py
    # 关联 metrics.py anomaly_access_detected_total / anomaly_access_last_detected_at
    anomaly_detection_enabled: bool = True
    # 高频访问检测: 同一用户 N 分钟内操作数超阈值
    anomaly_high_freq_window_minutes: int = 5
    anomaly_high_freq_threshold: int = 100
    # 非工作时间访问检测: 22:00~06:00 视为非工作时间 (UTC 小时)
    anomaly_off_hours_start: int = 22
    anomaly_off_hours_end: int = 6
    # 异地访问检测: 同一用户 N 小时内不同 IP 数量超阈值
    # 注: 当前无 GeoIP 解析, 简化为基于 IP 数量的检测
    anomaly_cross_region_window_hours: int = 24
    anomaly_cross_region_ip_threshold: int = 3
    # 横向越权访问检测: 同一用户 N 分钟内访问的不同 target_type 数量超阈值
    # 咨询师正常工作涉及多 target_type, 阈值按 operator_role 区分
    anomaly_lateral_window_minutes: int = 30
    anomaly_lateral_target_type_threshold: int = 5
    # 异常检测扫描间隔 (秒), Celery beat 调度使用
    anomaly_scan_interval_seconds: int = 300

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allowed_origins.strip()
        if not raw:
            # 未显式配置: 开发环境提供开发端口默认值；生产环境返回空列表（拒绝跨域）
            if self.app_env.lower() == "production":
                return []
            return ["http://localhost:5173", "http://localhost:3000"]
        # M-Core-2 修复：通配符校验已移至 model_validator 启动时执行，
        # 此处仅做解析，避免每次请求重复校验。
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def SKLEARN_VERSION(self) -> str | None:
        """延迟首次访问时导入 sklearn 并缓存版本号。

        H-Core-5 修复：原实现为模块级普通函数，调用方写 settings.SKLEARN_VERSION
        (不带括号) 会得到函数对象而非版本字符串。改为 @property 符合 lazy property 语义。
        Windows 上导入 sklearn 可能触发 DLL 初始化崩溃，延迟到首次访问可避免模块加载阶段失败。
        """
        return _get_sklearn_version()


settings = Settings()

# 启动时检查：如果 JWT 密钥为空或不安全，在生产环境下阻止启动
if (
    settings.jwt_secret_key in _INSECURE_KEYS
    and settings.app_env.lower() == "production"
):
    # P1-E 修复：使用 logger.critical 替代 print()，便于生产环境统一日志收集
    logger.critical(
        "JWT_SECRET_KEY is missing or using a default/insecure value in production mode. "
        "The application cannot start without a secure JWT secret key. "
        'Generate a strong key with: python -c "import secrets; print(secrets.token_urlsafe(32))" '
        "and set it in your .env file.",
    )
    sys.exit(1)

# 开发环境下仅发出警告
if (
    settings.jwt_secret_key in _INSECURE_KEYS
    and settings.app_env.lower() != "production"
):
    warnings.warn(
        "⚠️  安全警告: JWT_SECRET_KEY 使用默认值或不安全值!\n"
        "   请立即生成安全密钥并更新 .env 文件:\n"
        '   python -c "import secrets; print(secrets.token_urlsafe(32))"\n'
        "   生产环境下使用不安全密钥将导致应用无法启动!",
        UserWarning,
        stacklevel=2,
    )

# P1-INFRA-003/004 修复：生产环境强制要求 PII 加密密钥、Webhook 和 Metrics 鉴权令牌
if settings.app_env.lower() == "production":
    _missing_prod_secrets: list[str] = []
    if not settings.pii_encryption_key:
        _missing_prod_secrets.append("PII_ENCRYPTION_KEY")
    if not settings.alertmanager_webhook_secret:
        _missing_prod_secrets.append("ALERTMANAGER_WEBHOOK_SECRET")
    if not settings.metrics_access_token:
        _missing_prod_secrets.append("METRICS_ACCESS_TOKEN")
    if _missing_prod_secrets:
        # P1-E 修复：使用 logger.critical 替代 print()，便于生产环境统一日志收集
        logger.critical(
            "以下密钥在生产环境未配置: %s。应用无法启动。请在 .env 文件中设置这些密钥。",
            ", ".join(_missing_prod_secrets),
        )
        sys.exit(1)


def __getattr__(name: str):
    """模块级懒加载属性 (PEP 562)。

    H-Core-5 修复：为 `from app.core.config import SKLEARN_VERSION` 提供向后兼容访问，
    返回版本字符串 (而非函数对象)，延迟首次访问时执行 sklearn 导入并缓存。
    """
    if name == "SKLEARN_VERSION":
        return _get_sklearn_version()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
