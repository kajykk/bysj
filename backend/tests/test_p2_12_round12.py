"""P2 第十二轮闸门：#34 统一错误方言 + 末道脱敏 + #33/#35/#36 余量收敛。

反假闸门设计（沿用前几轮教训）：
- **异常断言一律带 `match=`**（第九轮 E33：断言异常类型 ≠ 断言异常来源）。
- **脱敏测试是"前后对照"**（内部信息进、通用文案出），不是"断言中间件存在"。
- **`to_dict()` 不出 internal_detail** 是硬约束，用"塞入可识别内部信息 → 断言响应体
  不含该信息"的方式测，而不是断言字段不存在（后者挡不住将来改名）。
- **作用域闸门**（`TestScopeResolution`）：本轮所有新增引用都必须过名字解析检查
  （第十一轮 `py_compile` 事故的直接对策），`py_compile` 通过不算验证。
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO = pathlib.Path(__file__).resolve().parents[2]
BE = REPO / "backend/app"
DOCS = REPO / "docs"

AUDIT = DOCS / "P2_12_ROUND12_AUDIT.md"
REGISTRY = DOCS / "RETENTION_REGISTRY.md"


def _build_app() -> FastAPI:
    from app.main import app

    return app


class TestServiceErrorContract:
    """#34 基础设施：ServiceError 的两条硬约束。"""

    def test_client_message_is_the_only_egress_field(self):
        from app.core.exceptions import ServiceError

        err = ServiceError(
            "操作失败",
            internal_detail="psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint",
            tenant_id=7,
        )
        body = err.to_dict()
        # 硬约束：internal_detail 不得出现在响应体的任何位置
        assert "psycopg2" not in str(body), "internal_detail 泄漏进响应体"
        assert "duplicate key" not in str(body), "internal_detail 泄漏进响应体"
        assert body["error"]["message"] == "操作失败"
        assert body["message"] == "操作失败"

    def test_missing_tenant_id_raises_typeerror_with_message(self):
        # E33 教训：必须 match 消息特征，否则 json.dumps(sentinel) 抛的 TypeError 会让测试恒绿
        from app.core.exceptions import ServiceError

        with pytest.raises(TypeError, match="tenant_id"):
            ServiceError("x")

    def test_none_tenant_id_is_explicit_platform_op(self):
        from app.core.exceptions import ServiceError

        err = ServiceError("x", tenant_id=None)
        payload = err.log_payload(has_request=True)
        assert "tenant_id" not in payload, "None 表示平台级操作，不得写 tenant_id 键"

    def test_log_payload_shape_matches_record_audit(self):
        """与 record_audit 的 detail 格式对齐：tenant_id / no_request，不自创字段。"""
        from app.core.audit import record_audit
        from app.core.exceptions import ServiceError
        import inspect

        sig = inspect.signature(record_audit)
        assert "tenant_id" in sig.parameters, "record_audit 的 tenant_id 契约变了？"
        assert "request" in sig.parameters

        err = ServiceError("x", internal_detail={"k": "v"}, tenant_id=3)
        p = err.log_payload(has_request=False)
        assert p["tenant_id"] == 3
        assert p["no_request"] is True
        assert p["k"] == "v"

    def test_handler_logs_internal_detail_not_response(self, caplog):
        """脱敏前后对照：内部信息进日志、通用文案出响应。"""
        import logging

        from app.core.exceptions import ServiceError

        app = FastAPI()
        from app.core.exceptions import install_exception_handlers

        install_exception_handlers(app)

        sentinel = "psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint \"users_email_key\""

        @app.get("/boom")
        async def _boom():
            raise ServiceError(
                "创建用户失败",
                internal_detail=sentinel,
                status_code=409,
                tenant_id=7,
            )

        client = TestClient(app, raise_server_exceptions=False)
        with caplog.at_level(logging.ERROR):
            res = client.get("/boom")
        assert res.status_code == 409
        # 出网侧：只有通用文案
        assert "创建用户失败" in res.json()["error"]["message"]
        assert "psycopg2" not in res.text
        assert "users_email_key" not in res.text
        # 落盘侧：内部信息必须可追溯
        assert sentinel in caplog.text, "internal_detail 未进日志（失去可追溯性）"


class TestLastDitchSanitizer:
    """末道脱敏中间件：确定性特征清单 + 前后对照。"""

    def test_scrub_replaces_internal_info_with_generic_message(self):
        from app.core.middlewares import _scrub_error_body

        body = (
            b'{"code":500,"message":"\\u5904\\u7406\\u5931\\u8d25",'
            b'"error":{"code":"INTERNAL","message":'
            b'"psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint \\"users_email_key\\""}}'
        )
        new_body, scrubbed = _scrub_error_body(body)
        assert scrubbed is True
        assert b"psycopg2" not in new_body
        assert b"users_email_key" not in new_body
        assert "请求处理失败".encode("utf-8") in new_body

    def test_scrub_catches_psycopg_detail_alone(self):
        """只含 psycopg 单一特征的 body 必须被脱敏。

        这条用例专门让"删掉 psycopg 特征"的变异可检出：若 body 里同时含
        `duplicate key value violates`，删掉前者仍会被后者命中，变异就太弱了。
        """
        from app.core.middlewares import _scrub_error_body

        body = (
            b'{"code":500,"message":"x","error":{"code":"INTERNAL",'
            b'"message":"psycopg2.OperationalError: connection refused"}}'
        )
        new_body, scrubbed = _scrub_error_body(body)
        assert scrubbed is True
        assert b"psycopg2" not in new_body

    def test_scrub_leaves_legitimate_client_messages_alone(self):
        """正当的用户可读文案不得被误伤（启发式判据会误伤，故用确定性清单）。"""
        from app.core.middlewares import _scrub_error_body

        legit = (
            '{"code":400,"message":"Path traversal detected: \'..\' is not allowed in dataset_path.",'
            '"error":{"code":"VALIDATION","message":"\\u8def\\u5f84\\u4e0d\\u5408\\u6cd5"}}'
        ).encode("utf-8")
        new_body, scrubbed = _scrub_error_body(legit)
        assert scrubbed is False, "正当安全提示被误伤"
        assert new_body == legit

    def test_scrub_ignores_short_strings(self):
        """长度下限：短文本一律不判敏感（防误伤 + 省 CPU）。

        这条用例专门盯住 `_looks_sensitive` 里的 `len(value) < 8` 下限：
        没有它，"去掉长度下限"的变异将无人检出（F4 首轮即因此假绿）。
        """
        from app.core.middlewares import _looks_sensitive

        assert _looks_sensitive("404") is False
        assert _looks_sensitive("不存在") is False
        assert _looks_sensitive(None) is False
        assert _looks_sensitive(12345) is False
        # 关键：**短且含特征**的文本必须因长度下限而被放过。
        # 少了这条，"放宽长度下限"的变异无人检出（F4 首轮假绿的根因）。
        assert _looks_sensitive("psycopg") is False

    def test_scrub_ignores_success_bodies_and_non_json(self):
        from app.core.middlewares import _scrub_error_body

        # 非 JSON：原样放行，不猜不抛
        raw = b"<html>500 Internal Server Error</html>"
        assert _scrub_error_body(raw) == (raw, False)
        # 顶层非 dict：原样放行
        arr = b'["psycopg2.errors.UniqueViolation"]'
        assert _scrub_error_body(arr) == (arr, False)

    def test_middleware_end_to_end_scrubs_unhandled_exception(self):
        """端到端：忘改的 HTTPException(detail=str(exc)) 也被末道闸门拦住。"""
        import asyncio

        from starlette.responses import JSONResponse

        from app.core.middlewares import error_sanitizer_middleware

        async def call_next(_request):
            # 模拟"绕过统一方言"的写法：异常原文直接进 detail
            return JSONResponse(
                status_code=500,
                content={
                    "code": 500,
                    "message": "服务器内部错误",
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": 'Traceback (most recent call last): File "/home/app/main.py", line 1',
                    },
                },
            )

        class _Req:
            url = type("U", (), {"path": "/api/v1/x"})()
            state = type("S", (), {"request_id": "test-req"})

        resp = asyncio.run(error_sanitizer_middleware(_Req(), call_next))
        assert resp.status_code == 500
        assert b"Traceback" not in resp.body
        assert b"/home/app" not in resp.body
        assert "请求处理失败".encode("utf-8") in resp.body


class TestP234LeakConvergence:
    """#34 全量：泄漏类清零 + 正当明文登记。"""

    def _leak_sites(self) -> list[tuple[str, int]]:
        """精确判据：HTTPException 的 detail 里出现异常对象被格式化。"""
        rows: list[tuple[str, int]] = []
        for p in BE.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except Exception:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                    continue
                fn = node.exc.func
                nm = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if nm != "HTTPException":
                    continue
                for kw in node.exc.keywords:
                    if kw.arg != "detail":
                        continue
                    v = kw.value
                    hit = False
                    if isinstance(v, ast.Call) and getattr(v.func, "id", None) == "str":
                        hit = True
                    elif isinstance(v, ast.JoinedStr):
                        for val in v.values:
                            if isinstance(val, ast.FormattedValue):
                                fv = val.value
                                if getattr(getattr(fv, "func", None), "id", None) == "str":
                                    hit = True
                                elif isinstance(fv, ast.Name) and re.match(
                                    r"^(e|exc|err|error|ex)$", fv.id
                                ):
                                    hit = True
                    if hit:
                        rows.append((p.relative_to(BE.parent).as_posix(), node.lineno))
        return rows

    def test_no_exception_text_in_http_exception_detail(self):
        got = self._leak_sites()
        assert not got, "仍有 HTTPException detail 直接带异常原文:\n" + "\n".join(
            f"{f}:{l}" for f, l in got
        )

    def test_service_error_is_used_in_review_template(self):
        t = (BE / "api/v1/review.py").read_text(encoding="utf-8")
        assert t.count("raise ServiceError(") >= 6, "样板间六处应已迁 ServiceError"
        assert "detail=str(e)" not in t

    def test_migrated_call_sites_pass_tenant_id(self):
        """每处 ServiceError 调用都必须显式传 tenant_id（必填关键字，漏传 TypeError）。"""
        missing: list[str] = []
        for p in BE.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            src = p.read_text(encoding="utf-8")
            for m in re.finditer(r"raise ServiceError\(", src):
                seg = src[m.start() : m.start() + 400]
                # 截到右括号配平
                depth = 0
                end = 0
                for i, ch in enumerate(seg):
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                call = seg[:end]
                if "tenant_id=" not in call:
                    missing.append(f"{p.relative_to(BE.parent).as_posix()}:{src[:m.start()].count(chr(10))+1}")
        assert not missing, "ServiceError 调用缺 tenant_id:\n" + "\n".join(missing)

    def test_legit_plaintext_registered_in_retention_registry(self):
        """正当明文 detail 必须登记（RES-P2-034-xx），不许散落在注释里。"""
        t = REGISTRY.read_text(encoding="utf-8")
        assert "RES-P2-034" in t, "#34 的正当明文保留决议未登记"
        assert AUDIT.exists(), "审计文档缺失"


class TestScopeResolution:
    """作用域闸门：本轮所有新增引用都必须过名字解析（py_compile 不算验证）。

    范式来自第十一轮 `TestModuleLevelNamesDefined`（fusion.py 缺 logger 事故）。
    本轮覆盖 #34/#33/#35/#36 改动过的文件。
    """

    TARGETS = [
        "core/exceptions.py",
        "core/middlewares.py",
        "core/metrics.py",
        "main.py",
        "api/v1/review.py",
        # #34 全量收敛改过的文件（auth.py 的 register/refresh 无 current_user，
        # 曾因批量脚本统一写 current_user.tenant_id 触发 NameError —— 正是本闸门的用途）
        "api/v1/auth.py",
        "api/v1/admin.py",
        "api/v1/canary.py",
        "api/v1/counselor.py",
        "api/v1/user_data.py",
        "api/v1/model_predict/experiment.py",
        "api/v1/model_predict/registry.py",
    ]

    @staticmethod
    def _scope_names(node: ast.AST) -> set[str]:
        names: set[str] = set()

        def add_target(t_: ast.AST) -> None:
            for n in ast.walk(t_):
                if isinstance(n, ast.Name):
                    names.add(n.id)

        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda, ast.ClassDef)):
            raw = getattr(node, "body", [])
            body = list(raw) if isinstance(raw, list) else []
            if isinstance(node, ast.Lambda):
                body = []
            for stmt in body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(stmt.name)
                elif isinstance(stmt, ast.Assign):
                    for t_ in stmt.targets:
                        add_target(t_)
                elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                    add_target(stmt.target)
                elif isinstance(stmt, (ast.For, ast.AsyncFor)):
                    add_target(stmt.target)
                elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                    for item in stmt.items:
                        if item.optional_vars is not None:
                            add_target(item.optional_vars)
                elif isinstance(stmt, ast.Import):
                    for a in stmt.names:
                        names.add(a.asname or a.name.split(".")[0])
                elif isinstance(stmt, ast.ImportFrom):
                    for a in stmt.names:
                        if a.name != "*":
                            names.add(a.asname or a.name)
                elif isinstance(stmt, ast.ExceptHandler) and stmt.name:
                    names.add(stmt.name)
                elif isinstance(stmt, (ast.Global, ast.Nonlocal)):
                    names.update(stmt.names)
                for sub in ast.walk(stmt):
                    if sub is stmt:
                        continue
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                        ast.Lambda)):
                        continue
                    if isinstance(sub, (ast.Global, ast.Nonlocal)):
                        names.update(sub.names)
                    elif isinstance(sub, ast.ExceptHandler):
                        if sub.name:
                            names.add(sub.name)
                    elif isinstance(sub, (ast.For, ast.AsyncFor)):
                        add_target(sub.target)
                    elif isinstance(sub, (ast.With, ast.AsyncWith)):
                        for item in sub.items:
                            if item.optional_vars is not None:
                                add_target(item.optional_vars)
                    elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
                        add_target(sub.target)
                    elif isinstance(sub, ast.Assign):
                        for t_ in sub.targets:
                            add_target(t_)

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            a = node.args
            for arg in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
                        + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else [])):
                names.add(arg.arg)
        for sub in ast.walk(node):
            if isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                for gen in sub.generators:
                    for n in ast.walk(gen.target):
                        if isinstance(n, ast.Name):
                            names.add(n.id)
        if not isinstance(node, ast.Module):
            lo = getattr(node, "lineno", 0)
            hi = getattr(node, "end_lineno", 0)
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)) and lo <= getattr(sub, "lineno", 0) <= hi:
                    if isinstance(sub, ast.Import):
                        for a in sub.names:
                            names.add(a.asname or a.name.split(".")[0])
                    else:
                        for a in sub.names:
                            if a.name != "*":
                                names.add(a.asname or a.name)
        return names

    def test_used_names_are_defined_or_imported(self):
        import builtins as _b

        bad: list[str] = []
        for rel in self.TARGETS:
            src = (BE / rel).read_text(encoding="utf-8")
            tree = ast.parse(src, filename=rel)
            scopes = [(tree, self._scope_names(tree))]
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    scopes.append((node, self._scope_names(node)))

            def parents(node: ast.AST) -> list[set[str]]:
                chain: list[set[str]] = []
                for scope_node, names in scopes:
                    if scope_node is node:
                        continue
                    if isinstance(scope_node, ast.Module):
                        chain.append(names)
                        continue
                    if (getattr(node, "lineno", 0) >= getattr(scope_node, "lineno", 0)
                            and getattr(node, "end_lineno", 0) <= getattr(scope_node, "end_lineno", 0)):
                        chain.append(names)
                return chain

            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if node.id in self._scope_names(tree):
                        continue
                    if any(node.id in names for names in parents(node)):
                        continue
                    if node.id in dir(_b) or node.id in {"__file__", "__name__", "__path__"}:
                        continue
                    bad.append(f"{rel}:{node.lineno} {node.id}")
        assert not bad, "引用了未定义/未导入的名字:\n" + "\n".join(sorted(set(bad))[:20])
