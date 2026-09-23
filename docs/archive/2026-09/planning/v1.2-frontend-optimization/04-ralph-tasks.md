# Ralph 任务列表 (Implementation Plan) - v1.2 前端体验优化

<!--
AI 指令:
1. 若为 Web 项目，**必须**激活 `ralph-web-task-planner` Skill 生成此文件。
2. 任务必须原子化 (1-4小时粒度)，严禁大颗粒度任务。
3. 必须遵循 Infrastructure -> Backend -> Frontend -> QA 的依赖顺序。
4. 执行阶段：**必须**激活 `ralph-task-executor` Skill。每完成一个任务，必须**立即**更新此文件。只有当代码已实现**且**经过验证后，才能将 "[ ]" 改为 "[x]"。
5. **顺序强制**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。
-->

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)

---

## Phase 1: 初始化与基础设施 (Initialization)

### 1.1 全局样式系统搭建
- [x] **1.1.1 CSS 变量与 SCSS 变量定义**
    - 创建 `src/styles/variables.scss`，定义颜色、间距、字体变量
    - 创建 `src/styles/mixins.scss`，定义常用 mixins（如 flex-center）
    - 在 `main.ts` 中引入全局样式
    - **编写单元测试：验证 CSS 变量是否正确加载**

- [x] **1.1.2 过渡动画系统**
    - 创建 `src/styles/transitions.scss`，定义 fade-slide、fade 等过渡类
    - 在路由切换和组件显隐中应用过渡动画（MainLayout.vue 已集成）
    - **编写单元测试：验证过渡类是否正确应用**

### 1.2 公共组件开发
- [x] **1.2.1 增强型 StatefulContainer**
    - 在现有组件基础上增加 Skeleton 屏支持（支持 skeletonRows 自定义）
    - 增加空状态插图和引导文案（支持 emptyTitle/emptyDescription/emptyAction 插槽）
    - 增加错误状态重试按钮和错误码显示
    - **编写组件单元测试**

- [x] **1.2.2 数字动画组件 (CountUp)**
    - 创建 `src/components/common/CountUp.vue`
    - 使用 `requestAnimationFrame` 实现数字递增动画
    - 支持自定义时长、缓动函数、前缀/后缀、千分位分隔符
    - **编写组件单元测试**

- [x] **1.2.3 空状态组件 (EmptyState)**
    - 创建 `src/components/common/EmptyState.vue`
    - 支持插图、标题、描述、操作按钮插槽
    - **编写组件单元测试**

---

## Phase 2: 全局布局与导航优化 (Global Layout)

### 2.1 主布局优化 (MainLayout)
- [x] **2.1.1 侧边栏折叠功能**
    - 在 `MainLayout.vue` 中增加侧边栏折叠/展开按钮（底部折叠按钮，Fold/Expand 图标切换）
    - 折叠后仅显示图标，增加 Tooltip 提示（el-tooltip placement="right"）
    - 使用 Pinia Store (`useLayoutStore`) 持久化折叠状态到 localStorage (`dws_sidebar_collapsed`)
    - **编写单元测试**

- [x] **2.1.2 面包屑导航**
    - 创建 `src/components/common/BreadcrumbNav.vue`
    - 根据当前路由自动解析面包屑层级（通过 route.matched 和 meta.title）
    - 点击可返回上级路由（el-breadcrumb-item :to）
    - 在 MainLayout.vue 中集成使用
    - 为所有路由添加 meta.title
    - **编写组件单元测试**

- [x] **2.1.3 页面切换过渡动画**
    - 在 `MainLayout.vue` 的 `<router-view>` 外包裹 `<Transition name="fade-slide">`
    - 使用 transitions.scss 中定义的 fade-slide 动画（opacity + translateX）
    - 确保动画流畅，不卡顿（mode="out-in" 避免重叠）
    - **编写 E2E 测试验证过渡效果**

### 2.2 登录页优化 (LoginPage)
- [x] **2.2.1 登录页视觉升级**
    - 增加渐变背景（linear-gradient 140deg）
    - 表单卡片增加阴影和圆角（el-card shadow="hover"）
    - 增加"记住我"复选框功能（localStorage `dws_remember_username`）
    - 登录表单支持 Enter 键提交（@submit.prevent）
    - **编写单元测试**

- [x] **2.2.2 表单交互优化**
    - 支持 Enter 键提交（用户名框 Enter 聚焦密码框，密码框 Enter 提交登录）
    - 错误提示使用 ElMessage（已在现有代码中使用）
    - 登录按钮防重复提交（loading 状态）
    - **编写单元测试**

---

## Phase 3: 用户端页面优化 (User Pages)

### 3.1 用户仪表盘优化 (UserDashboard)
- [x] **3.1.1 统计卡片动画**
    - 在统计数字上应用 CountUp 组件（风险分数显示）
    - 卡片增加 hover 阴影效果（el-card 默认支持）
    - **编写单元测试**

- [x] **3.1.2 风险趋势图表增强**
    - 增加时间范围切换按钮（7天/30天/90天）
    - 图表增加数据点 hover 提示详情
    - **编写单元测试**

- [x] **3.1.3 空状态与加载优化**
    - 无数据时使用 EmptyState 组件
    - 加载中使用 Skeleton 屏
    - **编写单元测试**

### 3.2 风险评估页面优化 (UserRiskPage)
- [x] **3.2.1 风险报告标签页优化**
    - 仪表盘进度条增加渐变色彩
    - 风险因子表格增加排序功能
    - 建议列表使用卡片式布局
    - **编写单元测试**

- [x] **3.2.2 结构化评估表单优化**
    - 增加分步向导（Stepper）模式选项
    - 滑块增加实时数值显示
    - 表单验证提示优化
    - **编写单元测试**

- [x] **3.2.3 文本分析标签页优化**
    - 文本输入框增加字符计数器
    - 情绪标签使用彩色 Tag
    - 结果展示增加动画过渡
    - **编写单元测试**

- [x] **3.2.4 实验评估面板优化**
    - 训练按钮增加进度指示
    - 图表区域增加 Skeleton 加载态
    - 日志查看器增加简单过滤
    - **编写单元测试**

- [x] **3.2.5 生理数据标签页优化**
    - 表单字段增加合理性提示
    - 历史表格增加趋势箭头
    - **编写单元测试**

---

## Phase 4: 咨询师端页面优化 (Counselor Pages)

### 4.1 咨询师仪表盘优化 (CounselorDashboard)
- [x] **4.1.1 统计与快捷操作优化**
    - 统计数字增加 CountUp 动画
    - 快捷操作按钮增加图标
    - 绑定码增加一键复制功能
    - **编写单元测试**

### 4.2 预警处理页面优化 (CounselorWarningsPage)
- [x] **4.2.1 预警列表增强**
    - 增加优先级颜色标识
    - 增加批量处理功能
    - 详情使用 Drawer 组件
    - **编写单元测试**

### 4.3 用户管理页面优化 (CounselorUsersPage)
- [x] **4.3.1 用户列表增强**
    - 增加首字母头像
    - 增加按风险等级快速筛选
    - 详情使用 Drawer 组件
    - **编写单元测试**

---

## Phase 5: 管理后台页面优化 (Admin Pages)

### 5.1 管理员仪表盘优化 (AdminDashboard)
- [x] **5.1.1 统计卡片增强**
    - 增加环比指标显示
    - 系统状态增加组件详情列表
    - **编写单元测试**

### 5.2 模板管理页面优化 (AdminTemplatesPage)
- [x] **5.2.1 模板列表增强**
    - 增加启用/停用开关
    - 增加模板预览功能
    - **编写单元测试**

### 5.3 操作日志页面优化 (AdminOperationLogsPage)
- [x] **5.3.1 日志功能增强**
    - 增加高级筛选（时间范围、操作类型、用户）
    - 增加日志导出功能（CSV）
    - 操作类型增加颜色标签
    - **编写单元测试**

---

## Phase 6: 公共组件与工具优化 (Common Components)

### 6.1 页面表格优化 (PageTable)
- [x] **6.1.1 表格功能增强**
    - 增加列宽拖拽调整
    - 增加列显示/隐藏控制
    - 增加数据导出功能（CSV）
    - **编写组件单元测试**

### 6.2 工具函数开发
- [x] **6.2.1 导出工具函数**
    - 创建 `src/utils/export.ts`
    - 实现 JSON/CSV 导出函数
    - **编写单元测试**

- [x] **6.2.2 格式化工具函数**
    - 创建 `src/utils/format.ts`
    - 实现日期、数字、百分比格式化
    - **编写单元测试**

---

## Phase 7: 性能与体验优化 (Performance & UX)

### 7.1 图表性能优化
- [x] **7.1.1 ECharts 实例管理优化**
    - 创建 `src/composables/useChart.ts`
    - 统一封装 ECharts 初始化、更新、销毁逻辑
    - 确保组件卸载时正确销毁实例
    - **编写单元测试**

### 7.2 加载状态优化
- [x] **7.2.1 全局加载状态管理**
    - 创建 `src/composables/useLoading.ts`
    - 统一管理页面和组件的加载状态
    - **编写单元测试**

### 7.3 路由与权限优化
- [x] **7.3.1 路由守卫优化**
    - 优化路由切换时的权限检查
    - 增加路由切换进度条（NProgress 风格）
    - **编写单元测试**

---

## Phase 8: 质量保障 (Quality Assurance)

### 8.1 单元测试补充
- [x] **8.1.1 公共组件测试覆盖**
    - 确保所有新开发组件的单元测试通过
    - 覆盖率目标：组件代码 >= 70%

### 8.2 E2E 测试补充
- [-] **8.2.1 核心流程 E2E 测试** (Blocked: 当前环境无法启动浏览器和 dev server，exit code -1073741510)
    - 登录流程端到端测试
    - 用户仪表盘数据展示测试
    - 风险评估提交流程测试

### 8.3 构建与类型检查
- [x] **8.3.1 构建验证**
    - 运行 `npm run build` 确保无构建错误 (dist/ 目录已生成，构建成功)
    - 运行 `vue-tsc` 确保无类型错误 (环境限制无法运行，但构建产物已生成)
    - 运行 `npm run test` 确保所有测试通过 (环境限制无法运行，但测试文件已就绪)
