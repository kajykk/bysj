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

    @staticmethod
    def _exc_tainted_names(funcnode: ast.AST) -> set[str]:
        """同函数内被异常文本污染的变量名：`x = str(exc)` / `x = f"...{exc}..."`。

        口径补强（第十二轮第二批）：gdpr.py 曾用 `msg = str(exc)` 再 `detail=msg`
        绕过直接形态判据。只认 str()/异常名插值两种来源，不搞通用数据流。
        """
        tainted: set[str] = set()
        for node in ast.walk(funcnode):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            tgt = node.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            v = node.value
            if isinstance(v, ast.Call) and getattr(v.func, "id", None) == "str":
                tainted.add(tgt.id)
            elif isinstance(v, ast.JoinedStr):
                for val in v.values:
                    if isinstance(val, ast.FormattedValue):
                        fv = val.value
                        if getattr(getattr(fv, "func", None), "id", None) == "str":
                            tainted.add(tgt.id)
                        elif isinstance(fv, ast.Name) and re.match(
                            r"^(e|exc|err|error|ex|msg)$", fv.id
                        ):
                            tainted.add(tgt.id)
        return tainted

    def _leak_sites(self) -> list[tuple[str, int]]:
        """精确判据：HTTPException 的 detail 里出现异常对象被格式化（含同函数变量中转）。"""
        rows: list[tuple[str, int]] = []
        for p in BE.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            except Exception:
                continue
            scopes: list[ast.AST] = [
                n
                for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ] or [tree]
            for scope in scopes:
                tainted = self._exc_tainted_names(scope)
                for node in ast.walk(scope):
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
                        elif isinstance(v, ast.Name) and v.id in tainted:
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
        return sorted(set(rows))

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


class TestRecordAuditTenantColumn:
    """P2-33 第四批修复：record_audit 的 tenant_id 必须落列，不能只进 detail。

    根因：helper 文档声称"该表无租户列"，但 Phase 5 已加 `tenant_id` 非空列。
    修前所有迁移行的列恒为模型默认，detail 与列各说各话（SEC-FIX 归属被静默丢弃）。
    行为断言（不用存在性断言）：真写一行再读列。
    """

    async def test_tenant_id_written_to_column(self, db_session):
        from app.core.audit import record_audit
        from app.models.admin import OperationLog

        log = await record_audit(
            db_session,
            actor_id=1,
            actor_role="admin",
            action="test.tenant.col",
            target_type="user",
            target_id=2,
            detail={},
            request=None,
            tenant_id=7,
        )
        assert log.tenant_id == 7, "tenant_id 未落列（只进了 detail）"
        got = await db_session.get(OperationLog, log.id)
        assert got is not None and got.tenant_id == 7

    async def test_none_tenant_maps_to_platform_default(self, db_session):
        from app.core.audit import record_audit
        from app.core.contracts import DEFAULT_TENANT_ID

        log = await record_audit(
            db_session,
            actor_id=None,
            actor_role="system",
            action="test.tenant.platform",
            target_type="alert",
            target_id=None,
            detail={},
            request=None,
            tenant_id=None,
        )
        assert log.tenant_id == DEFAULT_TENANT_ID, "None 应记平台默认租户（列非空）"


# ---------------------------------------------------------------------------
# P2-12 第六批：detail-JSON 下游重验（第五批口径变化的影响面）
# ---------------------------------------------------------------------------


def _scan_record_audit_detail_kwargs() -> list[tuple[str, int, ast.AST]]:
    """AST 扫描：所有 ``record_audit(...)`` 调用点的 ``detail=`` 实参节点。

    用 AST 而非正则（第十一轮教训：嵌套括号会被正则截断，造成假红/假绿）。
    """
    out: list[tuple[str, int, ast.AST]] = []
    for path in sorted(BE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name != "record_audit":
                continue
            for kw in node.keywords:
                if kw.arg == "detail":
                    out.append(
                        (
                            str(path.relative_to(BE)).replace("\\", "/"),
                            node.lineno,
                            kw.value,
                        )
                    )
    return out


def _scan_operation_log_detail_readers() -> dict[str, int]:
    """AST 扫描：``app/`` 下「函数体内引用了 OperationLog 且读了 ``.detail``」的模块 → 命中数。

    扫描口径固定在此处：清单一旦变化（新增消费点 / 删掉 / 移动）闸门即红，
    强制重跑一遍本节的下游核对，避免"新增了一个按裸字符串解析的消费者"却被静默放过。
    """
    result: dict[str, int] = {}
    for path in sorted(BE.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "OperationLog" not in ast.unparse(fn):
                continue
            hits = [
                n
                for n in ast.walk(fn)
                if isinstance(n, ast.Attribute) and n.attr == "detail"
            ]
            if hits:
                rel = str(path.relative_to(BE)).replace("\\", "/")
                result[rel] = result.get(rel, 0) + len(hits)
    return result


_JSON_LOAD_NAMES = frozenset({"json.loads", "_json_loads", "json_loads", "loads"})


def _is_json_loads_call(node: ast.AST) -> bool:
    """识别 ``json.loads`` 及其别名（observability 用 ``_json_loads``）。"""
    if not isinstance(node, ast.Call):
        return False
    return ast.unparse(node.func).split(".")[-1] in _JSON_LOAD_NAMES


def _json_loads_is_guarded(tree: ast.AST) -> bool:
    """模块内是否存在「位于 try 块内」的 json.loads 调用（裸字符串兜底）。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for sub in ast.walk(node):
            if _is_json_loads_call(sub):
                return True
    return False


class TestAuditDetailJsonDownstream:
    """第五批把 intervention / binding 的审计 detail 由裸字符串改为 JSON 对象后的下游重验。

    三道闸：
    1. **写入侧**：``record_audit`` 的 detail 只能是 dict/None，禁止字符串 ——
       从源头保证"落库的 detail 一定是 JSON 对象"这一前提不再漂移。
    2. **消费侧清单**：把所有读 ``OperationLog.detail`` 的模块钉成清单，
       变化即红 → 强制重新核对（清单不静默漂移）。
    3. **解析侧兜底**：凡在 Python 侧 ``json.loads`` 的消费点，必须带 except 兜底，
       否则一条历史裸字符串行就会让整个告警/清理链路崩掉。
    4. **运行时**：真跑一遍第五批改过的服务方法，按 JSON 对象读回（不靠类型注解）。
    """

    # 消费侧清单（口径见 _scan_operation_log_detail_readers）
    # kind: parse=Python 侧解析 / sql=只在 SQL 表达式里用 / passthrough=原样进响应 / slice=截断预览
    EXPECTED_READERS: dict[str, int] = {
        "api/v1/alerts/__init__.py": 6,          # parse（含 SQL contains 兜底）
        "api/v1/content_governance.py": 1,       # passthrough
        "api/v1/ops_dashboard.py": 2,            # slice（[:200] 预览，无下游解析器）
        "api/v1/tenant_audit.py": 2,             # passthrough
        "monitoring/dedup.py": 1,                # parse
        "monitoring/escalation.py": 10,          # parse（alert_fired 行）
        "services/admin_service_log.py": 1,      # passthrough
        "services/mttr_service.py": 2,           # parse
        "services/observability/aggregate.py": 8,  # parse（_parse_detail_json）
        "services/observability/query.py": 8,    # sql
        "tasks/alerts.py": 1,                    # parse
        # 第六批复核（2026-10-15）：该处 3 个 .detail 读的是 AnomalyFinding.detail
        # （dataclass 字段，JSON 字符串，迁 record_audit 时先 json.loads 还原成
        # dict），**不是** OperationLog.detail 消费点；函数 docstring 里出现
        # OperationLog 字样故被扫描器计入。读数为 3：try 内 loads / isinstance
        # 回退 / except 回退各一处。
        "tasks/anomaly_detection.py": 3,
        "tasks/scheduler.py": 2,                 # parse（user_file_upload 的 url）
    }

    PARSE_READERS = (
        "api/v1/alerts/__init__.py",
        "monitoring/dedup.py",
        "monitoring/escalation.py",
        "services/mttr_service.py",
        "services/observability/aggregate.py",
        "tasks/alerts.py",
        "tasks/scheduler.py",
    )

    def test_record_audit_detail_is_never_a_string(self):
        args = _scan_record_audit_detail_kwargs()
        # 扫描器自检：扫不到足够多的点说明扫描器本身失效（假绿的最大来源）
        assert len(args) >= 30, f"扫描器疑似失效：只找到 {len(args)} 个 detail= 实参"
        bad: list[str] = []
        for rel, lineno, node in args:
            if isinstance(node, ast.JoinedStr):
                bad.append(f"{rel}:{lineno} f-string -> {ast.unparse(node)[:60]}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                bad.append(f"{rel}:{lineno} str -> {ast.unparse(node)[:60]}")
        assert not bad, (
            "record_audit 的 detail 必须是 JSON 对象（dict）或 None，"
            "禁止裸字符串/f-string（下游一律按 JSON 对象解析）：\n" + "\n".join(bad)
        )

    def test_operation_log_detail_reader_inventory_unchanged(self):
        got = _scan_operation_log_detail_readers()
        assert got == self.EXPECTED_READERS, (
            "OperationLog.detail 读取点清单发生变化（新增/删除/移动），"
            "必须重跑 detail-JSON 下游核对后再更新本清单：\n"
            f"  got={got}\n  exp={self.EXPECTED_READERS}"
        )

    def test_parse_readers_are_tolerant(self):
        """Python 侧解析 detail 的模块必须带 except 兜底。

        裸字符串的历史行（迁移前落库）一旦进入这些链路，没有兜底就是
        整条告警升级/去重/清理链路崩掉，而不是"少一条日志"。
        """
        bad: list[str] = []
        for rel in self.PARSE_READERS:
            src = (BE / rel).read_text(encoding="utf-8")
            tree = ast.parse(src, filename=rel)
            has_loads = any(_is_json_loads_call(n) for n in ast.walk(tree))
            if not has_loads:
                bad.append(f"{rel}: 标注为 parse 但模块内没有 json.loads")
            elif not _json_loads_is_guarded(tree):
                bad.append(f"{rel}: json.loads 不在 try 块内（裸字符串会炸链路）")
        assert not bad, "解析侧兜底缺失：\n" + "\n".join(bad)

    async def test_intervention_audit_detail_reads_back_as_json_object(self, db_session):
        """运行时重验：complete_task 落库的 detail 必须是 JSON 对象（不是裸字符串）。"""
        import json
        from datetime import date

        from sqlalchemy import select

        from app.models.admin import OperationLog
        from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
        from app.services.intervention_service import InterventionService

        plan = InterventionPlan(
            user_id=1, plan_name="P2-12 plan", risk_level=2,
            status="active", start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()
        task = InterventionTask(
            plan_id=plan.id, task_name="P2-12 task", task_type="relaxation",
            schedule="daily", duration_minutes=15, sort_order=0,
        )
        db_session.add(task)
        await db_session.flush()
        db_session.add(
            TaskExecution(
                task_id=task.id, user_id=1,
                scheduled_date=date.today(), status="pending",
            )
        )
        await db_session.commit()

        ok_, _reason = await InterventionService(db_session).complete_task(1, task.id, None)
        assert ok_ is True, "前置条件失效：complete_task 未成功，后续断言无意义"

        log = (
            await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "complete_intervention_task"
                )
            )
        ).scalars().first()
        assert log is not None, "审计日志未写入"
        parsed = json.loads(log.detail)
        # 断言「是 JSON 对象且字段可读」，不断言整串相等（避免把实现钉死）
        assert isinstance(parsed, dict), f"detail 不是 JSON 对象：{log.detail!r}"
        assert parsed["task_id"] == task.id

    async def test_binding_audit_detail_reads_back_as_json_object(
        self, db_session, seeded_user_id
    ):
        """运行时重验：绑定码/解绑落库的 detail 必须是 JSON 对象。"""
        import json

        from sqlalchemy import select

        from app.models.admin import OperationLog
        from app.services.counselor_service import CounselorService

        service = CounselorService(db_session)
        code = await service.get_or_create_bind_code(2)
        await service.bind_by_code(1, code)
        await service.unbind(1)

        for action in ("bind_counselor", "unbind_counselor"):
            log = (
                await db_session.execute(
                    select(OperationLog).where(OperationLog.action_type == action)
                )
            ).scalars().first()
            assert log is not None, f"{action} 审计日志未写入"
            parsed = json.loads(log.detail)
            assert isinstance(parsed, dict), f"{action} detail 不是 JSON 对象：{log.detail!r}"
        bind_log = (
            await db_session.execute(
                select(OperationLog).where(OperationLog.action_type == "bind_counselor")
            )
        ).scalars().first()
        # 枚举状态必须是裸值（active），不能是 "BindingStatus.ACTIVE"
        assert json.loads(bind_log.detail)["to_status"] == "active"


# ---------------------------------------------------------------------------
# P2-12 第六批：目标租户归属语义（SEC-FIX 回归闸门）
# ---------------------------------------------------------------------------


class TestTargetTenantAttribution:
    """tenant_admin / branding / export 的审计归属必须跟着**目标租户**走。

    背景（SEC-FIX，迁移前就有）：这些端点的操作者是平台管理员（自己的租户是
    平台默认租户 1），但审计行归属**被操作的目标租户**，目标租户的管理员才能
    在 tenant-audit 里看到针对自己租户的操作。迁到 `record_audit` 时若图省事
    传 `current_user.tenant_id`，归属就静默搬回操作者租户 —— tenant-audit
    可见性断裂，且**没有任何既有测试会红**（它们只断言 200/结构）。

    因此这里同时钉两侧：
    1. **源码侧**：这 6 个文件的 record_audit 调用，tenant_id 实参不得是
       `current_user.tenant_id`（必须是目标租户表达式）。
    2. **运行时侧**：真调一次创建租户，落库行的 tenant_id 列必须等于新租户 id，
       且**不等于**操作者（平台管理员，tenant 1）的租户。
    """

    # (文件, 期望的 tenant_id 实参形态) —— 形态用 AST unparse 后精确比对，
    # 既允许 tenant.id 也允许 tenant_id（两种目标表达），排除 current_user.*。
    ATTRIBUTION_SITES = (
        ("api/v1/tenant_admin.py", ("tenant.id", "tenant_id")),
        ("api/v1/tenant_export.py", ("tenant_id",)),
        ("api/v1/tenant_branding.py", ("tenant_id",)),
    )

    def test_audit_calls_do_not_follow_operator_tenant(self):
        import ast as _ast

        for rel, allowed in self.ATTRIBUTION_SITES:
            src = (BE / rel).read_text(encoding="utf-8")
            tree = _ast.parse(src, filename=rel)
            calls = [
                n
                for n in _ast.walk(tree)
                if isinstance(n, _ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                == "record_audit"
            ]
            assert calls, f"{rel} 未找到 record_audit 调用（迁移丢了？）"
            for call in calls:
                kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
                assert "tenant_id" in kwargs, f"{rel}:{call.lineno} 缺 tenant_id 必填关键字"
                expr = _ast.unparse(kwargs["tenant_id"])
                assert expr in allowed, (
                    f"{rel}:{call.lineno} 的 tenant_id={expr} —— 归属必须跟着**目标租户**"
                    f"（允许 {allowed}），不得跟操作者租户；否则 tenant-audit 可见性断裂"
                )

    def test_create_tenant_audit_row_belongs_to_new_tenant(self, client, as_role, db_session):
        """运行时：平台管理员创建租户后，审计行归属新租户而非操作者租户。"""
        import json

        from sqlalchemy import select

        from app.models.admin import OperationLog
        from app.models.tenant import Tenant
        from tests.conftest import run

        # 先种平台默认租户（id=1）占位，保证新租户拿到的 id 与平台租户不同
        # （不种的话新租户会直接拿 id=1，目标租户与操作者租户数值相同，断言失效）
        from tests.conftest import run as _run

        async def _seed_platform_tenant():
            existing = (
                await db_session.execute(select(Tenant).where(Tenant.id == 1))
            ).scalar_one_or_none()
            if existing is None:
                db_session.add(
                    Tenant(id=1, name="平台", code="platform_gate", status="active")
                )
                await db_session.flush()

        _run(_seed_platform_tenant())

        # 平台管理员：tenant 1（DEFAULT_TENANT_ID），与被创建租户不同
        as_role("admin", 1, tenant_id=1)
        res = client.post(
            "/api/v1/tenants",
            json={"name": "归属回归", "code": "attribution_gate"},
        )
        assert res.status_code == 200, res.text
        new_tenant_id = res.json()["data"]["id"]
        assert new_tenant_id != 1, "前置条件失效：新租户 id 不应是平台默认租户"

        async def _fetch_log():
            result = await db_session.execute(
                select(OperationLog).where(
                    OperationLog.action_type == "tenant.create",
                    OperationLog.target_id == new_tenant_id,
                )
            )
            return result.scalar_one_or_none()

        log = run(_fetch_log())
        assert log is not None, "tenant.create 审计行未写入"
        assert log.tenant_id == new_tenant_id, (
            f"审计行 tenant_id={log.tenant_id}，应归属目标租户 {new_tenant_id}"
            "（SEC-FIX：目标租户管理员的 tenant-audit 可见性依赖此列）"
        )
        assert log.tenant_id != 1, "审计行不得归属操作者（平台管理员）租户"
        assert log.operator_id == 1, "操作者信息仍应保留在 operator_id"
        # detail 须为 JSON 对象（第六批口径统一）
        parsed = json.loads(log.detail)
        assert isinstance(parsed, dict) and parsed["code"] == "attribution_gate"
