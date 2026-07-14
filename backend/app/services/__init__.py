"""Services package - unified re-export entry point.

MAINT-P2-005: 补齐 re-export, 统一导入入口。
调用方应从 app.services 导入, 而非直接从子模块导入。
"""

# ── Admin ──
from .admin_service import AdminService

# ── Alert Lifecycle ──
from .alert_lifecycle_service import (
    AlertLifecycleService,
    AlertStatus,
    NotificationChannel,
    alert_lifecycle_service,
)

# ── Anomaly Detection ──
from .anomaly_detection_service import AnomalyFinding, detect_all

# ── Auth ──
from .auth_service import AuthService

# ── Auto Rollback ──
from .auto_rollback_service import (
    AutoRollbackService,
    RollbackCheckResult,
    auto_rollback_service,
)

# ── Canary Fallback Monitor ──
from .canary_fallback_monitor import (
    is_canary_fallback_running,
    start_canary_fallback_monitor,
    stop_canary_fallback_monitor,
)

# ── Canary Manager ──
from .canary_manager import (
    CanaryManager,
    RollbackThresholds,
    TrafficDecision,
    canary_manager,
)

# ── Content ──
from .content_service import ContentService

# ── Counselor ──
from .counselor_service import CounselorService

# ── Crisis Export ──
from .crisis_export_service import CrisisExportService

# ── Drift Detector ──
from .drift_detector import DriftDetector

# ── Email ──
from .email_service import EmailService

# ── Excel Export ──
from .excel_export_service import (
    ExcelExportResult,
    ExcelExportService,
    excel_export_service,
)

# ── Excel Job Store ──
from .excel_job_store import ExcelJob, ExcelJobStore, excel_job_store

# ── Experiment Data ──
from .experiment_data import ExperimentDataManager

# ── Experiment Evaluator ──
from .experiment_evaluator import ExperimentEvaluator

# ── Experiment Metrics ──
from .experiment_metrics import ExperimentMetrics

# ── Experiment Service ──
from .experiment_service import ExperimentService

# ── Experiment Trainer ──
from .experiment_trainer import ExperimentTrainer

# ── GDPR ──
from .gdpr_service import GDPRService

# ── Input Validator ──
from .input_validator import InputValidator, ValidationResult, input_validator

# ── Intervention ──
from .intervention_service import (
    InterventionRecommendation,
    InterventionService,
)

# ── Model Predict ──
from .model_predict_service import ModelExperimentService, ModelPredictService

# ── MTTR ──
from .mttr_service import MttrService, MttrStats, mttr_service

# ── Observability Exporter ──
from .observability_exporter import ObservabilityExporter

# ── Observability Service ──
from .observability_service import (
    Counter,
    LatencyHistogram,
    ObservabilityCollector,
    observability_collector,
)

# ── PDF Job Store ──
from .pdf_job_store import PdfJob, PdfJobStore, pdf_job_store

# ── PDF Report ──
from .pdf_report_service import (
    PDFReportResult,
    PDFReportService,
    ReportData,
    pdf_report_service,
)

# ── Review ──
from .review_service import CrisisEventService, ReviewService

# ── Risk ──
from .risk_service import RiskService

# ── User Data ──
from .user_data_service import UserDataService

# ── Validation Engine ──
from .validation_engine import (
    ValidationEngine,
    ValidationMetrics,
    validation_engine,
)
from .validation_engine import (
    ValidationResult as EngineValidationResult,
)

# ── Warning ──
from .warning_service import WarningService

__all__ = [
    # Admin
    "AdminService",
    # Alert Lifecycle
    "AlertLifecycleService",
    "AlertStatus",
    "NotificationChannel",
    "alert_lifecycle_service",
    # Anomaly Detection
    "AnomalyFinding",
    "detect_all",
    # Auth
    "AuthService",
    # Auto Rollback
    "AutoRollbackService",
    "RollbackCheckResult",
    "auto_rollback_service",
    # Canary Fallback Monitor
    "is_canary_fallback_running",
    "start_canary_fallback_monitor",
    "stop_canary_fallback_monitor",
    # Canary Manager
    "CanaryManager",
    "RollbackThresholds",
    "TrafficDecision",
    "canary_manager",
    # Content
    "ContentService",
    # Counselor
    "CounselorService",
    # Crisis Export
    "CrisisExportService",
    # Drift Detector
    "DriftDetector",
    # Email
    "EmailService",
    # Excel Export
    "ExcelExportResult",
    "ExcelExportService",
    "excel_export_service",
    # Excel Job Store
    "ExcelJob",
    "ExcelJobStore",
    "excel_job_store",
    # Experiment Data
    "ExperimentDataManager",
    # Experiment Evaluator
    "ExperimentEvaluator",
    # Experiment Metrics
    "ExperimentMetrics",
    # Experiment Service
    "ExperimentService",
    # Experiment Trainer
    "ExperimentTrainer",
    # GDPR
    "GDPRService",
    # Input Validator
    "InputValidator",
    "ValidationResult",
    "input_validator",
    # Intervention
    "InterventionRecommendation",
    "InterventionService",
    # Model Predict
    "ModelExperimentService",
    "ModelPredictService",
    # MTTR
    "MttrService",
    "MttrStats",
    "mttr_service",
    # Observability Exporter
    "ObservabilityExporter",
    # Observability Service
    "Counter",
    "LatencyHistogram",
    "ObservabilityCollector",
    "observability_collector",
    # PDF Job Store
    "PdfJob",
    "PdfJobStore",
    "pdf_job_store",
    # PDF Report
    "PDFReportResult",
    "PDFReportService",
    "ReportData",
    "pdf_report_service",
    # Review
    "CrisisEventService",
    "ReviewService",
    # Risk
    "RiskService",
    # User Data
    "UserDataService",
    # Validation Engine
    "ValidationEngine",
    "ValidationMetrics",
    "EngineValidationResult",
    "validation_engine",
    # Warning
    "WarningService",
]
