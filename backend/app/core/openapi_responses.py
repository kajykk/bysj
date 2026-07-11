# PERF/SCHEMA: 使用 $ref 引用 FastAPI 自动注册的 components/schemas/ErrorResponse,
# 而非 ErrorResponse.model_json_schema() (会内联 $defs/ErrorDetail, OpenAPI 3.0 不识别).
ERROR_RESPONSE_SCHEMA = {
    "description": "统一错误响应",
    "content": {
        "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
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

# 文件下载端点 200 响应: OpenAPI 文档化 application/pdf content-type,
# 避免 schemathesis contract 测试 UndefinedContentType 误报
PDF_SUCCESS_RESPONSE = {
    200: {
        "description": "PDF 文件",
        "content": {"application/pdf": {}},
    },
}

# 导出端点 200 响应: 支持 json/csv/pdf 多种格式
FILE_EXPORT_RESPONSE = {
    200: {
        "description": "导出数据 (JSON/CSV/PDF)",
        "content": {
            "application/json": {},
            "application/pdf": {},
            "text/csv": {},
        },
    },
}
