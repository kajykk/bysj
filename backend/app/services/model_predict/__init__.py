"""Split implementation for model prediction and training orchestration.

The public compatibility facade remains ``app.services.model_predict_service``.
"""

from .fusion import FusionMixin
from .inference import InferenceService

__all__ = ["FusionMixin", "InferenceService"]
