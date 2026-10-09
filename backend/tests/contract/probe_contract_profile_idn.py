"""IDN 邮箱契约 flaky 的复现探针（schemathesis，单端点）— 2026-10-09 入库。

背景
----
``tests/contract/test_api_contract.py::test_api_contract[PUT /api/v1/auth/profile]``
是低频 flaky：本地全量三轮里只在第三轮出现过一次。整份契约测试本地跑不完
（900s 只到 36%），且**不能用 node id 精确跑** —— schemathesis 的
``@schema.parametrize()`` 动态生成 id，会报 ``no match in any of
[<Module test_api_contract.py>]``。本探针用 ``schema.include(method="PUT")``
把范围收到单个端点，从而在十几秒内拿到真实断言。

为什么放在 tests/contract/ 而不是 scripts/
--------------------------------------------
本探针需要 ``tests/conftest.py`` 的环境初始化（建表 + 测试库 ``test_app.db``）。
实测放到 ``backend/scripts/`` 下因缺少该初始化而无法在合理时间内跑完
（300s 超时；app 会去连非测试库），证据脚本跑不动就等于没有证据。

已定性的根因（**不是** schema 声明不全，也**不是**限流/密文问题）
------------------------------------------------------------------
schemathesis 输出的可复现命令与实际响应::

    请求:  {"email": "h@fcqr6axccp.liti0ydoe2-dg.xn--3bst00m"}   <- punycode
    响应:  {"email":"h@fcqr6axccp.liti0ydoe2-dg.集团"}            <- 规范化成 unicode IDN
    -> Response violates schema (ApiResponse_ProfileResponse_/properties/data)

Pydantic ``EmailStr``（email-validator）接受 punycode 并规范化成 unicode，
而 jsonschema 的 ``format: email`` 基于 RFC 5322、不接受 unicode 域名 ⇒ 判不合规。
只有 hypothesis 恰好生成 punycode 域名时才触发，故为低频 flaky。

排除项（均已查证）：与 2026-10-09 那批改动无关（openapi.json / ProfileResponse /
UpdateProfileRequest 当日均未改动）；不是密文泄漏（``user.email`` 是
``EncryptedString`` 透明加密，读出即明文）；不是 415 或 429（两者都在
``expected_statuses`` 放行列表内）；端点返回字段与 ``ProfileResponse`` 一致。

处置（2026-10-09 定夺）
------------------------
**短期接受 flaky 并记录在案**，不为让测试变绿而在请求侧禁用 IDN ——
那等于为测试收窄产品功能。长期 ticket 见
``docs/2026-10-09_深度审查整改报告.md`` 第 5.1 节。

用法
----
从 ``backend/`` 目录执行（文件名不匹配 ``test_*.py``，不会被
``pytest tests/contract/`` 自动收集，需显式指定）::

    .venv/Scripts/python.exe -m pytest tests/contract/probe_contract_profile_idn.py -q

``max_examples=10`` 不复现；``200``（当前默认）约 13 秒复现。
"""

from __future__ import annotations

from pathlib import Path

import schemathesis
from hypothesis import settings
from schemathesis.config import SchemathesisConfig
from schemathesis.config._checks import (
    ChecksConfig,
    NotAServerErrorConfig,
    PositiveDataAcceptanceConfig,
)
from schemathesis.config._generation import GenerationConfig
from schemathesis.config._projects import ProjectConfig, ProjectsConfig
from schemathesis.generation import GenerationMode

from app.main import app

OPENAPI_PATH = Path(__file__).parent / "openapi.json"

_positive = PositiveDataAcceptanceConfig(
    expected_statuses=["2xx", "400", "401", "403", "404", "409", "415", "422", "429", "5xx"]
)
_checks = ChecksConfig(
    positive_data_acceptance=_positive,
    not_a_server_error=NotAServerErrorConfig(
        expected_statuses=["2xx", "3xx", "4xx", "5xx"]
    ),
)
_gen = GenerationConfig(modes=[GenerationMode.POSITIVE])
_cfg = SchemathesisConfig(
    projects=ProjectsConfig(default=ProjectConfig(checks=_checks, generation=_gen))
)

schema = schemathesis.openapi.from_path(str(OPENAPI_PATH), config=_cfg)
schema.app = app
target = schema.include(path="/api/v1/auth/profile", method="PUT")


@target.parametrize()
@settings(max_examples=200, deadline=None)
def test_profile_contract(case):
    """见模块 docstring：复现 IDN 邮箱导致的 schema 不符。"""
    response = case.call()
    case.validate_response(response)
