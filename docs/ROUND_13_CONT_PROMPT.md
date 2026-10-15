# P2 第十三轮续作提示词（#35 X 桶剩余簇 + prettier 决议收口）

> 状态：第十三轮已推进至**第十一批**（`3e5969d`→`478d1cc`，CI 每次全绿，
> `total_count=10`）。本提示词用于从**第十二批**起继续，直至本轮所有未决项收口。
>
> 起点快照（`478d1cc`）：棘轮 **W=70 / P=15 / X=145**（总数 334）。
> 已接 #35 实记录 42 处 + 探针 1 处；实记录 X 余 **145**（待接约 110 + 已裁定跳过
> 35，跳过分布在 P2_11 附录各「第十三轮第 X 批」条）。prettier 决议仍挂起
> （P2_13 §二）。tenant_admin / #33 / #34 / #36 / #32 均已关闭。

## 一、本轮剩余范围（按价值排序，做完一条再下一条）

1. **#35 X 桶剩余簇**：继续分批接线（每批 2–6 处，真降级定义不变：
   fallback / 部分数据 / fire-and-forget 丢失 / 假数据 / 静默安全网失效）。
   建议优先级（均为尚未裁定簇，先 `grep` 审计文档确认再动手）：
   - `core/model_engine/predict.py`（5）：`_run_experimental_v123` /
     `_run_adapter` / `_apply_lite_calibration`×2 / `_run_experimental_v121`
     —— 实验/对照路径算分退化，疑似与第二批已接的 scaler fallback 同族，
     **务必先追调用链**区分是否已有 `_incr_model_fallback` 计数。
   - `monitoring/escalation.py`（3）：升级计算失败 → 告警升级静默丢失。
   - `core/idempotency.py`（3）/ `core/safe_pickle.py`（3）：幂等/反序列化安全
     路径，注意 fail-closed 与 fail-open 语义（参考第十一批 file_security）。
   - `services/validation_engine.py`（3）：验证指标计算/推理/基线失败。
   - 其余 1–2 处小簇（`model_registry_v2`、`model_engine/inference`、
     `pii_crypto`、`rate_limit` 等）。
   每批：存在性→行为双断言；新位置登记进 P2_11 附录（棘轮 `>=` 式）；
   桶计数逐处改钉。
2. **prettier 决议收口**（P2_13 §二）：第十一轮起已记账两次，本轮必须终局——
   要么执行，要么给出**新的**书面理由/条件并明确"不再第三次原样记账"。
3. **P2_13 §三累计状态**：每批收口后同步更新（结账口径，历史快照不回改）。

## 二、铁律（全部继承，第十三轮第 7–11 批新增如下）

- **挑簇前置动作**：取新簇前先 `git grep` 审计文档（P2_11 附录 + P2_13 各
  「一之X」节）确认该文件是否**已裁定**——第四批已把 `scheduler.py` 判为
  空簇，第十一批前若不查会白接一轮（见本轮"空簇"教训）。
- **patch 命名空间三态**（每批先想清楚打哪一层）：
  1. from-import 的函数 → patch **使用方**命名空间（第七批 `ld.resolve_model_path`）；
  2. 包 `__init__` 同名 from-import 会**遮蔽子模块**——`import pkg.sub as x`
     可能拿到实例而非模块，须 `importlib.import_module`（第九批
     `app.services.auto_rollback_service`）；
  3. 函数体内做局部 `from ... import f` → patch **定义方**模块属性。
- **测试环境不得改变被测语义**：async 测试内直接调"无事件循环"分支会**成功建
  task**，须丢进 `asyncio.to_thread`（第十批）；驱动含前置守卫的内部方法需逐道
  满足（第七批 `_load_model` 的 MODEL_PATHS/`is_model_enabled`/`_abs_path`/缓存锁）。
- **全称注释词表**：`必然|恒为|恒[A-Z]|永远|不会|保证|一定|所有.+都会|仅当|只[有会]`。
  新注释命中即棘轮红；按 #38 纪律**改写注释逐词避开整张表**（"恒回/仅留/停摆"
  等），不要靠加数（第十批踩坑）。
- **探针接线口径**：把 `ImportError` **探针记录本身**接线会使其 `wired=True` →
  从 P 桶移入 W 桶（第十一批首见）；这类**桶间迁移**必须在 P2_11 附录 +
  P2_13 §三双侧逐条记账，并解释"总数 334 不变、无候选丢失/新增"。
- **变异纪律**：先审强度（子串逃逸式弱变异直接作废）→ 用**整块/整行删除**或
  **整串改名（含闭合引号，防子串逃逸）** → 期望红测试逐个点名 → 还原后必须全绿。
- **CI push 重试**：本机网络对 github 偶发不可达，`git push` 失败时按
  ~50→100→120s 退避重试，勿改 git 配置。

## 三、收工标准（每批）

- 接线 + 双向闸门（存在性 + 运行时覆盖）+ 桶计数改钉 + `scan/classify` 产物复跑刷新。
- 三处同步：P2_11 附录条目 / P2_13「一之X」节 / §三累计状态。
- 三次真实变异 RED-OK/GREEN-OK，落盘 `mutate_p2_35_round13_batchN_result.log`。
- 实测读数落盘：P2 六闸门（`test_p2_09/10/11/12/31/32`）+ affected 全跑；
  后端全量本地未跑则**如实记账**、由 CI 兜底。
- 独立提交；push；CI 全绿（报 `total_count` 实数）。提交信息按既有
  `fix(backend): P2-13第N批：…` 风格，含"未验证如实记账"小节。

## 四、本轮总收工（所有批次完成后）

- prettier 决议终局 + §三累计状态定稿 + P2_13 补「第十三轮收口」小节。
- 独立提交 + push + CI 全绿。
