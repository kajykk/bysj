from __future__ import annotations


def ok(data=None, message: str = "success", code: int = 200) -> dict:
    return {"code": code, "message": message, "data": data}
