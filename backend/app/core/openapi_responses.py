from app.schemas.common import ErrorResponse

ERROR_RESPONSE_SCHEMA = {
    "description": "统一错误响应",
    "content": {
        "application/json": {
            "schema": ErrorResponse.model_json_schema()
        }
    },
}

COMMON_ERROR_RESPONSES = {
    400: {**ERROR_RESPONSE_SCHEMA, "description": "业务处理失败"},
    401: {**ERROR_RESPONSE_SCHEMA, "description": "未认证"},
    403: {**ERROR_RESPONSE_SCHEMA, "description": "权限不足"},
    404: {**ERROR_RESPONSE_SCHEMA, "description": "资源不存在"},
    409: {**ERROR_RESPONSE_SCHEMA, "description": "状态冲突"},
    422: {**ERROR_RESPONSE_SCHEMA, "description": "参数校验失败"},
    500: {**ERROR_RESPONSE_SCHEMA, "description": "服务内部错误"},
}

AUTH_ERROR_RESPONSES = {
    401: COMMON_ERROR_RESPONSES[401],
    403: COMMON_ERROR_RESPONSES[403],
}
