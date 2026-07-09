# 前端美化问题清单 (Visual Beautification Issues)

> **事实来源 #3 (Source of Truth #3)**
> 本文件是 UI/UX/视觉/响应式/可访问性问题的绝对真理。
> 审查依据：`uploads/计划.md` 第六、七、九节。
> 审查日期：2026-07-05

---

## 📋 视觉一致性问题（VIS）

### P1 高优先级（10 项）

| 编号 | 分类 | 文件#行号 | 问题 | 修复建议 |
|------|------|-----------|------|----------|
| VIS-P1-01 | 色彩 | variables.scss L42-46 / theme.scss L4-6 | 设计令牌命名分裂：--bg-color vs --bg-primary 两套并存 | 统一为单一命名空间，废弃旧命名 |
| VIS-P1-02 | 间距 | variables.scss L48-56 | 间距令牌不符合规范（--spacing-md=12px，计划要求 --space-md=16px） | 重命名为 --space-* 并调整数值至 4/8/16/24/32px |
| VIS-P1-03 | 圆角 | variables.scss L58-63, BentoCell.vue L84 | 圆角令牌缺失（仅 4/8/12px），BentoCell 硬编码 20px | 新增 --radius-sm=6px / --radius-md=10px / --radius-lg=16px |
| VIS-P1-04 | 响应式 | variables.scss L156-157, useBreakpoint.ts L6-13 | 断点令牌严重不足：SCSS 2 档 vs useBreakpoint 6 档，数值与计划不匹配 | 统一为 768/1024/1366/1920 四档断点 |
| VIS-P1-05 | 色彩 | ErrorPage.vue L127-149, L168-208 | 完全脱离设计系统：硬编码 6 种颜色 + 硬编码中文 + 无深色模式 | 全面迁移到 CSS 变量 + i18n + 深色模式适配 |
| VIS-P1-06 | 色彩 | SkipLink.vue L1-25 | 硬编码 #409eff + 硬编码中文"跳转到主内容" | 改用 var(--primary-color) + i18n |
| VIS-P1-07 | 色彩 | StatefulContainer.vue L41,46,55 / EmptyState.vue L62,91,98 | 硬编码 #dcdfe6/padding/font-size + 硬编码中文 | 迁移到 CSS 变量 + i18n |
| VIS-P1-08 | 色彩 | FilterBar.vue L11,15,30 | 硬编码中文"查询/重置" + margin-bottom: 12px 硬编码 | i18n 化 + 使用 --space-md |
| VIS-P1-09 | 色彩 | PageTable.vue L148, L135 | 行高亮硬编码 #ecf5ff + margin-top: 12px | 改用 var(--primary-light) + --space-md |
| VIS-P1-10 | 视觉 | UserSettingsPage/AdminSettingsPage/UserRiskPage/UserContentPage | BentoCell 与 el-card 视觉双轨并存（圆角/阴影/间距不一致） | 统一为 BentoCell 或新建 FormCard 组件 |

### P2 中优先级（12 项）

| 编号 | 分类 | 文件#行号 | 问题 | 修复建议 |
|------|------|-----------|------|----------|
| VIS-P2-01 | 图表 | RiskTrendChart.vue L66,69,96,99,112,115 | 图表色板硬编码 #3b82c4/#d65a5a/#5a9e3a | 抽到 chartPalette.ts + CSS 变量 |
| VIS-P2-02 | 图表 | UserDashboard.vue L637-645 | ECharts tooltip HTML 内联样式硬编码颜色 | 改用 CSS 变量或 isDark 切换 |
| VIS-P2-03 | 色彩 | AdminCrisisEventsPage.vue L466-471 | getScoreColor 硬编码 #999/#d65a5a/#d4923a/#5a9e3a | 复用 riskFormatters.ts 的 getRiskScoreColor |
| VIS-P2-04 | 图表 | CounselorUsersPage.vue L231 | 图表色板硬编码 7 色未抽到统一色板 | 抽到 chartPalette.ts |
| VIS-P2-05 | 色彩 | CounselorReviewDetailPage.vue L245-248 | getScoreColor 硬编码且阈值与 AdminCrisisEvents 不一致 | 统一复用 getRiskScoreColor |
| VIS-P2-06 | 色彩 | AdminSettingsPage.vue L1009,1013,1020 | 使用未定义的 --color-success/--color-danger 变量 | 改为 var(--success-color)/var(--danger-color) |
| VIS-P2-07 | 色彩 | AuthBrandPanel.vue L70,83-122,157,200,248,266 | 硬编码 7+ 颜色 + 硬编码中文默认值 | 抽到 --auth-brand-* 变量 + i18n |
| VIS-P2-08 | 表单 | 多处 | label-width 数值混乱（80/90/100/120/160px 5 种值） | 统一为 120px 或抽 formLabelWidth 常量 |
| VIS-P2-09 | 弹窗 | AdminCrisisEventsPage L244,302,345 / UserRiskPage L219 | 所有 el-dialog width="500px" 移动端溢出 | 改为 :width="isMobile ? '90vw' : '500px'" |
| VIS-P2-10 | 间距 | BentoCell.vue L84,85,116,117,127,133,143,173 | padding/gap 硬编码 rem 值 | 改用 --space-* 令牌 |
| VIS-P2-11 | 间距 | ListPageScaffold.vue L44,49 | padding: 1.25rem / gap: 1rem 硬编码 | 改用 --space-lg / --space-md |
| VIS-P2-12 | 字体 | 多处 | 主标题字号不一致（30px/26px/24px） | 统一为 --font-size-display: 24-28px |

### P3 低优先级（4 项）

| 编号 | 分类 | 问题 |
|------|------|------|
| VIS-P3-01 | 内联样式 | UserRiskPage/TextAssessTab/MisclassifiedTable 等大量内联 style |
| VIS-P3-02 | 图标 | MainLayout 侧边栏混用线性/填充图标 |
| VIS-P3-03 | 阴影 | BentoCell/UserDashboard/AdminDashboard 硬编码 box-shadow |
| VIS-P3-04 | 性能 | utilities.scss 全局 body::before 噪点纹理影响渲染性能 |

### P4 建议（3 项）

- VIS-P4-01：抽离 chartPalette.ts 统一管理图表色板
- VIS-P4-02：getScoreColor/getStatusTag 等通用映射函数抽到 utils/riskFormatters.ts
- VIS-P4-03：统一表单布局组件 FormCard，固化 label-width 和提交按钮位置

---

## 📱 响应式问题（RSP）

### P1 高优先级（2 项）

| 编号 | 文件#行号 | 问题 | 修复建议 |
|------|-----------|------|----------|
| RSP-P1-01 | AdminCrisisEventsPage L244,302,345 / UserRiskPage L219 | 所有 el-dialog width="500px"，移动端横向溢出 | 改为 :width="isMobile ? '90vw' : '500px'" |
| RSP-P1-02 | BottomNav.vue L42-48 | BottomNav 角色覆盖不全：admin 无底部导航；/settings 对所有角色跳同一地址 | 按 role 渲染不同 BottomNav 项 |

### P2 中优先级（6 项）

| 编号 | 文件#行号 | 问题 | 修复建议 |
|------|-----------|------|----------|
| RSP-P2-03 | CounselorUserDetailPage.vue L16-37 | el-descriptions :column="2" 小屏未切换为单列 | :column="isMobile ? 1 : 2" |
| RSP-P2-04 | PageTable.vue | 表格无小屏适配策略 | 关键列保留 + 次要列隐藏 + 横向滚动 |
| RSP-P2-05 | FilterBar.vue L1-3 | 筛选项 >4 时小屏挤压 | 支持展开/收起 |
| RSP-P2-06 | LoginPage.vue L477, AuthBrandPanel.vue L271 | 登录页断点 960px 与 useBreakpoint 992px 不匹配 | 统一断点 |
| RSP-P2-07 | UserRiskPage.vue L58 | style="max-width: 760px" 大屏固定小屏未适配 | 改用响应式 max-width |
| RSP-P2-08 | BaseChart.vue L34, UserDashboard.vue L961 | 图表高度 300px 在小屏未降低 | 改为 :height="isMobile ? '200px' : '300px'" |

### P3 低优先级（2 项）

| 编号 | 问题 |
|------|------|
| RSP-P3-09 | PageTable 分页 layout="total, sizes, prev, pager, next" 在 375px 屏被挤压 |
| RSP-P3-10 | MainLayout header-right 在 768px 时用户名直接消失 |

---

## 🎨 UX 问题（UX）

### P1 高优先级（2 项）

| 编号 | 问题 | 修复建议 |
|------|------|----------|
| UX-P1-01 | 全项目 15 处 ElMessageBox.confirm 全部使用 type:'warning'，删除账户/解绑咨询师/删除模板等不可逆操作未使用 danger | 改为 type:'error' 或自定义 danger 按钮 |
| UX-P1-02 | ErrorPage 404/403/500 文案硬编码中文未走 i18n | 迁移到 i18n |

### P2 中优先级（9 项）

| 编号 | 问题 | 修复建议 |
|------|------|----------|
| UX-P2-03 | CounselorWarningsPage 批量操作未显示"已选 N 条/共 M 条" | 在 batch-actions 区显示选中数量 |
| UX-P2-04 | AdminCrisisEventsPage/UserRiskPage 导出无进度反馈 | 加百分比/大小提示 |
| UX-P2-05 | UserModelTrainingPage 训练任务无进度条或轮询机制 | 加进度条或 WebSocket 推送 |
| UX-P2-06 | 加载失败重试入口不一致（EmptyState vs StatefulContainer vs AdminDashboard） | 统一重试组件 |
| UX-P2-07 | 解绑咨询师等高风险操作确认文案不具体 | 加具体影响说明 |
| UX-P2-08 | UserDashboard 显示 severityLabel 但无 tooltip 解释等级判定标准 | 加 el-tooltip |
| UX-P2-09 | 所有列表页无"今天/最近 7 天/最近 30 天"快捷筛选 | 加快捷日期按钮 |
| UX-P2-10 | Dashboard 卡片点击区域不一致（仅底部按钮可跳转） | 整张卡片可点击 |
| UX-P2-11 | 图表 tooltip 解释不足（默认 axis crosshair） | 自定义 formatter 提供风险等级解释 |

### P3 低优先级（4 项）

| 编号 | 问题 |
|------|------|
| UX-P3-12 | CounselorUserDetailPage 操作区不固定（滚动后顶部 Tab 操作不在视口） |
| UX-P3-13 | CounselorUserDetailPage 无时间线视图（风险轨迹/干预记录） |
| UX-P3-14 | 错误提示位置不一致（toast vs 页面中部 vs 字段下） |
| UX-P3-15 | 长文案无折叠（description/note 等字段未配置 show-overflow-tooltip） |

---

## ♿ 可访问性问题（A11Y）

### P1 高优先级（4 项）

| 编号 | 文件#行号 | 问题 | 修复建议 |
|------|-----------|------|----------|
| A11Y-P1-01 | ErrorPage.vue L168-182 | 无深色模式（白底白字低对比） | 添加深色模式样式 |
| A11Y-P1-02 | BottomNav.vue L75,87 | 字号 10px 低于规范 12px | 改为 font-size: 12px |
| A11Y-P1-03 | BottomNav.vue L5 | aria-label="主导航" 硬编码中文未走 i18n | 改为 :aria-label="t('nav.mainNav')" |
| A11Y-P1-04 | SkipLink.vue L2,16 | "跳转到主内容" 硬编码 + #409eff 与 --primary-color 不一致 | i18n + var(--primary-color) |

### P2 中优先级（5 项）

| 编号 | 问题 | 修复建议 |
|------|------|----------|
| A11Y-P2-05 | 弹窗焦点管理缺失（未配置 :focus-on-close） | 配置焦点回归触发元素 |
| A11Y-P2-06 | UserDashboard 趋势图标 `<el-icon><Top /></el-icon>` 无 aria-label | 加 aria-label |
| A11Y-P2-07 | AdminCrisisEventsPage/UserDashboard 颜色作为唯一状态表达 | 加图标/文字辅助 |
| A11Y-P2-08 | BaseChart role="img" 但 ECharts tooltip 不可访问 | 加 aria-describedby 或替代文本 |
| A11Y-P2-09 | StatefulContainer 错误图标无 alt | 加 aria-label |

### P3 低优先级（3 项）

| 编号 | 问题 |
|------|------|
| A11Y-P3-10 | focus-visible 仅全局 outline，el-button 内部元素可能覆盖 |
| A11Y-P3-11 | UserDashboard .warning-item li 可点击但不可键盘聚焦 |
| A11Y-P3-12 | 未审查 index.html 的 <html lang> 是否随 i18n 切换更新 |

---

## 📋 增量审查发现 (Delta Audit Findings, 2026-07-10)

> 审查范围：feat/frontend-api-alignment 合并 + 并行进程改进 + WCAG/字体优化以来的前端新增/变更代码
> 关联问题编号：ISS-152 ~ ISS-164（详见 `05-audit-issues.md`）
> 修复状态：7 项全部已关闭（✅）

### 响应式问题（Delta）

| 编号 | 分类 | 文件#行号 | 问题 | 修复建议 | 状态 |
|------|------|-----------|------|----------|------|
| VIS-D-P1-13 | 弹窗 | HelpCenter.vue L35, L57 | el-dialog width="600px"/"440px" 移动端溢出（375px 屏幕横向滚动） | 改为 :width="isMobile ? '90vw' : '600px'" | ✅ 已关闭 (ISS-154) |
| VIS-D-P1-14 | 布局 | AdminObservabilityPage.vue L83-143 | el-col :span="6" 四列布局无响应式断点，移动端严重挤压 | 加 :xs="24" :sm="12" :md="6" 响应式断点 | ✅ 已关闭 (ISS-155) |

### 视觉一致性问题（Delta）

| 编号 | 分类 | 文件#行号 | 问题 | 修复建议 | 状态 |
|------|------|-----------|------|----------|------|
| VIS-D-P2-13 | 间距 | variables.scss L70 | --spacing-lg=16px 与 --spacing-md=16px 重复（应为 24px，符合 4/8/12/16/24/32 规范） | 改为 --spacing-lg: 24px | ✅ 已关闭 (ISS-159) |
| VIS-D-P3-05 | 色彩 | index.html L41-42, L53 | 骨架屏 loading 颜色硬编码 #eef2f6/#e8ecf0 未走令牌 | 改用 var(--skeleton-bg) 或 CSS 变量 | ✅ 已关闭 (ISS-163) |

### UX 问题（Delta）

| 编号 | 分类 | 文件#行号 | 问题 | 修复建议 | 状态 |
|------|------|-----------|------|----------|------|
| UX-D-P2-16 | 交互 | AdminCanaryPage.vue L60-68 | 金丝雀部署操作按钮（创建/完成/回滚）无 loading 状态，重复点击风险 | 加 :loading="submitting" 状态 | ✅ 已关闭 (ISS-161) |
| UX-D-P2-17 | 交互 | AdminMonitoringPage.vue L100 | 详情展示用 `<pre>{{ JSON.stringify(detailRow, null, 2) }}</pre>` 原始 JSON 不友好 | 改用 el-descriptions 或格式化展示 | ✅ 已关闭 (ISS-158) |

### 可访问性问题（Delta）

| 编号 | 分类 | 文件#行号 | 问题 | 修复建议 | 状态 |
|------|------|-----------|------|----------|------|
| A11Y-D-P2-10 | 键盘 | AdminMonitoringPage.vue L91 | @row-click 无键盘可访问性（无 @keyup.enter） | 加 tabindex 和 @keyup.enter 处理 | ✅ 已关闭 (ISS-158) |

---

## 📊 美化问题统计 (Visual Beautification Statistics)

> 含 2026-07-10 增量审查发现 7 项（Delta Audit），全部 7 项已关闭

| 分类 | 总数 | 待处理 | 修复中 | 已关闭 |
|------|------|--------|--------|--------|
| 色彩 | 19 | 18 | 0 | 1 |
| 字体 | 1 | 1 | 0 | 0 |
| 间距 | 6 | 5 | 0 | 1 |
| 圆角 | 1 | 1 | 0 | 0 |
| 阴影 | 1 | 1 | 0 | 0 |
| 图标 | 1 | 1 | 0 | 0 |
| 表格 | 2 | 2 | 0 | 0 |
| 表单 | 2 | 2 | 0 | 0 |
| 图表 | 5 | 5 | 0 | 0 |
| 弹窗 | 2 | 1 | 0 | 1 |
| 空状态 | 1 | 1 | 0 | 0 |
| 加载态 | 0 | 0 | 0 | 0 |
| 响应式 | 12 | 11 | 0 | 1 |
| 可访问性 | 13 | 12 | 0 | 1 |
| 交互 | 2 | 0 | 0 | 2 |
| **合计** | **67** | **61** | **0** | **6** |

---

## 🎯 整体视觉/UX 健康评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 设计令牌体系完整度 | 60/100 | 令牌命名分裂、间距/圆角不符合规范、断点不足 |
| 视觉一致性 | 65/100 | BentoCell 与 el-card 并存、硬编码颜色 30+ 处、label-width 5 种值 |
| 响应式覆盖度 | 55/100 | 弹窗无响应式、BottomNav 角色不全、断点混乱、表格无小屏策略 |
| 交互完整性 | 70/100 | 骨架屏/loading 较完善、批量操作有、但 danger 确认缺失、长任务无进度 |
| 可访问性 | 60/100 | SkipLink/BaseChart 有 aria-label，但 ErrorPage 无深色模式、BottomNav 字号 10px |
| i18n 覆盖度 | 70/100 | 页面主体已 i18n，但通用组件硬编码中文 |

### **综合健康评分：63 / 100**
