# 测试计划 — v1.17-review-workflow-text-model-upgrade

> **生成时间**: 2026-05-01
> **基于文档**: 01-requirements.md, 02-architecture.md, 03-design.md
> **测试框架**: pytest (Unit) + FastAPI TestClient (Integration)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 上线环境验证测试 (Baseline Validation)

### 1.1 前端构建

- [ ] `[TC-BASE-001]` 运行 `npm run build` 成功，无错误 (P0)
- [ ] `[TC-BASE-002]` 构建输出目录包含预期文件 (P0)

### 1.2 后端启动

- [ ] `[TC-BASE-003]` 后端服务正常启动 (P0)
- [ ] `[TC-BASE-004]` 数据库连接正常 (P0)
- [ ] `[TC-BASE-005]` 模型加载正常，无报错 (P0)

### 1.3 健康检查

- [ ] `[TC-BASE-006]` GET `/health` 返回 200 (P0)
- [ ] `[TC-BASE-007]` GET `/health/ready` 返回 200 (P0)

### 1.4 API 冒烟测试

- [ ] `[TC-BASE-008]` POST `/model/predict/text` 正常文本返回 200 (P0)
- [ ] `[TC-BASE-009]` POST `/model/predict/text` 危机文本返回 crisis_detected=true (P0)
- [ ] `[TC-BASE-010]` POST `/model/predict/fusion` 正常请求返回 200 (P0)
- [ ] `[TC-BASE-011]` POST `/model/predict/fusion` 危机请求返回 crisis_override=true (P0)

---

## 2. Review Service 单元测试

### 2.1 创建复核任务

**Happy Path (HP):**
- [ ] `[TC-REVIEW-HP-001]` 根据预测结果创建复核任务，状态为 pending (P0)
- [ ] `[TC-REVIEW-HP-002]` crisis_override=true 时创建 crisis_review 优先级任务 (P0)
- [ ] `[TC-REVIEW-HP-003]` 单模型 high 时创建 high_risk_review 优先级任务 (P0)

**Edge Cases (EC):**
- [ ] `[TC-REVIEW-EC-001]` 重复创建复核任务时更新现有任务 (P1)
- [ ] `[TC-REVIEW-EC-002]` 空预测结果不创建任务 (P1)

### 2.2 状态流转

**Happy Path (HP):**
- [ ] `[TC-REVIEW-HP-004]` pending -> assign -> in_review (P0)
- [ ] `[TC-REVIEW-HP-005]` in_review -> resolve -> resolved (P0)
- [ ] `[TC-REVIEW-HP-006]` in_review -> escalate -> escalated (P0)

**Sad Path (SP):**
- [ ] `[TC-REVIEW-SP-001]` resolved 任务不可再次 resolve (P0)
- [ ] `[TC-REVIEW-SP-002]` pending 任务不可直接 resolve (必须先 assign) (P0)

### 2.3 查询筛选

**Happy Path (HP):**
- [ ] `[TC-REVIEW-HP-007]` 按状态筛选返回正确结果 (P0)
- [ ] `[TC-REVIEW-HP-008]` 按优先级筛选返回正确结果 (P0)
- [ ] `[TC-REVIEW-HP-009]` 分页返回正确数量 (P0)

---

## 3. Review API 集成测试

### 3.1 权限控制

**Happy Path (HP):**
- [ ] `[TC-API-REVIEW-HP-001]` 咨询师可查看分配的复核任务 (P0)
- [ ] `[TC-API-REVIEW-HP-002]` 咨询师可处理分配的复核任务 (P0)
- [ ] `[TC-API-REVIEW-HP-003]` 管理员可查看全部复核任务 (P0)

**Sad Path (SP):**
- [ ] `[TC-API-REVIEW-SP-001]` 普通用户不可查看复核任务列表 (P0)
- [ ] `[TC-API-REVIEW-SP-002]` 咨询师不可查看未分配的复核任务 (P0)
- [ ] `[TC-API-REVIEW-SP-003]` 未登录用户返回 401 (P0)

### 3.2 端到端流程

- [ ] `[TC-API-REVIEW-E2E-001]` 预测 -> 创建复核任务 -> 咨询师查看 -> 咨询师处理 (P0)
- [ ] `[TC-API-REVIEW-E2E-002]` 预测 -> 创建复核任务 -> 升级危机事件 (P0)

---

## 4. Crisis Event 测试

### 4.1 记录危机事件

**Happy Path (HP):**
- [ ] `[TC-CRISIS-HP-001]` 检测到危机时自动记录危机事件 (P0)
- [ ] `[TC-CRISIS-HP-002]` 记录的危机事件包含正确关键词 (P0)
- [ ] `[TC-CRISIS-HP-003]` 记录的危机事件关联正确的 review_task_id (P0)

### 4.2 查询和导出

**Happy Path (HP):**
- [ ] `[TC-CRISIS-HP-004]` 管理员可查询危机事件列表 (P0)
- [ ] `[TC-CRISIS-HP-005]` 按时间范围筛选返回正确结果 (P0)
- [ ] `[TC-CRISIS-HP-006]` 导出危机事件为 CSV (P1)

**Sad Path (SP):**
- [ ] `[TC-CRISIS-SP-001]` 普通用户不可查询危机事件 (P0)
- [ ] `[TC-CRISIS-SP-002]` 咨询师不可导出危机事件 (P0)

---

## 5. 前端组件测试

### 5.1 复核列表页

- [ ] `[TC-FE-REVIEW-001]` 页面加载显示复核任务列表 (P0)
- [ ] `[TC-FE-REVIEW-002]` 状态筛选正常工作 (P0)
- [ ] `[TC-FE-REVIEW-003]` 优先级筛选正常工作 (P0)
- [ ] `[TC-FE-REVIEW-004]` 分页正常工作 (P0)

### 5.2 复核详情页

- [ ] `[TC-FE-REVIEW-005]` 显示用户信息和模型预测结果 (P0)
- [ ] `[TC-FE-REVIEW-006]` 显示风险因素和保护因素 (P0)
- [ ] `[TC-FE-REVIEW-007]` 标记已处理按钮正常工作 (P0)
- [ ] `[TC-FE-REVIEW-008]` 升级危机事件按钮正常工作 (P0)
- [ ] `[TC-FE-REVIEW-009]` 危机任务红色高亮显示 (P0)

---

## 6. 文本安全增强测试

### 6.1 关键词扩展

**Happy Path (HP):**
- [ ] `[TC-TEXT-V17-HP-001]` "emo到不想活" 触发危机检测 (P0)
- [ ] `[TC-TEXT-V17-HP-002]` "破防到想死" 触发危机检测 (P0)
- [ ] `[TC-TEXT-V17-HP-003]` "已经准备好了" 触发计划性表达 (P0)
- [ ] `[TC-TEXT-V17-HP-004]` "救救我" 触发求助表达 (P0)

**Edge Cases (EC):**
- [ ] `[TC-TEXT-V17-EC-001]` "笑死了" 不触发危机检测 (P0)
- [ ] `[TC-TEXT-V17-EC-002]` "气死了" 不触发危机检测 (P0)
- [ ] `[TC-TEXT-V17-EC-003]` "社死了" 不触发危机检测 (P0)

---

## 7. 回归测试

### 7.1 v1.16 核心能力

- [ ] `[TC-REG-V16-001]` 危机检测模块正常工作 (P0)
- [ ] `[TC-REG-V16-002]` 阈值校准正常工作 (P0)
- [ ] `[TC-REG-V16-003]` 融合优先级规则正常工作 (P0)
- [ ] `[TC-REG-V16-004]` 预期风险样本测试通过 (P0)
- [ ] `[TC-REG-V16-005]` 前端风险展示正常 (P0)
- [ ] `[TC-REG-V16-006]` 危机预警弹窗正常 (P0)

---

## 测试统计

| 类别 | 总数 | P0 | P1 |
| :--- | :--- | :--- | :--- |
| 上线环境验证 | 11 | 11 | 0 |
| Review Service | 11 | 9 | 2 |
| Review API | 8 | 8 | 0 |
| Crisis Event | 7 | 6 | 1 |
| 前端组件 | 9 | 9 | 0 |
| 文本安全增强 | 7 | 7 | 0 |
| 回归测试 | 6 | 6 | 0 |
| **总计** | **59** | **56** | **3** |

---

> **文档版本**: v1.0
> **生成时间**: 2026-05-01
> **迭代**: v1.17-review-workflow-text-model-upgrade
