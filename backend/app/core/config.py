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
DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'depression_system.db').as_posix()}"

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
            _TRANSFORMERS_AVAILABLE = importlib.util.find_spec("transformers") is not None
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

# SKLEARN_VERSION is accessed lazily via property to avoid importing sklearn
# at module load time, which can crash on Windows with exit code -1073741510.
_SKLEARN_VERSION_VALUE: str | None = None


def SKLEARN_VERSION() -> str | None:  # type: ignore[return]
    global _SKLEARN_VERSION_VALUE
    if _SKLEARN_VERSION_VALUE is None:
        _SKLEARN_VERSION_VALUE = _get_sklearn_version()
    return _SKLEARN_VERSION_VALUE

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

    @model_validator(mode="after")
    def apply_env_defaults(self) -> "Settings":
        if self.app_env.lower() == "production" and self.database_url.startswith("sqlite"):
            raise ValueError("DATABASE_URL must be explicitly set in production (cannot use sqlite)")
        if self.app_env.lower() == "production" and self.jwt_secret_key in _INSECURE_KEYS:
            raise ValueError(
                "JWT_SECRET_KEY is required and must be secure in production. "
                "Generate a strong key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        if self.jwt_secret_key in _INSECURE_KEYS and self.app_env.lower() != "production":
            self.jwt_secret_key = secrets.token_urlsafe(32)
            warnings.warn(
                "⚠️  JWT_SECRET_KEY was empty/insecure — auto-generated a random key for this session. "
                "Set JWT_SECRET_KEY in .env for persistent tokens across restarts.",
                UserWarning,
                stacklevel=2,
            )
        return self

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 7
    password_reset_token_expire_minutes: int = 30

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

    # ── v1.25 路由配置 ──
    route_feature_coverage_threshold: float = 0.80
    route_lite_min_text_length: int = 20

    # ── v1.26 轻特征模型召回优化配置 ──
    lite_decision_threshold: float = 0.40
    crisis_keywords: list[str] = [
        "想死", "自杀", "自残", "活不下去", "不想活",
        "结束生命", "死了算了", "一死了之", "不如死了", "死了一了百了",
    ]

    cors_allowed_origins: str = ""

    # PII 加密密钥 (v1.27): 用于敏感字段 (email/phone/emergency_contact) 加密
    pii_encryption_key: str = ""

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

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_allowed_origins.strip()
        if not raw:
            # 未显式配置: 开发环境提供开发端口默认值；生产环境返回空列表（拒绝跨域）
            if self.app_env.lower() == "production":
                return []
            return ["http://localhost:5173", "http://localhost:3000"]
        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        # 修复：allow_credentials=True 时禁止通配符 "*"，否则浏览器可能反射任意 Origin
        # 导致任意站点可携带 Cookie 发起跨域请求
        if "*" in origins:
            raise ValueError(
                "CORS 配置错误：allow_credentials=True 时不允许使用通配符 '*'。"
                "请显式配置受信域名列表，例如：https://example.com,https://app.example.com"
            )
        return origins


settings = Settings()

# 启动时检查：如果 JWT 密钥为空或不安全，在生产环境下阻止启动
if settings.jwt_secret_key in _INSECURE_KEYS and settings.app_env.lower() == "production":
    # P1-E 修复：使用 logger.critical 替代 print()，便于生产环境统一日志收集
    logger.critical(
        "JWT_SECRET_KEY is missing or using a default/insecure value in production mode. "
        "The application cannot start without a secure JWT secret key. "
        "Generate a strong key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\" "
        "and set it in your .env file.",
    )
    sys.exit(1)

# 开发环境下仅发出警告
if settings.jwt_secret_key in _INSECURE_KEYS and settings.app_env.lower() != "production":
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
