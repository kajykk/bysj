from fastapi import APIRouter

from app.core.openapi_responses import AUTH_ERROR_RESPONSES
from app.api.v1.admin import router as admin_router
from app.api.v1.admin_metrics import router as admin_metrics_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.observability import router as observability_router
from app.api.v1.silences import router as silences_router
from app.api.v1.grafana_adapter import router as grafana_adapter_router  # v1.37
from app.api.v1.auth import router as auth_router
from app.api.v1.canary import router as canary_router
from app.api.v1.counselor import router as counselor_router
from app.api.v1.gdpr import router as gdpr_router
from app.api.v1.metrics import router as metrics_router
from app.api.v1.model_predict import router as model_predict_router
from app.api.v1.monitoring import router as monitoring_router
from app.api.v1.reports import router as reports_router
from app.api.v1.review import router as review_router
from app.api.v1.user_content import router as user_content_router
from app.api.v1.user_data import router as user_data_router
from app.api.v1.user_intervention import router as user_intervention_router
from app.api.v1.user_risk import router as user_risk_router
from app.api.v1.user_upload import router as user_upload_router
from app.api.v1.user_warning import router as user_warning_router
from app.api.v1.validation import router as validation_router
from app.api.v1.version import router as version_router

api_router = APIRouter(prefix="/api/v1", responses=AUTH_ERROR_RESPONSES)
api_router.include_router(auth_router)
api_router.include_router(user_data_router)
api_router.include_router(user_warning_router)
api_router.include_router(user_intervention_router)
api_router.include_router(user_risk_router)
api_router.include_router(user_content_router)
api_router.include_router(user_upload_router)
api_router.include_router(model_predict_router)
api_router.include_router(monitoring_router)
api_router.include_router(canary_router)
api_router.include_router(validation_router)
api_router.include_router(reports_router)
api_router.include_router(review_router)
api_router.include_router(counselor_router)
api_router.include_router(admin_router)
api_router.include_router(version_router)
api_router.include_router(gdpr_router)
api_router.include_router(metrics_router)
api_router.include_router(admin_metrics_router)
api_router.include_router(alerts_router)
api_router.include_router(observability_router)
api_router.include_router(silences_router)
api_router.include_router(grafana_adapter_router)  # v1.37
