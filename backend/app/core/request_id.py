from __future__ import annotations

import logging
import re
from typing import Any
from uuid import uuid4

from fastapi import Request

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "x-request-id"

# M-Core-10 修复：校验客户端传入的 x-request-id 格式，防止 CRLF 注入
# 仅允许字母、数字、连字符，长度 8-128
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]{8,128}$")

# AUDIT-2026-10-05: Celery 侧传播用的 header 名。取独立名字而非复用
# REQUEST_ID_HEADER（那个是 HTTP header 语义），避免与 HTTP 链路混淆。
TASK_REQUEST_ID_HEADER = "x_dws_request_id"

# AUDIT-2026-10-05: bind/unbind 跟踪当前 worker 线程绑定的 request_id,
# 用于诊断"任务间 ID 泄漏"。tracing.set_current_request_id 不暴露 ContextVar
# token, 故只能记录值本身, 无法用 reset() 精确还原 —— 置None 是当前唯一可靠做法。
_task_request_id_token: Any = None


def get_or_create_request_id(request: Request) -> str:
    request_id = request.headers.get(REQUEST_ID_HEADER)
    if request_id:
        request_id = request_id.strip()
        # 格式不匹配则忽略并生成新的，避免 CRLF 注入
        if request_id and _REQUEST_ID_PATTERN.match(request_id):
            return request_id
    return str(uuid4())


def new_request_id() -> str:
    """生成格式合法的 request_id（非 HTTP 场景, 如 Celery 定时任务/无请求上下文）。"""
    return str(uuid4())


def bind_task_request_id(request_id: str | None) -> None:
    """把 request_id 绑定到当前 worker 线程的 ContextVar。

    背景 (AUDIT-2026-10-05): request_id 原先只由 HTTP 中间件
    ``set_current_request_id`` 设置, 且在 finally 中清空。而 Celery 任务运行
    在**独立 worker 进程/线程**, ContextVar 从未被设置 -> 任务内所有日志的
    req_id 都是 "-", 且risk_assessments 表无该列。

    对医疗心理健康系统这是合规审计缺口: 无法回答"某次风险评分由哪次请求产生"。
    本函数供 Celery ``task_prerun`` 信号调用, 把随任务带过来的 request_id
    恢复到 ContextVar, 使任务日志可与调用方关联。
    """
    global _task_request_id_token
    from app.core.tracing import set_current_request_id

    # tracing.set_current_request_id 返回 None (不暴露 ContextVar token),
    # 故这里只记录"已绑定"状态, 还原统一靠 unbind 置 None。
    set_current_request_id(request_id)
    _task_request_id_token = request_id
    if request_id:
        logger.debug("Celery request_id bound: %s", request_id)


def unbind_task_request_id() -> None:
    """还原 ContextVar, 避免 ID 泄漏给同一 worker 线程上的后续任务。"""
    global _task_request_id_token
    from app.core.tracing import set_current_request_id

    set_current_request_id(None)
    _task_request_id_token = None


def resolve_task_request_id(headers: dict | None) -> str:
    """从任务 headers 取出 request_id, 缺失或非法则新建一个。

    非法值的处理与 HTTP 链路一致（``get_or_create_request_id``）:
    宁可丢弃上游给的值另生成, 也不放行不合法字符串进入日志。
    """
    if not headers:
        return new_request_id()
    candidate = headers.get(TASK_REQUEST_ID_HEADER) or headers.get("request_id")
    if candidate:
        candidate = str(candidate).strip()
        if _REQUEST_ID_PATTERN.match(candidate):
            return candidate
        logger.warning(
            "Celery task 携带的 request_id 格式非法, 已重新生成 (原值长度=%d)",
            len(candidate),
        )
    return new_request_id()
