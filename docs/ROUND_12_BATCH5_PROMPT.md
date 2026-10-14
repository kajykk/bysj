# P2 第十二轮第五批提示词（#36 收尾 + #33 服务层 + #35 批量）

> 状态：第四批 `e55aaa3` CI 10/10 全绿。#33 余 34（服务层/任务层/`tenant_admin` 目标归属语义）；
> #35 余量；#36 9/12（余 `AdminAlerts`/`CounselorReviewList`/`UserAssessments`，均已有 STATE，
> 只差竞态守卫）；#32 维持只裁定不合并。

## 一、本批范围（只做以下，超出一律记账不顺手做）

1. **#36 最后 3 页**：`AdminAlertsPage`（tab 双数据源 history/archive + filters）、
   `CounselorReviewListPage`（510 行，对话框多，先读全再动手）、`UserAssessmentsPage`。
   沿用既定形状：`fetcher` 闭包组装参数（含 tab/筛选）→ `onSuccess` 写附属块 →
   `setPage` 写 URL query → `immediate:false` + 原 `onMounted` 保留 →
   对外名零改动。每页一个迁移钉（含先发后到竞态用例 + 一次真实变异红）。
2. **#33 第六批（服务层）**：沿 `warning_service` 打样——方法加
   `*, request: Request | None = None, tenant_id: int | None = None`，
   API 端点加 `Request` 并传入 `request + current_user.tenant_id`；
   任务/旧测试不传（None/平台默认），**既有单测必须零改动全绿**。
   候选簇（一次一批）：`review_service` 2 → `intervention_service` 2 →
   `counselor_service_*` 6。`tenant_admin` 4 处**不动**（目标租户归属语义，
   record_audit 落列后需逐点确认归属再迁，本批只记账）。
3. **#35 批量**：每次 3–4 处真降级（fallback/部分数据/ fire-and-forget 丢失），
   ImportError 探测、`Sentry capture_*` 自身失败、`指标上报失败` 一律跳过；
   新位置登记进 `P2_11` 附录（棘轮是 `>=` 式，不用改数）。

## 二、铁律（沿用，违反直接回滚重做）

- 先 import 烟测，再跑闸门；`py_compile` 通过不算验证（第十一轮事故）。
- 同套件**禁止并发双跑**（sqlite 争用卡死；kill 后单跑 8s 过）。
- 计数/名单/文档三处同步（#38 范式）；历史快照只追加不改。
- 结构断言 pin 行为不 pin 实现名；迁移后旧名断言恒假必须同步放宽。
- 每个新闸门一次真实变异（红 → 恢复绿），落盘记录。
- 正则扫调用一律用 AST（嵌套括号截断假红已有两例）。
- `tenant_id=None` 只允许平台/系统语义并注释；服务层可选关键字是唯一例外，
  调用方必须能说出每个 None 的归属去向。

## 三、收工标准

- `test_p2_11` 棘轮数更新 + `test_p2_12` 全绿 + affected 单跑全绿（落盘记数）。
- 前端迁移钉全绿 + `vue-tsc` 0 错 + 前端全量跑通（偶发红按红线查，不直接判抖动）。
- 审计文档补一节（含实测读数 + 未验证记账）；独立提交；push；CI 全绿（报
  `total_count` 实数，不报"10/10"固定数）。
