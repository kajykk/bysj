"""MAINT-P2-005: services __init__.py re-export tests."""

from __future__ import annotations


class TestServicesInitImports:
    """services __init__.py should import without cycles."""

    def test_module_importable(self):
        import app.services as svc

        assert svc is not None

    def test_no_circular_import(self):
        """Importing app.services should not trigger app.api imports."""
        import sys

        mods_before = set(sys.modules.keys())
        import app.services  # noqa: F401

        mods_after = set(sys.modules.keys())
        new_mods = mods_after - mods_before
        forbidden = {m for m in new_mods if m.startswith("app.api.")}
        assert not forbidden, f"services __init__ triggered api imports: {forbidden}"


class TestServicesAllCompleteness:
    """__all__ should include all public symbols."""

    def test_all_is_list(self):
        import app.services as svc

        assert isinstance(svc.__all__, list)
        assert len(svc.__all__) > 0

    def test_all_names_exist_in_module(self):
        import app.services as svc

        for name in svc.__all__:
            assert hasattr(svc, name), f"{name} in __all__ but not in module"

    def test_all_no_duplicates(self):
        import app.services as svc

        assert len(svc.__all__) == len(set(svc.__all__)), "__all__ has duplicates"

    def test_all_contains_key_services(self):
        import app.services as svc

        key_services = {
            "AdminService",
            "AuthService",
            "RiskService",
            "WarningService",
            "ModelPredictService",
            "ReviewService",
            "GDPRService",
            "ValidationEngine",
            "MttrService",
            "CanaryManager",
            "EmailService",
            "CounselorService",
            "InterventionService",
            "UserDataService",
            "ContentService",
            "ExperimentService",
            "ObservabilityExporter",
            "ObservabilityCollector",
        }
        assert key_services.issubset(set(svc.__all__))

    def test_export_count_meets_threshold(self):
        """__init__.py should export at least 50 symbols (was 2 before)."""
        import app.services as svc

        assert len(svc.__all__) >= 50


class TestServicesSingletons:
    """Module-level singleton instances should be accessible."""

    def test_auto_rollback_service_singleton(self):
        from app.services import auto_rollback_service

        assert auto_rollback_service is not None

    def test_canary_manager_singleton(self):
        from app.services import canary_manager

        assert canary_manager is not None

    def test_mttr_service_singleton(self):
        from app.services import mttr_service

        assert mttr_service is not None

    def test_excel_export_service_singleton(self):
        from app.services import excel_export_service

        assert excel_export_service is not None

    def test_pdf_report_service_singleton(self):
        from app.services import pdf_report_service

        assert pdf_report_service is not None

    def test_validation_engine_singleton(self):
        from app.services import validation_engine

        assert validation_engine is not None

    def test_observability_collector_singleton(self):
        from app.services import observability_collector

        assert observability_collector is not None

    def test_alert_lifecycle_service_singleton(self):
        from app.services import alert_lifecycle_service

        assert alert_lifecycle_service is not None


class TestBackwardCompatibility:
    """Existing direct imports should still work."""

    def test_experiment_service_still_importable_directly(self):
        from app.services.experiment_service import ExperimentService

        assert ExperimentService is not None

    def test_observability_exporter_still_importable_directly(self):
        from app.services.observability_exporter import ObservabilityExporter

        assert ObservabilityExporter is not None
