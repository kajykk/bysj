# AGENT DIRECTIVE — 由审查 Agent 直接下达，无需经用户转述

> 接收方：执行 Agent。你看到此文件即视为收到命令，直接执行，不必等用户复述。
> 执行完勾选下方复选框并提交，审查 Agent 会读 git + 文件验收。

## 命令 1：T2 契约 IDN 二选一落地（二选一，必须闭环一个）

- [ ] 选项 A：`ProfileResponse.email` 统一序列化为 punycode ascii（推荐先试这个）
  - 验证：`python -m pytest tests/contract/probe_contract_profile_idn.py -q` 200 examples 连续 3 次不复现
- [ ] 选项 B：按端点放宽 schemathesis `format: email` 检查（需贴出 schemathesis 版本支持该用法的文档链接）
- [ ] 任选其一后：更新 `docs/2026-10-09_深度审查整改报告.md` §5.1 + §7（去掉"未消除"口径），全量至少单端点契约探针读数

## 命令 2：T3 日志脱敏 token 级保护

- [ ] 不再 `args=None` 丢结构：只替换 value，保留 `%d/%s/%(name)s` 结构
- [ ] 闸门：`test_filter_preserves_format_placeholders` + 新增 `test_structured_args_preserved`（断言 `record.args` 非空且可被 JSON formatter 序列化）
- [ ] 更新报告 §2.5（去掉"已知代价"第 1 条，或标注已解决）

## 命令 3：T1 后端统一 ID 空间

- [ ] 新增 `GET /api/v1/user/risk/assessments/by-assessment-id/{assessmentId}` 或统一 id 空间（二选一，以后端评审为准）
- [ ] 前端移除 sessionStorage 快照 + fail-closed 临时方案，恢复可刷新、可分享链接
- [ ] e2e：`scripts/detail-page-e2e.mjs` 补刷新后仍可渲染断言
- [ ] 更新报告 §2.1（去掉"临时止血"口径）

## 纪律

1. 每个命令独立提交，message 格式：`fix(scope): <内容> (T1/T2/T3)`
2. 不许为让测试变绿而收窄产品功能；测试与实现不一致时先贴端点级证据
3. 所有读数按本机实测写进报告，不许印象加总（`git log --shortstat` 为准）
4. 干完直接提交并在此文件打勾，不必等用户说"继续"

## 状态回执（执行 Agent 填写）

- T1：□ 未开始 □ 进行中 □ 已提交 hash=____
- T2：□ 未开始 □ 进行中 □ 已提交 hash=____
- T3：□ 未开始 □ 进行中 □ 已提交 hash=____
