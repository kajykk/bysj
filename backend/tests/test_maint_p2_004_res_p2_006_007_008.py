"""MAINT-P2-004 / RES-P2-006 / RES-P2-007 / RES-P2-008 专项测试.

验证四项 P2 任务:
- MAINT-P2-004: BaseService/GenericCRUD 通用 CRUD 基类
- RES-P2-006: monitoring_snapshot.json → 统一 Prometheus
- RES-P2-007: Google Fonts CDN → 自托管字体 (CSP 清理)
- RES-P2-008: nginx Brotli 压缩启用
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# MAINT-P2-004: BaseService/GenericCRUD
# ============================================================================


class TestBaseServiceStructure:
    """MAINT-P2-004: BaseService 模块结构测试."""

    def test_module_exists(self) -> None:
        """base_service 模块存在."""
        from app.services import base_service

        assert base_service is not None

    def test_base_service_class_exists(self) -> None:
        """BaseService 类存在."""
        from app.services.base_service import BaseService

        assert BaseService is not None

    def test_not_found_error_exists(self) -> None:
        """NotFoundError 异常存在."""
        from app.services.base_service import NotFoundError

        assert NotFoundError is not None

    def test_base_service_is_generic(self) -> None:
        """BaseService 是泛型类 (支持 TypeVar)."""
        from app.services.base_service import BaseService

        # 检查 __class_getitem__ 是否存在 (Generic 类的标志)
        assert hasattr(BaseService, "__class_getitem__")

    def test_module_has_maint_p2_004_annotation(self) -> None:
        """模块源码标注 MAINT-P2-004."""
        from app.services import base_service

        source = inspect.getsource(base_service)
        assert "MAINT-P2-004" in source

    def test_base_service_has_crud_methods(self) -> None:
        """BaseService 包含 5 个 CRUD 方法."""
        from app.services.base_service import BaseService

        assert hasattr(BaseService, "get_by_id")
        assert hasattr(BaseService, "get_by_id_or_404")
        assert hasattr(BaseService, "list_paginated")
        assert hasattr(BaseService, "create")
        assert hasattr(BaseService, "update")
        assert hasattr(BaseService, "delete")

    def test_base_service_has_model_attribute(self) -> None:
        """BaseService 有 model 类属性 (子类需设置)."""
        from app.services.base_service import BaseService

        # model 是类型注解, 检查 __annotations__
        assert "model" in BaseService.__annotations__


@pytest.mark.asyncio
class TestBaseServiceBehavior:
    """MAINT-P2-004: BaseService 行为测试."""

    async def test_not_found_error_message(self) -> None:
        """NotFoundError 包含 model_name 和 record_id."""
        from app.services.base_service import NotFoundError

        error = NotFoundError("WarningNotification", 999)
        assert "WarningNotification" in str(error)
        assert "999" in str(error)
        assert error.model_name == "WarningNotification"
        assert error.record_id == 999

    async def test_get_by_id_or_404_raises_not_found(self) -> None:
        """get_by_id_or_404 在记录不存在时抛出 NotFoundError."""
        from app.models.risk import WarningNotification
        from app.services.base_service import BaseService, NotFoundError

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        class WarningService(BaseService):
            model = WarningNotification

        service = WarningService(mock_db)
        with pytest.raises(NotFoundError):
            await service.get_by_id_or_404(999)

    async def test_delete_returns_false_when_not_found(self) -> None:
        """delete 在记录不存在时返回 False."""
        from app.models.risk import WarningNotification
        from app.services.base_service import BaseService

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        class WarningService(BaseService):
            model = WarningNotification

        service = WarningService(mock_db)
        result = await service.delete(999)
        assert result is False

    async def test_list_paginated_returns_tuple(self) -> None:
        """list_paginated 返回 (records, total) 元组."""
        from app.models.risk import WarningNotification
        from app.services.base_service import BaseService

        mock_db = AsyncMock()
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        list_result = MagicMock()
        list_scalars = MagicMock()
        list_scalars.all.return_value = []
        list_result.scalars.return_value = list_scalars
        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        class WarningService(BaseService):
            model = WarningNotification

        service = WarningService(mock_db)
        records, total = await service.list_paginated(offset=0, limit=10)
        assert total == 5
        assert isinstance(records, list)


# ============================================================================
# RES-P2-006: monitoring_snapshot.json → 统一 Prometheus
# ============================================================================


class TestResP2006MetricsStructure:
    """RES-P2-006: metrics.py 新增 model_* Gauge."""

    def test_model_cache_size_gauge_exists(self) -> None:
        """model_cache_size Gauge 存在."""
        from app.core.metrics import model_cache_size

        assert model_cache_size is not None

    def test_model_uptime_seconds_gauge_exists(self) -> None:
        """model_uptime_seconds Gauge 存在."""
        from app.core.metrics import model_uptime_seconds

        assert model_uptime_seconds is not None

    def test_model_high_critical_ratio_gauge_exists(self) -> None:
        """model_high_critical_ratio Gauge 存在."""
        from app.core.metrics import model_high_critical_ratio

        assert model_high_critical_ratio is not None

    def test_model_high_critical_count_gauge_exists(self) -> None:
        """model_high_critical_count Gauge 存在."""
        from app.core.metrics import model_high_critical_count

        assert model_high_critical_count is not None

    def test_model_fallback_count_gauge_exists(self) -> None:
        """model_fallback_count Gauge 存在."""
        from app.core.metrics import model_fallback_count

        assert model_fallback_count is not None

    def test_model_experimental_hit_count_gauge_exists(self) -> None:
        """model_experimental_hit_count Gauge 存在."""
        from app.core.metrics import model_experimental_hit_count

        assert model_experimental_hit_count is not None

    def test_model_experimental_miss_count_gauge_exists(self) -> None:
        """model_experimental_miss_count Gauge 存在."""
        from app.core.metrics import model_experimental_miss_count

        assert model_experimental_miss_count is not None

    def test_model_structured_total_gauge_exists(self) -> None:
        """model_structured_total Gauge 存在."""
        from app.core.metrics import model_structured_total

        assert model_structured_total is not None

    def test_metrics_has_res_p2_006_annotation(self) -> None:
        """metrics.py 标注 RES-P2-006."""
        from app.core import metrics

        source = inspect.getsource(metrics)
        assert "RES-P2-006" in source


class TestResP2006ModelEngineIntegration:
    """RES-P2-006: model_engine._publish_to_prometheus 方法."""

    def test_publish_to_prometheus_method_exists(self) -> None:
        """_publish_to_prometheus 方法存在."""
        from app.core.model_engine import ModelEngine

        assert hasattr(ModelEngine, "_publish_to_prometheus")
        assert callable(ModelEngine._publish_to_prometheus)

    def test_persist_loop_calls_publish_to_prometheus(self) -> None:
        """_persist_loop 调用 _publish_to_prometheus."""
        from app.core.model_engine import ModelEngine

        source = inspect.getsource(ModelEngine._persist_loop)
        assert "_publish_to_prometheus" in source
        assert "RES-P2-006" in source

    def test_publish_to_prometheus_updates_gauges(self) -> None:
        """_publish_to_prometheus 更新 metrics.py 中的 Gauge."""
        from app.core.model_engine import ModelEngine

        source = inspect.getsource(ModelEngine._publish_to_prometheus)
        assert "model_cache_size" in source
        assert "model_uptime_seconds" in source
        assert "model_high_critical_ratio" in source
        assert "model_fallback_count" in source
        assert "model_fallback_rate" in source

    def test_publish_to_prometheus_has_res_p2_006_annotation(self) -> None:
        """_publish_to_prometheus 标注 RES-P2-006."""
        from app.core.model_engine import ModelEngine

        source = inspect.getsource(ModelEngine._publish_to_prometheus)
        assert "RES-P2-006" in source

    def test_persist_loop_retains_snapshot_file(self) -> None:
        """_persist_loop 保留 monitoring_snapshot.json (向后兼容)."""
        from app.core.model_engine import ModelEngine

        source = inspect.getsource(ModelEngine._persist_loop)
        assert "monitoring_snapshot.json" in source


# ============================================================================
# RES-P2-007: Google Fonts CDN → 自托管字体
# ============================================================================


class TestResP2007CspCleanup:
    """RES-P2-007: CSP 清理 Google Fonts 白名单."""

    def test_csp_ts_exists(self) -> None:
        """csp.ts 文件存在."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        csp_file = frontend_root / "src" / "csp.ts"
        assert csp_file.exists()

    def test_csp_ts_has_res_p2_007_annotation(self) -> None:
        """csp.ts 标注 RES-P2-007."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        csp_file = frontend_root / "src" / "csp.ts"
        content = csp_file.read_text(encoding="utf-8")
        assert "RES-P2-007" in content

    def test_csp_ts_no_google_fonts_in_prod(self) -> None:
        """PROD_POLICY 不包含 fonts.googleapis.com (非注释行)."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        csp_file = frontend_root / "src" / "csp.ts"
        content = csp_file.read_text(encoding="utf-8")
        # 检查非注释行中是否包含 Google Fonts
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            if "fonts.googleapis.com" in stripped or "fonts.gstatic.com" in stripped:
                pytest.fail(f"Google Fonts reference found in non-comment line: {stripped}")

    def test_csp_ts_no_google_fonts_in_dev(self) -> None:
        """DEV_POLICY 不包含 fonts.gstatic.com (非注释行)."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        csp_file = frontend_root / "src" / "csp.ts"
        content = csp_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                continue
            if "fonts.gstatic.com" in stripped or "fonts.googleapis.com" in stripped:
                pytest.fail(f"Google Fonts reference found in non-comment line: {stripped}")

    def test_nginx_conf_no_google_fonts(self) -> None:
        """nginx.conf CSP header 不包含 Google Fonts."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        nginx_file = frontend_root / "nginx.conf"
        content = nginx_file.read_text(encoding="utf-8")
        assert "fonts.googleapis.com" not in content
        assert "fonts.gstatic.com" not in content

    def test_index_html_no_google_fonts_link(self) -> None:
        """index.html 不包含 Google Fonts <link> 标签 (非注释行)."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        index_file = frontend_root / "index.html"
        content = index_file.read_text(encoding="utf-8")
        # 检查非注释行中是否包含 Google Fonts 引用
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("<!--") or stripped.startswith("-->"):
                continue
            if "fonts.googleapis.com" in stripped and "<link" in stripped.lower():
                pytest.fail(f"Google Fonts <link> found: {stripped}")


# ============================================================================
# RES-P2-008: nginx Brotli 压缩启用
# ============================================================================


class TestResP2008NginxBrotli:
    """RES-P2-008: nginx Brotli 压缩配置.

    Brotli 已按部署决策移除 (Alpine 3.22 brotli 模块与 nginx 1.29.3 不兼容,
    nginx.conf 中注明 gzip 仍可用), 测试断言移除说明存在且 gzip 生效.
    """

    def test_nginx_conf_brotli_removed_with_reason(self) -> None:
        """nginx.conf 明确注释 Brotli 移除原因 (RES-P2-008 决策)."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        nginx_file = frontend_root / "nginx.conf"
        content = nginx_file.read_text(encoding="utf-8")
        assert "RES-P2-008" in content
        assert "Brotli 压缩已移除" in content
        # 不允许存在启用的 brotli 指令 (Alpine 3.22 不兼容)
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("brotli on") and not stripped.startswith("#"):
                pytest.fail("brotli on; 不应存在 (Alpine 3.22 不兼容, 已移除)")

    def test_nginx_conf_has_gzip_fallback(self) -> None:
        """nginx.conf gzip 仍启用作为压缩回退."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        nginx_file = frontend_root / "nginx.conf"
        content = nginx_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "gzip on;":
                return
        pytest.fail("gzip on; not found in nginx.conf")

    def test_nginx_conf_has_res_p2_008_annotation(self) -> None:
        """nginx.conf 标注 RES-P2-008."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        nginx_file = frontend_root / "nginx.conf"
        content = nginx_file.read_text(encoding="utf-8")
        assert "RES-P2-008" in content

    def test_nginx_conf_has_load_module_comment(self) -> None:
        """nginx.conf 有 Brotli 移除说明 (load_module 方案随移除不再生效)."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        nginx_file = frontend_root / "nginx.conf"
        content = nginx_file.read_text(encoding="utf-8")
        assert "RES-P2-008" in content
        assert "Brotli" in content or "brotli" in content


class TestResP2008Dockerfile:
    """RES-P2-008: Dockerfile Brotli 模块决策.

    Brotli 已移除 (Alpine 3.22 nginx-mod-http-brotli 与 nginx 1.29.3 不兼容),
    Dockerfile 中注明了移除原因与恢复条件, gzip 压缩不受影响.
    """

    def test_dockerfile_brotli_removed_with_reason(self) -> None:
        """Dockerfile 明确注释 Brotli 模块移除原因."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        dockerfile = frontend_root / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "RES-P2-008" in content
        assert "移除" in content
        # 移除原因必须注明 (Alpine 3.22 不兼容)
        assert "Alpine" in content
        # 注释行说明替代方案 (gzip 不受影响)
        assert "gzip" in content

    def test_dockerfile_gzip_unaffected(self) -> None:
        """Dockerfile 说明 gzip 压缩不受影响."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        dockerfile = frontend_root / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "gzip" in content

    def test_dockerfile_has_res_p2_008_annotation(self) -> None:
        """Dockerfile 标注 RES-P2-008."""
        frontend_root = Path(__file__).parent.parent.parent / "frontend"
        dockerfile = frontend_root / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "RES-P2-008" in content
