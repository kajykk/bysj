"""MAINT-P1-003 回归测试：contracts.py 契约聚合层

测试覆盖:
1. 模块可导入 (无循环导入)
2. 风险等级常量与 RISK_LEVELS frozenset
3. 预警动作/状态常量与 frozenset
4. 用户角色常量与 USER_ROLES
5. 用户状态常量与 USER_STATUSES
6. 通知渠道常量与 NOTIFY_CHANNELS
7. re-export 枚举与原始模块一致 (同一对象)
8. __all__ 完整性
9. normalize_risk_level / resolve_warning_status 函数行为
10. 向后兼容 (原有导入仍可用)
"""

from __future__ import annotations

# ===== 1. 模块导入与无循环导入 =====


class TestModuleImport:
    """contracts.py 可导入且无循环依赖."""

    def test_module_importable(self):
        import app.core.contracts as contracts

        assert contracts is not None

    def test_no_circular_import(self):
        """导入 contracts 不应触发 app.api/app.services 等重模块."""
        import sys

        # 清除可能已加载的模块以模拟首次导入
        mods_before = set(sys.modules.keys())
        import app.core.contracts  # noqa: F401

        mods_after = set(sys.modules.keys())
        new_mods = mods_after - mods_before
        # 不应加载 api/services 层
        forbidden = {
            m
            for m in new_mods
            if m.startswith("app.api.") or m.startswith("app.services.")
        }
        assert not forbidden, f"contracts.py 导入触发了禁止的模块: {forbidden}"


# ===== 2. 风险等级 =====


class TestRiskLevel:
    """风险等级常量."""

    def test_risk_level_map_values(self):
        from app.core.contracts import RISK_LEVEL_MAP

        assert RISK_LEVEL_MAP == {
            0: "none",
            1: "low",
            2: "medium",
            3: "high",
            4: "critical",
        }

    def test_risk_levels_frozenset(self):
        from app.core.contracts import RISK_LEVELS

        assert isinstance(RISK_LEVELS, frozenset)
        assert RISK_LEVELS == frozenset({"none", "low", "medium", "high", "critical"})

    def test_risk_levels_matches_map(self):
        from app.core.contracts import RISK_LEVEL_MAP, RISK_LEVELS

        assert RISK_LEVELS == frozenset(RISK_LEVEL_MAP.values())


# ===== 3. 预警动作与状态 =====


class TestWarningActions:
    """预警动作常量."""

    def test_action_values(self):
        from app.core.contracts import (
            WARNING_ACTION_ESCALATE,
            WARNING_ACTION_HANDLE,
            WARNING_ACTION_IGNORE,
        )

        assert WARNING_ACTION_HANDLE == "handle"
        assert WARNING_ACTION_IGNORE == "ignore"
        assert WARNING_ACTION_ESCALATE == "escalated"

    def test_warning_actions_frozenset(self):
        from app.core.contracts import WARNING_ACTIONS

        assert isinstance(WARNING_ACTIONS, frozenset)
        assert len(WARNING_ACTIONS) == 3


class TestWarningStatuses:
    """预警状态常量."""

    def test_status_values(self):
        from app.core.contracts import (
            WARNING_STATUS_ESCALATED,
            WARNING_STATUS_HANDLED,
            WARNING_STATUS_IGNORED,
            WARNING_STATUS_PENDING,
        )

        assert WARNING_STATUS_PENDING == "pending"
        assert WARNING_STATUS_HANDLED == "handled"
        assert WARNING_STATUS_IGNORED == "ignored"
        assert WARNING_STATUS_ESCALATED == "escalated"

    def test_warning_statuses_frozenset(self):
        from app.core.contracts import WARNING_STATUSES

        assert isinstance(WARNING_STATUSES, frozenset)
        assert len(WARNING_STATUSES) == 4

    def test_warning_audit_action_types(self):
        from app.core.contracts import (
            ACTION_TYPE_WARNING_ESCALATE,
            ACTION_TYPE_WARNING_HANDLE,
            ACTION_TYPE_WARNING_IGNORE,
            ACTION_TYPE_WARNING_READ,
            ACTION_TYPE_WARNING_READ_ALL,
        )

        assert ACTION_TYPE_WARNING_HANDLE == "warning_handle"
        assert ACTION_TYPE_WARNING_IGNORE == "warning_ignore"
        assert ACTION_TYPE_WARNING_READ == "warning_read"
        assert ACTION_TYPE_WARNING_READ_ALL == "warning_read_all"
        assert ACTION_TYPE_WARNING_ESCALATE == "warning_escalate"


# ===== 4. 用户角色 =====


class TestUserRoles:
    """用户角色常量."""

    def test_role_values(self):
        from app.core.contracts import (
            USER_ROLE_ADMIN,
            USER_ROLE_COUNSELOR,
            USER_ROLE_USER,
        )

        assert USER_ROLE_ADMIN == "admin"
        assert USER_ROLE_COUNSELOR == "counselor"
        assert USER_ROLE_USER == "user"

    def test_user_roles_frozenset(self):
        from app.core.contracts import USER_ROLES

        assert isinstance(USER_ROLES, frozenset)
        assert USER_ROLES == frozenset({"admin", "counselor", "user"})

    def test_roles_match_deps_hierarchy_keys(self):
        """USER_ROLES 应与 deps.py ROLE_HIERARCHY 的 key 一致."""
        from app.core.contracts import USER_ROLES
        from app.core.deps import ROLE_HIERARCHY

        assert USER_ROLES == frozenset(ROLE_HIERARCHY.keys())

    def test_roles_match_user_model_constraint(self):
        """USER_ROLES 应与 models/user.py 的 CheckConstraint 一致."""
        from app.core.contracts import USER_ROLES

        assert "admin" in USER_ROLES
        assert "counselor" in USER_ROLES
        assert "user" in USER_ROLES


# ===== 5. 用户状态 =====


class TestUserStatuses:
    """用户状态常量."""

    def test_status_values(self):
        from app.core.contracts import (
            USER_STATUS_ACTIVE,
            USER_STATUS_DELETED,
            USER_STATUS_INACTIVE,
        )

        assert USER_STATUS_ACTIVE == "active"
        assert USER_STATUS_INACTIVE == "inactive"
        assert USER_STATUS_DELETED == "deleted"

    def test_user_statuses_frozenset(self):
        from app.core.contracts import USER_STATUSES

        assert isinstance(USER_STATUSES, frozenset)
        assert USER_STATUSES == frozenset({"active", "inactive", "deleted"})


# ===== 6. 通知渠道 =====


class TestNotifyChannels:
    """通知渠道常量."""

    def test_channel_values(self):
        from app.core.contracts import (
            NOTIFY_CHANNEL_EMAIL,
            NOTIFY_CHANNEL_IN_APP,
            NOTIFY_CHANNEL_SMS,
            NOTIFY_CHANNEL_WEBSOCKET,
        )

        assert NOTIFY_CHANNEL_IN_APP == "in_app"
        assert NOTIFY_CHANNEL_EMAIL == "email"
        assert NOTIFY_CHANNEL_SMS == "sms"
        assert NOTIFY_CHANNEL_WEBSOCKET == "websocket"

    def test_notify_channels_frozenset(self):
        from app.core.contracts import NOTIFY_CHANNELS

        assert isinstance(NOTIFY_CHANNELS, frozenset)
        assert NOTIFY_CHANNELS == frozenset({"in_app", "email", "sms", "websocket"})

    def test_matches_warning_service_allowed_channels(self):
        """NOTIFY_CHANNELS 应与 warning_service._ALLOWED_NOTIFY_CHANNELS 一致."""
        from app.core.contracts import NOTIFY_CHANNELS
        from app.services.warning_service import _ALLOWED_NOTIFY_CHANNELS

        assert NOTIFY_CHANNELS == _ALLOWED_NOTIFY_CHANNELS


# ===== 7. Re-export 枚举一致性 =====


class TestReExportedEnums:
    """re-export 的枚举应与原始模块为同一对象."""

    def test_binding_status_same_object(self):
        from app.core.contracts import BindingStatus
        from app.core.states import BindingStatus as OrigBindingStatus

        assert BindingStatus is OrigBindingStatus

    def test_review_reason_same_object(self):
        from app.core.contracts import ReviewReason
        from app.core.review_reasons import ReviewReason as OrigReviewReason

        assert ReviewReason is OrigReviewReason

    def test_review_reason_labels_same_object(self):
        from app.core.contracts import REVIEW_REASON_LABELS
        from app.core.review_reasons import REVIEW_REASON_LABELS as OrigLabels

        assert REVIEW_REASON_LABELS is OrigLabels

    def test_severity_same_object(self):
        from app.core.alert_rules import Severity as OrigSeverity
        from app.core.contracts import Severity

        assert Severity is OrigSeverity

    def test_binding_status_values(self):
        from app.core.contracts import BindingStatus

        assert BindingStatus.PLACEHOLDER.value == "placeholder"
        assert BindingStatus.ACTIVE.value == "active"
        assert BindingStatus.INACTIVE.value == "inactive"

    def test_severity_values(self):
        from app.core.contracts import Severity

        assert Severity.CRITICAL.value == "critical"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


# ===== 8. __all__ 完整性 =====


class TestAllCompleteness:
    """__all__ 应包含所有公开符号."""

    def test_all_is_list(self):
        from app.core.contracts import __all__

        assert isinstance(__all__, list)
        assert len(__all__) > 0

    def test_all_names_exist_in_module(self):
        """__all__ 中的每个名称都应在模块中可访问."""
        import app.core.contracts as contracts

        for name in contracts.__all__:
            assert hasattr(contracts, name), f"{name} in __all__ but not in module"

    def test_all_contains_key_symbols(self):
        from app.core.contracts import __all__

        key_symbols = {
            "RISK_LEVEL_MAP",
            "RISK_LEVELS",
            "WARNING_ACTION_HANDLE",
            "WARNING_STATUSES",
            "USER_ROLE_ADMIN",
            "USER_ROLES",
            "USER_STATUSES",
            "NOTIFY_CHANNELS",
            "BindingStatus",
            "ReviewReason",
            "Severity",
            "normalize_risk_level",
            "resolve_warning_status",
        }
        assert key_symbols.issubset(set(__all__))

    def test_all_no_duplicates(self):
        from app.core.contracts import __all__

        assert len(__all__) == len(set(__all__)), "__all__ has duplicates"


# ===== 9. 函数行为 =====


class TestNormalizeRiskLevel:
    """normalize_risk_level 函数行为 (向后兼容)."""

    def test_none_returns_none(self):
        from app.core.contracts import normalize_risk_level

        assert normalize_risk_level(None) == "none"

    def test_valid_levels(self):
        from app.core.contracts import normalize_risk_level

        assert normalize_risk_level(0) == "none"
        assert normalize_risk_level(1) == "low"
        assert normalize_risk_level(2) == "medium"
        assert normalize_risk_level(3) == "high"
        assert normalize_risk_level(4) == "critical"

    def test_unknown_level_returns_unknown(self, caplog):
        from app.core.contracts import normalize_risk_level

        result = normalize_risk_level(5)
        assert result == "unknown"
        result = normalize_risk_level(-1)
        assert result == "unknown"


class TestResolveWarningStatus:
    """resolve_warning_status 函数行为 (向后兼容)."""

    def test_not_handled_returns_pending(self):
        from app.core.contracts import resolve_warning_status

        assert resolve_warning_status(False, None) == "pending"
        assert resolve_warning_status(False, "handle") == "pending"

    def test_handled_with_handle(self):
        from app.core.contracts import WARNING_ACTION_HANDLE, resolve_warning_status

        assert resolve_warning_status(True, WARNING_ACTION_HANDLE) == "handled"

    def test_handled_with_ignore(self):
        from app.core.contracts import WARNING_ACTION_IGNORE, resolve_warning_status

        assert resolve_warning_status(True, WARNING_ACTION_IGNORE) == "ignored"

    def test_handled_with_escalate(self):
        from app.core.contracts import WARNING_ACTION_ESCALATE, resolve_warning_status

        assert resolve_warning_status(True, WARNING_ACTION_ESCALATE) == "escalated"

    def test_handled_no_action_returns_handled(self):
        from app.core.contracts import resolve_warning_status

        assert resolve_warning_status(True, None) == "handled"


# ===== 10. 向后兼容 =====


class TestBackwardCompatibility:
    """原有导入方式仍可用."""

    def test_original_imports_still_work(self):
        """原有从 contracts 导入的符号仍可用."""
        from app.core.contracts import (
            RISK_LEVEL_MAP,
            WARNING_ACTION_HANDLE,
            normalize_risk_level,
            resolve_warning_status,
        )

        assert RISK_LEVEL_MAP[4] == "critical"
        assert WARNING_ACTION_HANDLE == "handle"
        assert normalize_risk_level(3) == "high"
        assert resolve_warning_status(False, None) == "pending"

    def test_existing_importers_not_broken(self):
        """现有引用者 (counselor_service/warning_service/scheduler) 的导入仍可用."""
        # counselor_service 导入 ACTION_TYPE_WARNING_ESCALATE 等
        # warning_service 导入 ACTION_TYPE_WARNING_READ 等
        from app.core.contracts import (  # noqa: F401  # noqa: F401
            ACTION_TYPE_WARNING_ESCALATE,
            ACTION_TYPE_WARNING_HANDLE,
            ACTION_TYPE_WARNING_IGNORE,
            ACTION_TYPE_WARNING_READ,
            ACTION_TYPE_WARNING_READ_ALL,
            WARNING_ACTION_ESCALATE,
            WARNING_ACTION_HANDLE,
            WARNING_ACTION_IGNORE,
            normalize_risk_level,
            resolve_warning_status,
        )
