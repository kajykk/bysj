# 回归测试计划与结果 (Regression Tests)

> **事实来源 #2 (Source of Truth #2)**
> 本文件是回归测试的绝对真理，`AUDIT_STATE.md` 中的回归统计数字必须基于本文件计算。
> 每条 `submit-fix` 必须同步在本文件创建或更新对应回归用例（Iron Rule #11）。

---

## 📋 回归用例表 (Regression Test Cases)

| 用例编号 | 关联问题 | 类型 | 标题 | 优先级 | 前置条件 | 步骤数 | 状态 | 执行人 | 执行日期 | 结果 |
| :------- | :------- | :--- | :--- | :----- | :------- | -----: | :--- | :----- | :------- | :--- |
| REG-001 | ISS-001 | API | [用例标题] | P0 | [前置] | 3 | ⏳ 待执行 | — | — | — |

> **状态**: ⏳ 待执行 / 🔄 执行中 / ✅ 通过 / ❌ 失败 / ⛔ 阻塞
> **类型**: 单测 / API / 集成 / E2E / 性能 / 安全 / 手工

### 用例编号规则
- 前缀 `REG-` + 三位序号。
- 关联问题字段填写 `ISS-NNN`，便于双向追溯。

---

## 🔬 用例详情 (Test Case Details)

### REG-001: [用例标题]

```text
用例编号：REG-001
关联问题：ISS-001
用例类型：[单测/API/集成/E2E/性能/安全/手工]
优先级：[P0/P1/P2/P3]
标题：
前置条件：
  1.
  2.
测试步骤：
  1.
  2.
  3.
期望结果：
  1.
  2.
实际结果：
执行人：
执行日期：YYYY-MM-DD
状态：[⏳ 待执行/🔄 执行中/✅ 通过/❌ 失败/⛔ 阻塞]
失败原因（如失败）：
关联日志/request_id：
```

---

## 📊 统计汇总 (Statistics Summary)

> 本节由 `audit-beautify-orchestrator` 自动维护，禁止手动编辑。

| 指标 | 数值 |
| :--- | ---: |
| 用例总数 | 0 |
| 已通过 | 0 |
| 失败 | 0 |
| 阻塞 | 0 |
| 未执行 | 0 |
| 通过率 | 0% |

---

## 🎯 必跑回归矩阵 (Mandatory Regression Matrix)

> 以下矩阵覆盖计划"十二、完成判定"中的核心要求，**必须** 全部通过才能进入 Phase 6。

### 1. 角色权限与越权回归
| 用例编号 | 角色 | 操作 | 期望 | 状态 |
| :------- | :--- | :--- | :--- | :--- |
| REG-RP-01 | 未登录用户 | 访问 /api/v1/user/profile | 401 | ⏳ |
| REG-RP-02 | 普通用户 | 访问 /api/v1/admin/users | 403 | ⏳ |
| REG-RP-03 | 普通用户 | 访问 /api/v1/counselor/list | 403 | ⏳ |
| REG-RP-04 | 咨询师 | 访问 /api/v1/admin/users | 403 | ⏳ |
| REG-RP-05 | 咨询师 | 访问未授权用户详情 | 403 | ⏳ |
| REG-RP-06 | 管理员 | 越权修改高危危机事件 | 403 | ⏳ |
| REG-RP-07 | Token 过期 | 任意敏感操作 | 401 跳登录 | ⏳ |
| REG-RP-08 | 被禁用账号 | 登录 | 拒绝 + 明确提示 | ⏳ |

### 2. 核心业务链路回归
| 用例编号 | 链路 | 步骤 | 状态 |
| :------- | :--- | :--- | :--- |
| REG-CB-01 | 评估→风险→预警→处理 | 用户提交评估 → 后端计算风险 → 生成报告/预警 → 咨询师处理 | ⏳ |
| REG-CB-02 | 模板配置→内容更新 | 管理员配置模板 → 用户/咨询师可见内容更新 | ⏳ |
| REG-CB-03 | 告警→静默→生命周期 | 告警产生 → 静默规则匹配 → 告警生命周期更新 | ⏳ |
| REG-CB-04 | GDPR 导出/删除→审计 | GDPR 数据导出/删除 → 审计记录生成 | ⏳ |
| REG-CB-05 | 模型训练→状态→展示 | 模型训练任务 → 任务状态 → 结果展示 | ⏳ |

### 3. 基线命令回归
| 用例编号 | 命令 | 期望 | 状态 |
| :------- | :--- | :--- | :--- |
| REG-BL-01 | `cd frontend && npm run typecheck` | 0 errors | ⏳ |
| REG-BL-02 | `cd frontend && npm run lint` | 0 errors | ⏳ |
| REG-BL-03 | `cd frontend && npm run test` | all pass | ⏳ |
| REG-BL-04 | `cd frontend && npm run build` | success | ⏳ |
| REG-BL-05 | `cd backend && pytest` | all pass | ⏳ |
| REG-BL-06 | `cd backend && ruff check app tests` | no issues | ⏳ |
| REG-BL-07 | `cd backend && black --check app tests` | all formatted | ⏳ |
| REG-BL-08 | `cd backend && bandit -r app` | no high severity | ⏳ |

### 4. Lighthouse 性能回归
| 用例编号 | 页面 | 指标 | 阈值 | 状态 |
| :------- | :--- | :--- | :--- | :--- |
| REG-LH-01 | 登录页 | Performance | ≥ 80 | ⏳ |
| REG-LH-02 | 登录页 | Accessibility | ≥ 90 | ⏳ |
| REG-LH-03 | 用户 Dashboard | Performance | ≥ 80 | ⏳ |
| REG-LH-04 | 用户 Dashboard | Accessibility | ≥ 90 | ⏳ |
| REG-LH-05 | 管理 Dashboard | Performance | ≥ 80 | ⏳ |
| REG-LH-06 | 管理 Dashboard | Accessibility | ≥ 90 | ⏳ |
| REG-LH-07 | LCP (任意页面) | ≤ 2.5s | ⏳ |
| REG-LH-08 | INP (任意页面) | ≤ 200ms | ⏳ |
| REG-LH-09 | CLS (任意页面) | ≤ 0.1 | ⏳ |

### 5. 响应式回归矩阵
| 用例编号 | 设备 | 分辨率 | 关键页面 | 状态 |
| :------- | :--- | :----- | :------- | :--- |
| REG-RS-01 | iPhone SE | 375 × 667 | 登录 / Dashboard / 列表 | ⏳ |
| REG-RS-02 | iPhone 12/13 | 390 × 844 | 登录 / Dashboard / 列表 | ⏳ |
| REG-RS-03 | Android 常见 | 412 × 915 | 登录 / Dashboard / 列表 | ⏳ |
| REG-RS-04 | iPad Mini | 768 × 1024 | 登录 / Dashboard / 列表 / 详情 | ⏳ |
| REG-RS-05 | iPad Pro | 1024 × 1366 | 全页面 | ⏳ |
| REG-RS-06 | Laptop | 1366 × 768 | 全页面 | ⏳ |
| REG-RS-07 | Desktop | 1920 × 1080 | 全页面 | ⏳ |

### 6. 浏览器兼容性回归
| 用例编号 | 浏览器 | 关键页面 | 状态 |
| :------- | :--- | :------- | :--- |
| REG-BC-01 | Chrome 最新版 | 全页面 | ⏳ |
| REG-BC-02 | Edge 最新版 | 全页面 | ⏳ |
| REG-BC-03 | Firefox 最新版 | 全页面 | ⏳ |
| REG-BC-04 | Safari (如有) | 全页面 | ⏳ |

---

## 🛡️ 回归执行规则

1. **修复必带回归**: 任何 `submit-fix` 必须同步在本文件创建或更新对应回归用例（Iron Rule #11）。
2. **关闭前置**: `close-issue` 前必须确认本文件中关联回归用例状态为 `✅ 通过`（Iron Rule #6）。
3. **失败处理**: 回归失败时，原问题重新打开或创建关联问题。
4. **基线回归**: REG-BL-01 ~ REG-BL-08 必须在 Phase 5 完成时全部 `✅ 通过`。
5. **必跑矩阵**: 第 1-6 节所有用例必须在 Phase 6 验收前全部 `✅ 通过`。
