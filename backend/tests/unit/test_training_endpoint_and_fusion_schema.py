"""P0-FIX-2026-10-11: 训练任务端点权限收紧 + FusionPredictRequest 补入参约束。

背景（来自 2026-10-11 全量源码审查，报告条目 10）：

1. ``GET /predict/training/jobs`` 与 ``GET /predict/training/jobs/{job_id}``
   用的权限是 ``user.predict.use`` —— 那是**普通学生**权限（与 ``/predict/*``
   同级）。但训练任务属后台运维域：兄弟端点 ``POST /predict/experiment/train``
   本身就要求 ``admin.predict.audit``。
   后果：任何登录用户都能列出全平台训练任务（数据集名、训练参数、模型指标），
   且 ``get_training_job(job_id)`` 是典型 IDOR —— 凭一个 job_id 读到不属于自己的
   任务详情，且跨租户。

2. ``TextPredictRequest.text`` 有 ``max_length=5000``，但
   ``FusionPredictRequest.text`` **完全无约束**，而 ``predict_fusion`` 直接透传；
   ``features`` / ``physiological`` 也无键数上限，与同文件
   ``StructuredPredictRequest`` 的 50 键上限不一致 —— 同一份特征表在不同端点
   校验结果不同。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.model_predict import status as status_module
from app.schemas.model_predict import FusionPredictRequest


class TestTrainingJobEndpointsRequireAdmin:
    def _dep_of(self, func):
        """取出端点签名里 ``Depends(...)`` 实际引用的依赖对象。

        必须用 ``get_type_hints(..., include_extras=True)``：模块里有
        ``from __future__ import annotations``，注解是字符串，直接读
        ``param.annotation`` 拿不到 Annotated 元数据（会静默返回 None，
        让本测试变成永远绿的假闸门）。
        """
        import typing

        hints = typing.get_type_hints(func, include_extras=True)
        for annotation in hints.values():
            for meta in getattr(annotation, "__metadata__", ()) or ():
                if meta.__class__.__name__ == "Depends":
                    return meta.dependency
        return None

    @staticmethod
    def _required_permission(dep):
        """从 require_*_permission 生成的闭包里取出权限字符串。

        注意 ``require_platform_permission("x")`` 返回的是内部 ``checker``
        闭包，**不是**工厂函数本身，所以不能拿函数对象做 identity 比较 ——
        那种写法要么恒假、要么被迫放宽成"随便什么依赖都行"，等于没断言。
        """
        for cell in getattr(dep, "__closure__", None) or ():
            value = cell.cell_contents
            if isinstance(value, str):
                return value
        return None

    def test_list_training_jobs_requires_platform_admin(self):
        dep = self._dep_of(status_module.list_training_jobs)
        assert dep is not None, "未解析出依赖对象 —— 解析方式失效，本测试形同虚设"
        assert dep is not status_module.require_permission, (
            "训练任务列表仍走普通 require_permission（学生级）"
        )
        assert self._required_permission(dep) == "admin.predict.audit", (
            "训练任务列表的权限键不是 admin.predict.audit"
        )

    def test_get_training_job_requires_platform_admin(self):
        dep = self._dep_of(status_module.get_training_job)
        assert dep is not None, "未解析出依赖对象"
        assert dep is not status_module.require_permission, "按 id 读训练任务仍是 IDOR"
        assert self._required_permission(dep) == "admin.predict.audit"


class TestFusionPredictRequestConstraints:
    def test_text_has_max_length(self):
        long_text = "x" * 5001
        with pytest.raises(ValidationError):
            FusionPredictRequest(text=long_text)

    def test_text_at_limit_is_accepted(self):
        assert FusionPredictRequest(text="x" * 5000).text is not None

    def test_text_optional_still_optional(self):
        assert FusionPredictRequest().text is None

    def test_features_max_50_keys(self):
        ok_payload = {f"f{i}": 1 for i in range(50)}
        assert FusionPredictRequest(features=ok_payload).features is not None
        with pytest.raises(ValidationError):
            FusionPredictRequest(features={f"f{i}": 1 for i in range(51)})

    def test_physiological_max_50_keys(self):
        assert FusionPredictRequest(
            physiological={f"f{i}": 1 for i in range(50)}
        ).physiological is not None
        with pytest.raises(ValidationError):
            FusionPredictRequest(physiological={f"f{i}": 1 for i in range(51)})

    def test_none_dicts_are_allowed(self):
        """None 表示"该模态缺失"，不能被当成空字典去查键数。"""
        FusionPredictRequest(features=None, physiological=None)

    def test_matches_text_predict_request_limit(self):
        """与 TextPredictRequest 保持同一上限，避免两处漂移。"""
        from app.schemas.model_predict import TextPredictRequest

        text_limit = TextPredictRequest.model_fields["text"].metadata
        fusion_limit = FusionPredictRequest.model_fields["text"].metadata
        assert type(text_limit) is type(fusion_limit)
        assert max(m for m in text_limit if hasattr(m, "max_length")).max_length == 5000