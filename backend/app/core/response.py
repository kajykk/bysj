from __future__ import annotations


def ok(data=None, message: str = "success", code: int = 200) -> dict:
    """STAB-P1-001: 统一成功响应体结构为 {code, message, data, error}.

    成功响应固定 ``error=None``，与错误响应 (``error`` 非 None, ``data=None``)
    保持结构对齐，前端可用同一套解析逻辑处理。
    """
    return {"code": code, "message": message, "data": data, "error": None}


def fail(
    message: str,
    *,
    code: int = 500,
    error: dict | str | None = None,
    data=None,
) -> dict:
    """STAB-P1-001: 统一错误响应体结构为 {code, message, data, error}.

    Args:
        message: 人类可读错误消息 (与成功响应的 message 字段对齐)
        code: HTTP 状态码 (与成功响应的 code 字段对齐)
        error: 结构化错误详情 (dict 或字符串), None 时使用 message 占位
        data: 失败响应固定 None, 保持字段对齐

    Returns:
        ``{"code": code, "message": message, "data": None, "error": error}``
    """
    if error is None:
        error = {"message": message}
    return {"code": code, "message": message, "data": data, "error": error}
