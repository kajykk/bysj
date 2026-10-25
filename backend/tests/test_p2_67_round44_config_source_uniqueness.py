"""ROUND_44 配置来源唯一性闸门.

两类「同一配置存在第二个来源」的漂移：

1. `getattr(settings, "<field>", <literal>)` 的兜底默认值必须等于
   `Settings.model_fields[field].default`。不等时，缺少该属性的 settings
   对象会静默使用另一个默认值，与声明默认值分叉。开工实测 13 处，2 处漂移：
   `structured_default_model`（兜底 v1.20 vs 声明 v1.23）、`model_dir`
   （兜底 None vs 声明 models）；本轮改为直接读取，剩 11 处全部一致。
2. 与 Settings 字段同名的环境变量不得在 `backend/app` 另开直读
   （pydantic 已消费 env / .env 并做类型解析，第二来源会绕过校验且
   `.env` 与进程环境可能不一致）。开工实测 3 处有意兜底：REDIS_URL ×2、
   SENTRY_DSN ×1；登记为显式允许项，并钉「settings 优先」与
   「sentry 仅库级兜底、main 透传 settings」。

扫描器只按属性名 / 环境变量名匹配，偏保守；自证用例确保已知点可见，
避免「恒空集合」式静默失效。
"""

from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]

CONFIG_REL = "app/core/config.py"
PREDICT_REL = "app/core/model_engine/predict.py"
METRICS_REL = "app/api/v1/metrics_helpers.py"
MAIN_REL = "app/main.py"
SENTRY_REL = "app/core/sentry.py"
CACHE_REL = "app/core/cache.py"
DEDUP_REL = "app/monitoring/dedup_lock.py"

# 唯一允许直读的「与 Settings 字段同名」的环境变量（显式兜底，不是漏改）
ALLOWLIST: dict[tuple[str, str], str] = {
    (CACHE_REL, "REDIS_URL"): (
        "settings.redis_url 优先；读取异常或值非法时回退进程环境"
    ),
    (DEDUP_REL, "REDIS_URL"): (
        "settings.redis_url 优先；读取异常时回退进程环境（warning 已自报）"
    ),
    (SENTRY_REL, "SENTRY_DSN"): (
        "init_sentry 库级直调兜底；main 始终透传 settings.sentry_dsn"
    ),
}

_UNRESOLVED = object()


def _read(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


def _app_trees():
    for p in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(BACKEND).as_posix()
        try:
            yield rel, ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue


def _func(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    return next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def _settings_defaults() -> dict[str, object]:
    from app.core.config import Settings

    return {name: field.default for name, field in Settings.model_fields.items()}


def _settings_getattr_calls(
    defaults: dict[str, object],
) -> list[tuple[str, int, str, object]]:
    out: list[tuple[str, int, str, object]] = []
    for rel, tree in _app_trees():
        for n in ast.walk(tree):
            if (
                not isinstance(n, ast.Call)
                or not isinstance(n.func, ast.Name)
                or n.func.id != "getattr"
                or len(n.args) < 3
            ):
                continue
            target, attr, default = n.args[:3]
            if not (isinstance(target, ast.Name) and target.id == "settings"):
                continue
            if not (
                isinstance(attr, ast.Constant)
                and isinstance(attr.value, str)
                and attr.value in defaults
            ):
                continue
            try:
                value: object = ast.literal_eval(default)
            except Exception:
                value = _UNRESOLVED
            out.append((rel, n.lineno, attr.value, value))
    return out


def _env_read_name(node: ast.AST) -> str | None:
    args: list[ast.expr] = []
    if isinstance(node, ast.Call):
        func = node.func
        is_getenv = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and func.attr == "getenv"
        ) or (isinstance(func, ast.Name) and func.id == "getenv")
        is_environ_get = (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
            and func.value.attr == "environ"
        )
        if not (is_getenv or is_environ_get):
            return None
        args = node.args
    elif isinstance(node, ast.Subscript):
        value = node.value
        if not (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "os"
            and value.attr == "environ"
        ):
            return None
        args = [node.slice]
    else:
        return None
    if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
        return args[0].value
    return None


def _env_reads() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for rel, tree in _app_trees():
        for n in ast.walk(tree):
            name = _env_read_name(n)
            if name:
                out.append((rel, n.lineno, name))
    return out


def _attr_lines(node: ast.AST, attr: str) -> list[int]:
    return sorted(
        n.lineno
        for n in ast.walk(node)
        if isinstance(n, ast.Attribute) and n.attr == attr
    )


def _env_lines(node: ast.AST, name: str) -> list[int]:
    return sorted(
        n.lineno for n in ast.walk(node) if _env_read_name(n) == name
    )


class TestFallbackDefaults:
    def test_no_getattr_fallback_diverges_from_settings_default(self):
        defaults = _settings_defaults()
        calls = _settings_getattr_calls(defaults)
        bad = [
            (rel, line, field, value)
            for rel, line, field, value in calls
            if value is _UNRESOLVED or value != defaults[field]
        ]
        assert bad == [], (
            "getattr(settings, ...) 的兜底默认值与 Settings 声明默认值不一致："
            f"{bad}。配置默认值只能有一个来源。"
        )

    def test_scanner_sees_known_fallback_sites(self):
        defaults = _settings_defaults()
        calls = _settings_getattr_calls(defaults)
        assert len(calls) >= 11, (
            f"扫描器可疑：只发现 {len(calls)} 处 getattr(settings, field, default)"
        )
        fields = {field for _, _, field, _ in calls}
        assert {"model_cache_maxsize", "ml_inference_cache_ttl"} <= fields

    def test_drift_sites_now_read_settings_directly(self):
        predict = _func(ast.parse(_read(PREDICT_REL)), "predict_structured")
        assert "structured_default_model" in [
            n.attr for n in ast.walk(predict) if isinstance(n, ast.Attribute)
        ], "predict_structured 不再直接读取 settings.structured_default_model"
        for n in ast.walk(predict):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "getattr"
                and len(n.args) >= 2
                and isinstance(n.args[1], ast.Constant)
                and n.args[1].value == "structured_default_model"
            ):
                raise AssertionError(
                    "predict_structured 又给 structured_default_model 加了兜底默认值"
                )

        roots = _func(ast.parse(_read(METRICS_REL)), "_model_roots")
        assert "model_dir" in [
            n.attr for n in ast.walk(roots) if isinstance(n, ast.Attribute)
        ], "_model_roots 不再直接读取 settings.model_dir"
        for n in ast.walk(roots):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "getattr"
                and len(n.args) >= 2
                and isinstance(n.args[1], ast.Constant)
                and n.args[1].value == "model_dir"
            ):
                raise AssertionError(
                    "_model_roots 又给 model_dir 加了兜底默认值"
                )

    def test_declared_defaults_pinned(self):
        defaults = _settings_defaults()
        assert defaults["structured_default_model"] == "v1.23"
        assert defaults["model_dir"] == "models"

    def test_config_declares_each_default_once(self):
        src = _read(CONFIG_REL)
        assert src.count('structured_default_model: str = "v1.23"') == 1
        assert src.count('model_dir: str = "models"') == 1


class TestEnvReadAllowlist:
    def test_same_name_env_reads_exactly_allowlisted(self):
        fields_upper = {name.upper() for name in _settings_defaults()}
        found = {
            (rel, name)
            for rel, _, name in _env_reads()
            if name in fields_upper
        }
        assert found == set(ALLOWLIST), (
            "与 Settings 字段同名的环境变量直读集合与允许清单不一致："
            f"实际 {sorted(found)}，允许 {sorted(ALLOWLIST)}。"
            "新增直读必须走 Settings，或在 ALLOWLIST 写明为何需要第二来源。"
        )

    def test_allowlist_entries_still_present(self):
        fields_upper = {name.upper() for name in _settings_defaults()}
        found = {
            (rel, name)
            for rel, _, name in _env_reads()
            if name in fields_upper
        }
        for entry in ALLOWLIST:
            assert entry in found, (
                f"允许项 {entry} 已不存在（过期豁免）——请从 ALLOWLIST 移除"
            )

    def test_allowlist_not_broadened(self):
        assert set(ALLOWLIST) == {
            (CACHE_REL, "REDIS_URL"),
            (DEDUP_REL, "REDIS_URL"),
            (SENTRY_REL, "SENTRY_DSN"),
        }, "ALLOWLIST 只允许这三处有意兜底"

    def test_allowlist_reasons_are_written(self):
        for entry, reason in ALLOWLIST.items():
            assert reason.strip(), f"允许项 {entry} 缺少理由"

    def test_env_scanner_covers_three_read_forms(self):
        snippet = (
            "import os\n"
            "os.getenv('A')\n"
            "os.environ.get('B')\n"
            "os.environ['C']\n"
        )
        found = {
            name
            for node in ast.walk(ast.parse(snippet))
            if (name := _env_read_name(node)) is not None
        }
        assert found == {"A", "B", "C"}, (
            f"环境变量扫描器漏读形态：{sorted(found)}"
        )

    def test_scanner_sees_known_env_reads(self):
        reads = _env_reads()
        names = {name for _, _, name in reads}
        assert {"REDIS_URL", "SENTRY_DSN", "WEB_CONCURRENCY"} <= names, (
            f"扫描器漏掉已知环境变量读取：{sorted(names)}"
        )
        assert len(reads) >= 15, f"扫描器可疑：只发现 {len(reads)} 处环境变量直读"

    def test_non_settings_env_names_not_flagged(self):
        fields_upper = {name.upper() for name in _settings_defaults()}
        flagged = {
            (rel, name)
            for rel, _, name in _env_reads()
            if name in fields_upper
        }
        assert "WEB_CONCURRENCY" not in fields_upper
        assert all(name != "WEB_CONCURRENCY" for _, name in flagged)


class TestAllowlistedFallbackSemantics:
    def test_redis_fallback_is_settings_first(self):
        for rel in (CACHE_REL, DEDUP_REL):
            fn = _func(ast.parse(_read(rel)), "_get_redis_url")
            settings_lines = _attr_lines(fn, "redis_url")
            env_lines = _env_lines(fn, "REDIS_URL")
            assert settings_lines, f"{rel} 的 _get_redis_url 不再读取 settings.redis_url"
            assert env_lines, f"{rel} 的 _get_redis_url 不再有 REDIS_URL 兜底"
            assert min(settings_lines) < min(env_lines), (
                f"{rel} 的 REDIS_URL 兜底排到了 settings.redis_url 之前"
            )

    def test_sentry_env_fallback_is_library_level_only(self):
        fn = _func(ast.parse(_read(SENTRY_REL)), "init_sentry")
        assert isinstance(fn, ast.FunctionDef)
        assert fn.args.args and fn.args.args[0].arg == "dsn"
        assert len(fn.args.defaults) == len(fn.args.args), (
            "init_sentry 的 dsn 不再是带默认值的位置参数"
        )
        assert ast.literal_eval(fn.args.defaults[0]) is None, (
            "init_sentry 的 dsn 默认值不再是 None（库级兜底前提变化）"
        )
        assert _env_lines(fn, "SENTRY_DSN"), "init_sentry 内 SENTRY_DSN 兜底消失"

    def test_main_passes_sentry_dsn_from_settings(self):
        fn = _func(ast.parse(_read(MAIN_REL)), "_init_sentry")
        calls = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "init_sentry"
        ]
        assert calls, "main._init_sentry 不再调用 init_sentry"
        keywords = {kw.arg: kw.value for kw in calls[0].keywords}
        dsn = keywords.get("dsn")
        assert (
            isinstance(dsn, ast.Attribute) and dsn.attr == "sentry_dsn"
        ), "main._init_sentry 不再透传 settings.sentry_dsn（库级 env 兜底会接管）"
