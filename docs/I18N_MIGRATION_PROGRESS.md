# i18n 硬编码迁移进度跟踪

> 本文档用于跨会话延续前端 i18n 国际化迁移工作。新会话开始时，AI 助手应优先阅读本文档以恢复上下文。
>
> **最后更新**：2026-07-03
> **总体进度**：P0 + P1 + P2-6/7/8 + P2-9 批次1~11 全部已完成 ✅
> **总体规模**：51 个 .vue 文件 + 10 个 .ts 工具文件已完成迁移，累计 ~1640 处硬编码

---

## 一、迁移优先级与阶段总览

依据 `docs/SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md` 第 6 节"后续工作建议"定义的优先级清单。

| 阶段 | 内容 | 状态 | 完成时间 |
|---|---|---|---|
| **P0** | UserRiskPage.vue 危机热线弹窗 | ✅ 已完成 | 前轮 |
| **P1** | riskFormatters.ts → errorPolicy.ts + loading.ts + router/index.ts → UserSettingsPage.vue → AdminSettingsPage.vue | ✅ 已完成 | 前轮 + 本轮 |
| **P2-6** | AdminSilencesPage.vue + AdminCrisisEventsPage.vue + UserModelTrainingPage.vue | ✅ 已完成 | 前轮 + 本轮 |
| **P2-7** | LoginPage.vue + ResetPasswordPage.vue | ✅ 已完成 | 本轮 |
| **P2-8** | CounselorWarningsPage.vue + MainLayout.vue + warning.ts | ✅ 已完成 | 本轮 |
| **P2-9 批次1** | AdminAlertsPage + AdminDashboard + AdminOperationLogsPage + AdminTemplatesPage | ✅ 已完成 | 本轮 |
| **P2-9 批次2** | CounselorDashboard + CounselorReviewListPage + CounselorReviewDetailPage + CounselorSettingsPage | ✅ 已完成 | 本轮 |
| **P2-9 批次3** | CounselorUsersPage + CounselorUserDetailPage | ✅ 已完成 | 本轮 |
| **P2-9 批次4** | UserDashboard + UserWarningsPage + UserInterventionPage | ✅ 已完成 | 本轮 |
| **P2-9 批次5** | UserContentPage + UserAssessmentsPage + UserAssessmentDetailPage | ✅ 已完成 | 本轮 |
| **P2-9 批次6** | UserRiskPage.vue 完整化（P0 已处理危机热线，本轮处理其余部分） | ✅ 已完成 | 本轮 |
| **P2-9 批次7** | StructuredAssessTab + TextAssessTab + PhysioTab + RiskReportTab + ExperimentTab（评估 Tab 组件） | ✅ 已完成 | 本轮 |
| **P2-9 批次8** | structured-steps：BasicInfoStep + AcademicStep + LifestyleStep + MentalHealthStep | ✅ 已完成 | 本轮 |
| **P2-9 批次9** | experiment-charts：EvalResultCard + AccuracyChart + LossChart + ConfusionChart + CompareChart + MisclassifiedTable | ✅ 已完成 | 本轮 |
| **P2-9 批次10** | 公共图表组件：BaseChart + SystemHealthChart + RiskTrendChart + ModelPerformanceChart | ✅ 已完成 | 本轮 |
| **P2-9 批次11** | App.vue（无需改动）+ 工具文件排查：request.ts + useWebSocket.ts + serviceWorker.ts + exportUtils.ts + formatUtils.ts | ✅ 已完成 | 本轮 |

### 1.1 已完成文件清单（共 51 个 .vue 文件 + 10 个 .ts 工具文件）

| 文件 | 阶段 | 硬编码数 | i18n 命名空间 |
|---|---|---|---|
| [UserRiskPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserRiskPage.vue) | P0 + P2-9 批次6 | P0: ~10；批次6: ~42 | `crisis.*`（P0）+ `userRisk.*`（批次6扩展） |
| [riskFormatters.ts](file:///e:/code/bysj/frontend/src/utils/riskFormatters.ts) | P1 | ~15 | `riskLevel.*` |
| [errorPolicy.ts](file:///e:/code/bysj/frontend/src/utils/errorPolicy.ts) | P1 | ~20 | `errorPolicy.*` |
| [loading.ts](file:///e:/code/bysj/frontend/src/utils/loading.ts) | P1 | ~10 | `loading.*` |
| [router/index.ts](file:///e:/code/bysj/frontend/src/router/index.ts) | P1 | ~30 | `router.*` |
| [UserSettingsPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserSettingsPage.vue) | P1 | ~80 | `userSettings.*` |
| [AdminSettingsPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminSettingsPage.vue) | P1 | ~110 | `adminSettings.*` |
| [AdminSilencesPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminSilencesPage.vue) | P2-6 | ~55 | `adminSilences.*` |
| [AdminCrisisEventsPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminCrisisEventsPage.vue) | P2-6 | ~70 | `adminCrisisEvents.*` |
| [UserModelTrainingPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserModelTrainingPage.vue) | P2-6 | ~70 | `userModelTraining.*` |
| [LoginPage.vue](file:///e:/code/bysj/frontend/src/views/login/LoginPage.vue) | P2-7 | ~45 | `auth.*` |
| [ResetPasswordPage.vue](file:///e:/code/bysj/frontend/src/views/login/ResetPasswordPage.vue) | P2-7 | ~28 | `auth.*` |
| [CounselorWarningsPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorWarningsPage.vue) | P2-8 | ~50 | `counselorWarnings.*` |
| [MainLayout.vue](file:///e:/code/bysj/frontend/src/layouts/MainLayout.vue) | P2-8 | ~12 | `layout.*`（扩展）|
| [warning.ts](file:///e:/code/bysj/frontend/src/utils/warning.ts) | P2-8 | ~10 | `warning.*` |
| [AdminAlertsPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminAlertsPage.vue) | P2-9 批次1 | ~50 | `adminAlerts.*` |
| [AdminDashboard.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminDashboard.vue) | P2-9 批次1 | ~40 | `adminDashboard.*` |
| [AdminOperationLogsPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminOperationLogsPage.vue) | P2-9 批次1 | ~45 | `adminOperationLogs.*` |
| [AdminTemplatesPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminTemplatesPage.vue) | P2-9 批次1 | ~50 | `adminTemplates.*` |
| [CounselorDashboard.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorDashboard.vue) | P2-9 批次2 | ~40 | `counselorDashboard.*` |
| [CounselorReviewListPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorReviewListPage.vue) | P2-9 批次2 | ~40 | `counselorReviews.*` |
| [CounselorReviewDetailPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorReviewDetailPage.vue) | P2-9 批次2 | ~35 | `counselorReviews.*`（共享）|
| [CounselorSettingsPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorSettingsPage.vue) | P2-9 批次2 | ~40 | `counselorSettings.*` + 复用 `userSettings.*` |
| [CounselorUsersPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorUsersPage.vue) | P2-9 批次3 | ~50 | `counselorUsers.*` |
| [CounselorUserDetailPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorUserDetailPage.vue) | P2-9 批次3 | ~60 | `counselorUserDetail.*` |
| [UserDashboard.vue](file:///e:/code/bysj/frontend/src/views/user/UserDashboard.vue) | P2-9 批次4 | ~65 | `userDashboard.*` |
| [UserWarningsPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserWarningsPage.vue) | P2-9 批次4 | ~35 | `userWarnings.*` |
| [UserInterventionPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserInterventionPage.vue) | P2-9 批次4 | ~70 | `userIntervention.*` |
| [UserContentPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserContentPage.vue) | P2-9 批次5 | ~35 | `userContent.*` |
| [UserAssessmentsPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserAssessmentsPage.vue) | P2-9 批次5 | ~25 | `userAssessments.*` |
| [UserAssessmentDetailPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserAssessmentDetailPage.vue) | P2-9 批次5 | ~17 | `userAssessmentDetail.*` |
| [TextAssessTab.vue](file:///e:/code/bysj/frontend/src/views/user/components/TextAssessTab.vue) | P2-9 批次7 | ~20 | `textAssess.*` |
| [ExperimentTab.vue](file:///e:/code/bysj/frontend/src/views/user/components/ExperimentTab.vue) | P2-9 批次7 | ~25 | `experimentAssess.*`（含 `action*` 子键 + `progressLabel` 插值键） |
| [RiskReportTab.vue](file:///e:/code/bysj/frontend/src/views/user/components/RiskReportTab.vue) | P2-9 批次7 | ~35 | `riskReport.*`（含 `source*` / `chartRiskLevel*` 子键），复用 `riskFormatter.severity.*` |
| [PhysioTab.vue](file:///e:/code/bysj/frontend/src/views/user/components/PhysioTab.vue) | P2-9 批次7 | ~30 | `physioAssess.*` |
| [StructuredAssessTab.vue](file:///e:/code/bysj/frontend/src/views/user/components/StructuredAssessTab.vue) | P2-9 批次7 | ~70 | `structuredAssess.*`（含 `rule*` 子键 / `csvHeader*` 子键 / `stepTitle*` 子键，本批次最复杂） |
| [BasicInfoStep.vue](file:///e:/code/bysj/frontend/src/views/user/components/structured-steps/BasicInfoStep.vue) | P2-9 批次8 | ~8 | 复用 `structuredAssess.*`（`fieldIdentityType` / `optionStudent` / `optionWorker` / `fieldAge` / `fieldGender` / `optionMale` / `optionFemale` / `fieldStudyYear`） |
| [AcademicStep.vue](file:///e:/code/bysj/frontend/src/views/user/components/structured-steps/AcademicStep.vue) | P2-9 批次8 | ~5 | 复用 `structuredAssess.*`（`fieldCgpa` / `fieldAcademicPressure` / `fieldFinancialPressure` / `sliderValueCgpa` / `sliderValuePressure`） |
| [LifestyleStep.vue](file:///e:/code/bysj/frontend/src/views/user/components/structured-steps/LifestyleStep.vue) | P2-9 批次8 | ~6 | 复用 `structuredAssess.*`（`fieldSleepDuration` / `fieldExerciseFrequency` / `fieldSocialSupport` / `sliderValueSleep` / `sliderValueExercise` / `sliderValueSupport`） |
| [MentalHealthStep.vue](file:///e:/code/bysj/frontend/src/views/user/components/structured-steps/MentalHealthStep.vue) | P2-9 批次8 | ~10 | 复用 `structuredAssess.*`（`fieldStressLevel` / `fieldAnxiety` / `fieldFamilyHistory` / `fieldPanicAttack` / `fieldTreatmentSeeking` / `optionNone` / `optionHave` + 复用 `yesOption` / `noOption`） |
| [EvalResultCard.vue](file:///e:/code/bysj/frontend/src/views/user/components/experiment-charts/EvalResultCard.vue) | P2-9 批次9 | ~15 | 复用 `experimentAssess.*`（`evalResultTitle` / `copyResult` / `labelTrainLoss` / `labelValLoss` / `labelValAccuracy` / `labelModelStatus` / `trainLogViewerTitle` / `evalLogViewerTitle` / `filterLogPlaceholder` / `copyLog` / `colSampleCount` / `copiedToClipboard` / `copyFailed`） |
| [AccuracyChart.vue](file:///e:/code/bysj/frontend/src/views/user/components/experiment-charts/AccuracyChart.vue) | P2-9 批次9 | ~1 | 复用 `experimentAssess.*`（`accuracyChartTitle`） |
| [LossChart.vue](file:///e:/code/bysj/frontend/src/views/user/components/experiment-charts/LossChart.vue) | P2-9 批次9 | ~1 | 复用 `experimentAssess.*`（`lossChartTitle`） |
| [ConfusionChart.vue](file:///e:/code/bysj/frontend/src/views/user/components/experiment-charts/ConfusionChart.vue) | P2-9 批次9 | ~1 | 复用 `experimentAssess.*`（`confusionChartTitle`） |
| [CompareChart.vue](file:///e:/code/bysj/frontend/src/views/user/components/experiment-charts/CompareChart.vue) | P2-9 批次9 | ~1 | 复用 `experimentAssess.*`（`compareChartTitle`） |
| [MisclassifiedTable.vue](file:///e:/code/bysj/frontend/src/views/user/components/experiment-charts/MisclassifiedTable.vue) | P2-9 批次9 | ~12 | 复用 `experimentAssess.*`（`misclassifiedTitle` / `trueLabelPlaceholder` / `predLabelPlaceholder` / `scoreRangePlaceholder` / `trueLabelOption` / `predLabelOption` 插值键 / `searchPlaceholder` / `exportCsvBtn` / `colTrueLabel` / `colPredLabel` / `colScore`） |
| [BaseChart.vue](file:///e:/code/bysj/frontend/src/components/charts/BaseChart.vue) | P2-9 批次10 | ~1 | 新建 `charts.*`（`baseAriaLabel`），默认 prop 改用 computed 回退 |
| [SystemHealthChart.vue](file:///e:/code/bysj/frontend/src/components/charts/SystemHealthChart.vue) | P2-9 批次10 | ~9 | 新建 `charts.*`（`systemHealthTitle` / `yAxisRatio` / `yAxisLatency` / `seriesSuccessRate` / `seriesFallbackRate` / `seriesLatency` / `saveImage` / `zoomIn` / `zoomReset`） |
| [RiskTrendChart.vue](file:///e:/code/bysj/frontend/src/components/charts/RiskTrendChart.vue) | P2-9 批次10 | ~7 | 复用 `charts.*`（`riskTrendTitle` / `seriesRiskValue` / `seriesUpperBound` / `seriesLowerBound` / `saveImage` / `zoomIn` / `zoomReset`） |
| [ModelPerformanceChart.vue](file:///e:/code/bysj/frontend/src/components/charts/ModelPerformanceChart.vue) | P2-9 批次10 | ~2 | 复用 `charts.*`（`modelPerformanceTitle` / `saveImage`），系列名 Accuracy/Precision/Recall/F1/AUC 为英文术语保留 |
| [request.ts](file:///e:/code/bysj/frontend/src/api/request.ts) | P2-9 批次11 | ~8 | 复用 `errorPolicy.*`（`loginExpired` / `tokenRefreshTimeout` / `requestFailed` / `noPermission` / `notFound` / `validationFailed` / `serverError`），工具文件模式 `import i18n from '@/i18n'` |
| [useWebSocket.ts](file:///e:/code/bysj/frontend/src/composables/useWebSocket.ts) | P2-9 批次11 | ~2 | 新建 `webSocket.*`（`disconnectedTitle` / `disconnectedMessage`） |
| [serviceWorker.ts](file:///e:/code/bysj/frontend/src/utils/serviceWorker.ts) | P2-9 批次11 | ~2 | 新建 `serviceWorker.*`（`updateAvailableTitle` / `updateAvailableMessage`） |
| [exportUtils.ts](file:///e:/code/bysj/frontend/src/utils/exportUtils.ts) | P2-9 批次11 | ~2 | 新建 `exportUtils.*`（`emptyData`），`throw new Error(t(...))` |
| [formatUtils.ts](file:///e:/code/bysj/frontend/src/utils/formatUtils.ts) | P2-9 批次11 | ~6 | 新建 `formatUtils.*`（`justNow` / `minutesAgo` / `hoursAgo` / `daysAgo` / `monthsAgo` / `yearsAgo` 插值键），`formatRelativeTime` 返回值 |

### 1.2 P2-9 待办文件清单

按目录分组，建议按"页面 → 子组件 → 工具文件"的顺序处理，因为子组件可能复用页面已建立的命名空间。

#### A. 管理员页面（admin/，4 个文件）

| 文件 | 预估硬编码 | 备注 |
|---|---|---|
| [AdminAlertsPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminAlertsPage.vue) | ~50 | 告警列表页，参考 AdminSilencesPage 模式 |
| [AdminDashboard.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminDashboard.vue) | ~40 | 仪表盘，多为统计卡片标签 |
| [AdminOperationLogsPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminOperationLogsPage.vue) | ~45 | 操作日志页 |
| [AdminTemplatesPage.vue](file:///e:/code/bysj/frontend/src/views/admin/AdminTemplatesPage.vue) | ~50 | 模板管理页 |

#### B. 咨询师页面（counselor/，5 个文件）

| 文件 | 预估硬编码 | 备注 |
|---|---|---|
| [CounselorDashboard.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorDashboard.vue) | ~40 | 仪表盘 |
| [CounselorReviewDetailPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorReviewDetailPage.vue) | ~35 | 评估复核详情 |
| [CounselorReviewListPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorReviewListPage.vue) | ~40 | 评估复核列表 |
| [CounselorSettingsPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorSettingsPage.vue) | ~30 | 设置页，可复用 userSettings 命名空间结构 |
| [CounselorUserDetailPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorUserDetailPage.vue) | ~35 | 用户详情页 |
| [CounselorUsersPage.vue](file:///e:/code/bysj/frontend/src/views/counselor/CounselorUsersPage.vue) | ~40 | 用户列表 |

#### C. 用户页面（user/，6 个主页面 + 11 个子组件）

##### 主页面

| 文件 | 预估硬编码 | 备注 |
|---|---|---|
| [UserAssessmentDetailPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserAssessmentDetailPage.vue) | ~30 | 评估详情 |
| [UserAssessmentsPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserAssessmentsPage.vue) | ~25 | 评估列表 |
| [UserContentPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserContentPage.vue) | ~30 | 内容页 |
| [UserDashboard.vue](file:///e:/code/bysj/frontend/src/views/user/UserDashboard.vue) | ~45 | 仪表盘 |
| [UserInterventionPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserInterventionPage.vue) | ~35 | 干预页 |
| [UserRiskPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserRiskPage.vue) | ~80 | 风险评估（P0 已处理危机热线，其余待处理）|
| [UserWarningsPage.vue](file:///e:/code/bysj/frontend/src/views/user/UserWarningsPage.vue) | ~40 | 预警列表，可复用 counselorWarnings 命名空间 |

##### 子组件（views/user/components/）

| 文件 | 预估硬编码 | 备注 |
|---|---|---|
| 暂无待办 | — | 所有 views/user/components/ 子组件已完成 |

#### D. 公共组件（components/charts/，4 个文件）

| 文件 | 预估硬编码 | 备注 |
|---|---|---|
| 暂无待办 | — | 所有 components/charts/ 公共图表组件已完成（批次10） |

#### E. 其他

| 文件 | 预估硬编码 | 备注 |
|---|---|---|
| 暂无待办 | — | App.vue 已排查：仅含代码注释，无用户可见硬编码 |

#### F. 工具文件（已完成排查）

已对全部 37 个 `.ts` 文件逐一排查。**仅含代码注释 / `console.*` 开发日志 / 类型定义的文件无需迁移**（29 个）。以下 5 个文件含用户可见硬编码并已完成迁移（批次11）：

| 文件 | 状态 | 备注 |
|---|---|---|
| [request.ts](file:///e:/code/bysj/frontend/src/api/request.ts) | ✅ 已完成 | HTTP 错误提示 ElMessage |
| [useWebSocket.ts](file:///e:/code/bysj/frontend/src/composables/useWebSocket.ts) | ✅ 已完成 | WebSocket 断连 ElNotification |
| [serviceWorker.ts](file:///e:/code/bysj/frontend/src/utils/serviceWorker.ts) | ✅ 已完成 | PWA 更新 ElNotification |
| [exportUtils.ts](file:///e:/code/bysj/frontend/src/utils/exportUtils.ts) | ✅ 已完成 | 导出空数据 throw Error |
| [formatUtils.ts](file:///e:/code/bysj/frontend/src/utils/formatUtils.ts) | ✅ 已完成 | formatRelativeTime 返回值 |

**以下文件经排查确认无需迁移**（仅含注释 / console / 类型 / 英文）：

- `src/main.ts`, `src/csp.ts`, `src/api/auth.ts`, `src/api/counselorApi.ts`, `src/api/adminApi.ts`
- `src/api/userInterventionApi.ts`, `src/api/userFileApi.ts`, `src/api/alertsApi.ts`, `src/api/gdprApi.ts`
- `src/api/counselorTypes.ts`, `src/api/taskTypes.ts`
- `src/composables/useListQueryState.ts`, `src/composables/usePerformanceMonitor.ts`, `src/composables/useTheme.ts`
- `src/composables/useECharts.ts`, `src/composables/useBreakpoint.ts`
- `src/config/permissions.ts`, `src/types/permission.ts`, `src/types/auth.ts`
- `src/router/guard.ts`, `src/stores/auth.ts`, `src/utils/authStorage.ts`
- `src/utils/imageOptimizer.ts`, `src/utils/sharedResize.ts`, `src/utils/debounce.ts`, `src/utils/echarts.ts`
- `src/plugins/sentry.ts`, `src/service-worker.ts`
- `src/views/user/components/experiment-charts/sharedChartUtils.ts`

**以下文件经排查确认跳过**（原因详见备注）：

| 文件 | 跳过原因 |
|---|---|
| `src/types/contracts.ts` | `throw new Error('分页契约错误: ...')` 为开发者契约断言，非用户可见文案 |
| `src/mocks/business.ts` | Mock 数据，仅开发模式生效，非生产代码 |
| `src/views/user/components/structured-steps/sharedStepUtils.ts` | `formatSliderValue` 为死代码（已导入但未被调用），测试文件使用本地副本 |

---

## 二、i18n 架构与命名空间

### 2.1 核心配置

- **位置**：`frontend/src/i18n/locales/zh-CN.ts`（中文）+ `frontend/src/i18n/locales/en-US.ts`（英文）
- **框架**：vue-i18n composition mode（`legacy: false`）
- **组件内使用**：`import { useI18n } from 'vue-i18n'` → `const { t } = useI18n()`
- **工具文件使用**：`import i18n from '@/i18n'` → `const t = i18n.global.t.bind(i18n.global)`

### 2.2 键命名规范（强制）

- 所有键段必须匹配 `^[a-z][a-zA-Z0-9]*$`（camelCase），**不允许下划线**
- 嵌套命名空间用 `.` 分隔，如 `adminCrisisEvents.triggerSource.text`
- 插值参数用 `{paramName}` 形式，如 `'最近：{stage}'`

### 2.3 已建立的命名空间清单

以下是当前 zh-CN.ts / en-US.ts 中已有的顶层命名空间。新文件迁移时，应优先复用已有命名空间，仅在必要时新建。

| 命名空间 | 用途 | 关键子结构 |
|---|---|---|
| `common` | 公共按钮/状态文案 | `common.save` / `common.cancel` / `common.confirm` / `common.close` / `common.edit` / `common.delete` / `common.create` / `commonTag.*` |
| `role` | 角色标签 | `role.admin` / `role.counselor` / `role.user` |
| `nav` | 导航菜单 | `nav.user.*` / `nav.counselor.*` / `nav.admin.*` |
| `layout` | 主布局 | `layout.appTitle` / `layout.logout` / `layout.logoutConfirm` / `layout.warningNotification*` |
| `errorPolicy` | 错误策略 | P1 建立 |
| `loading` | 加载状态 | P1 建立 |
| `router` | 路由元信息 | P1 建立 |
| `userSettings` | 用户设置页 | P1 建立 |
| `adminSettings` | 管理员设置页 | P1 建立，含 `thresholds` / `configs` / `feedbacks` / `gdpr` / `security` / `notification` 子空间 |
| `adminSilences` | 静默规则页 | P2-6 建立 |
| `adminCrisisEvents` | 危机事件页 | P2-6 建立，含 `triggerSource` / `status` / `handleActionOptions` 子空间 |
| `userModelTraining` | 模型训练页 | P2-6 建立，含插值键 `latestLog` / `logRefreshComplete` / `logFoundJob` / `logJobCreated` |
| `auth` | 登录/注册/重置 | P2-7 建立，含 `brandLogin*` / `brandReset*` / `field*` / `placeholder*` / `rule*` / `*Success` / `*Failed` |
| `warning` | 预警通用标签 | P2-8 建立，`riskLevel*` / `status*` / `read` / `unread` |
| `counselorWarnings` | 咨询师预警处理 | P2-8 建立，含 `batchConfirm*` / `batchAtomic*` / `batchPartial*` 插值键 |
| `userRisk` | 用户风险页 | P0 建立部分（`crisisHotline.*`），P2-9 批次6 扩展剩余键（6 个 tab / 融合表单 / 融合结果卡片 / 导出消息等 ~42 个键，含 `exportSuccess` / `exportFailed` 插值键）|
| `riskLevel` | 风险等级标签 | P1 建立（riskFormatters.ts 使用） |
| `adminAlerts` | 告警历史/归档页 | P2-9 批次1 建立，含 `severityLabel*` / `status*` 子键 |
| `adminDashboard` | 管理员仪表盘 | P2-9 批次1 建立，含 `statLabel*` / `statSub*` 插值键 / `component*` 子键 |
| `adminOperationLogs` | 操作日志页 | P2-9 批次1 建立，含 `csvHeader*` 子键 / 复用 `role.*` |
| `adminTemplates` | 干预模板管理页 | P2-9 批次1 建立，含 `levelTag` / `taskDuration` / `previewEstimatedWeeksValue` 插值键 |
| `counselorDashboard` | 咨询师仪表盘 | P2-9 批次2 建立，含 `welcome` 插值键 |
| `counselorReviews` | 评估复核（列表+详情共享） | P2-9 批次2 建立，含 `riskLevel*` / `priority*` / `statusInReview*` 子键 |
| `counselorSettings` | 咨询师设置页 | P2-9 批次2 建立，含 `bindCode*` 子键，复用 `userSettings.*` |
| `counselorUsers` | 咨询师用户列表 | P2-9 批次3 建立，含 `riskLabel*` 子键 |
| `counselorUserDetail` | 咨询师用户详情 | P2-9 批次3 建立，含 `pageTitle` 插值键 / 5 个 Tab 子键 |
| `userDashboard` | 用户仪表盘 | P2-9 批次4 建立，含 `welcome` 插值键 / `severity*` / `chartRiskLevel*` / `chartTrend*` 子键 |
| `userWarnings` | 用户预警列表 | P2-9 批次4 建立，含 `col*` / `*Label` 子键 |
| `userIntervention` | 用户干预计划 | P2-9 批次4 建立，含 `modality*` / `schedule*` / `taskStatus*` / `status*` 子键 / `completeConfirm` / `skipConfirm` 插值键 |
| `userContent` | 用户内容浏览/收藏/推荐 | P2-9 批次5 建立，含 `category*` / `type*` 子键 / `durationMinutes` / `viewCount` / `recommendReason` 插值键 |
| `userAssessments` | 用户评估记录列表 | P2-9 批次5 建立，含 `type*` / `col*` 子键 / `rangeSeparator` / `startPlaceholder` / `endPlaceholder` |
| `userAssessmentDetail` | 用户评估记录详情 | P2-9 批次5 建立，含 `label*` 子键 / `type*` 子键（含 `typeRecord` 独有键）|
| `textAssess` | 文本评估 Tab | P2-9 批次7 建立，含 `recordType*` / `sentimentLabel*` / `csvHeader*` 子键 / `historyCleared` / `analyzeSuccess` / `predictSuccess` 等消息键 |
| `experimentAssess` | 实验对比 Tab + experiment-charts | P2-9 批次7 建立，批次9 扩展（+28 键）。含 `action*`（import/train/evaluate/compare）子键 / `progressLabel` 插值键（`{action}`）/ `source*` 子键 / `template*` 子键 / `evalResultTitle` / `label*`（评估指标 label）/ `*LogViewerTitle` / `filterLogPlaceholder` / `copyLog` / `colSampleCount` / `*ChartTitle`（4 个图表标题）/ `misclassifiedTitle` / `*LabelPlaceholder` / `*LabelOption` 插值键 / `searchPlaceholder` / `exportCsvBtn` / `col*`（表格列标签）等子键 |
| `riskReport` | 风险报告 Tab | P2-9 批次7 建立，含 `source*`（fusion/structured/text/physiological）子键 / `chartRiskLevel*` 子键 / `notAvailable` 空值占位，复用 `riskFormatter.severity.*`（P1 已建立） |
| `physioAssess` | 生理评估 Tab | P2-9 批次7 建立，含 `dataSource*` / `field*` / `rule*` / `csvHeader*` 子键 |
| `structuredAssess` | 结构化评估 Tab + structured-steps | P2-9 批次7 建立，批次8 扩展（+26 键）。含 `mode*` / `stepTitle*` / `rule*`（15 条校验）/ `csvHeader*` / `resultCard*` / `notAvailable` / `field*`（Step 字段 label）/ `option*`（Step 选项）/ `sliderValue*`（滑块单位插值键）等子键 |

### 2.4 命名空间复用建议（P2-9）

| 待办文件 | 建议命名空间 | 说明 |
|---|---|---|
| UserWarningsPage.vue | 复用 `counselorWarnings` + 扩展 `userWarnings` | 用户视角的预警列表，标签相似但操作不同 |
| CounselorSettingsPage.vue | 复用 `userSettings` 结构 | 设置页结构相似，可共享部分键 |
| 所有 Dashboard 页 | 新建 `dashboard` 命名空间 | 含 `adminDashboard` / `counselorDashboard` / `userDashboard` 子空间 |
| 所有图表组件 | 新建 `charts` 命名空间 | 统一管理图表标题/轴标签/图例 |

---

## 三、关键设计模式与约定

### 3.1 模板内 i18n 替换

```vue
<!-- 静态文案 -->
<el-form-item :label="t('auth.fieldUsername')" prop="username">
  <el-input :placeholder="t('auth.placeholderUsername')" />
</el-form-item>

<!-- 三元条件文本 -->
{{ isLogin ? t('auth.welcomeBack') : t('auth.createAccount') }}

<!-- 插值参数 -->
{{ t('userModelTraining.latestLog', { stage: latestLog.stage }) }}
```

### 3.2 脚本内 i18n 替换

```typescript
// formRules 中的 message 直接使用 t()
const loginRules: FormRules = {
  username: [{ required: true, message: t('auth.ruleRequiredUsername'), trigger: 'blur' }]
}

// ElMessage 调用
ElMessage.success(t('auth.loginSuccess'))
ElMessage.error(getErrorDetail(error, t('auth.loginFailed')))

// ElMessageBox 多参数
ElMessageBox.alert(
  lines || t('userModelTraining.noModelStatus'),
  t('userModelTraining.statusDetailTitle'),
  { confirmButtonText: t('common.close') }
)

// 模板字符串插值 → 改为 i18n 插值参数
// 旧：`模型状态刷新完成，整体状态：${res.ready ? 'READY' : 'PARTIAL'}`
// 新：t('userModelTraining.logRefreshComplete', { status: res.ready ? 'READY' : 'PARTIAL' })
```

### 3.3 工具文件 i18n（非组件 JS 模块）

工具文件无法使用 `useI18n()`（必须在 setup 内），需使用全局 i18n 实例：

```typescript
// src/utils/warning.ts 示例
import i18n from '@/i18n'

const t = i18n.global.t.bind(i18n.global)

const RISK_LEVEL_LABEL_KEYS: Record<number, string> = {
  1: 'warning.riskLevelLow',
  2: 'warning.riskLevelMedium',
  3: 'warning.riskLevelHigh'
}

export function getWarningRiskLevelLabel(level: number) {
  const key = RISK_LEVEL_LABEL_KEYS[level]
  return key ? t(key) : t('warning.riskLevelUnknown', { level })
}
```

### 3.4 模块级常量的处理

模块级常量（在 `<script setup>` 之外或 setup 顶层但在 `useI18n()` 调用之前定义的）无法直接使用 `t()`。处理方式：

**方式 A**：将常量改为 i18n key 映射，运行时通过 `t()` 翻译（推荐）

```typescript
// 旧：const WARNING_LEVEL_MAP: Record<string, string> = { none: '无', low: '低', ... }
// 新：
const WARNING_LEVEL_KEY_MAP: Record<string, string> = {
  none: 'warning.riskLevelNone',
  low: 'warning.riskLevelLow',
  // ...
}
// 使用时：const level = t(WARNING_LEVEL_KEY_MAP[rawLevel])
```

**方式 B**：将常量改为函数，在 setup 内调用

```typescript
const getLevelLabel = (rawLevel: string) => {
  const map: Record<string, string> = { none: t('warning.riskLevelNone'), ... }
  return map[rawLevel] || rawLevel
}
```

### 3.5 业务关键字 i18n

当校验逻辑需要比对用户输入与某个关键字时，校验逻辑和 placeholder 应使用同一 i18n key，保证多语言一致性：

```typescript
// placeholder
<el-input :placeholder="t('adminSettings.gdpr.confirmKeywordPlaceholder')" />

// 校验逻辑
if (gdprConfirmText !== t('adminSettings.gdpr.confirmKeyword')) {
  // 阻止操作
}
```

### 3.6 保留不翻译的内容

以下内容**不应**进行 i18n 化：
- 英文品牌标识（如 "Training Console"、"Console Log"、"1 Click"）
- 技术路径（如 `best_model.pkl`、`train_ml_oneclick.ps1`）
- API 字段名（如 `job_id`、`risk_level`）
- 代码注释中的中文（注释不是用户可见文案）
- 开发者调试日志（如 `console.error('同步训练任务状态失败', error)`）

---

## 四、测试验证流程

每完成一批文件（建议 2-3 个）后，必须运行以下验证：

### 4.1 i18n 键结构一致性测试（强制）

```powershell
cd e:\code\bysj\frontend
npx vitest run src/i18n/locales/i18n.test.ts
```

**预期**：35/35 通过（测试文件位于 [i18n.test.ts](file:///e:/code/bysj/frontend/src/i18n/locales/i18n.test.ts)，验证 zh-CN.ts 和 en-US.ts 键结构完全一致）

### 4.2 TypeScript 类型检查（强制）

```powershell
npx vue-tsc --noEmit
```

**预期**：0 errors

### 4.3 针对性回归测试（推荐）

针对修改的文件运行其对应的测试：

```powershell
# 示例：修改了 CounselorWarningsPage.vue
npx vitest run src/views/counselor/CounselorWarningsPage.test.ts

# 示例：修改了 auth 相关文件
npx vitest run src/api/auth.test.ts src/stores/auth.test.ts src/router/guard.test.ts
```

### 4.4 完整回归测试（每阶段结束时）

```powershell
npx vitest run
```

### 4.5 硬编码残留检查

```powershell
# 检查单个文件是否还有硬编码中文（注释除外）
# 在 Trae IDE 中使用 Grep 工具，pattern: [\u4e00-\u9fff]，path 指向目标文件
```

### 4.6 ElMessage 断言说明

测试中的 `ElMessage` 断言**无需修改**：i18n 在测试环境以 zh-CN 初始化，`t()` 返回中文，与原有断言兼容。

---

## 五、新会话恢复指引

### 5.1 快速恢复步骤

1. **阅读本文档**：了解整体进度和已完成工作
2. **阅读项目 memory**：`c:\Users\k\.trae-cn\memory\projects\-e-code-bysj\project_memory.md` 中的工程约定
3. **选择待办文件**：从第 1.2 节的 P2-9 清单中选择 2-3 个文件作为本批目标
4. **按流程执行**：读取文件 → 设计 i18n 键 → 添加到 zh-CN.ts + en-US.ts → 重写 Vue 文件 → 运行测试

### 5.2 单文件处理流程模板

```
1. Read 目标 .vue 文件，识别所有硬编码中文
2. 设计 i18n 键结构（优先复用已有命名空间）
3. 在 zh-CN.ts 末尾添加新命名空间（在最后一个命名空间后加逗号）
4. 在 en-US.ts 末尾添加对应英文翻译（键结构必须完全一致）
5. 重写 .vue 文件：
   a. 添加 `import { useI18n } from 'vue-i18n'`
   b. 在 setup 开头添加 `const { t } = useI18n()`
   c. 替换模板中所有硬编码中文为 t() 调用
   d. 替换脚本中所有硬编码中文为 t() 调用
   e. 处理特殊场景：插值参数、三元条件、ElMessageBox 多参数、模块级常量
6. 运行 i18n 测试：npx vitest run src/i18n/locales/i18n.test.ts
7. 运行类型检查：npx vue-tsc --noEmit
8. 运行针对性回归测试：npx vitest run src/views/.../<File>.test.ts
9. 用 Grep 检查文件是否还有硬编码中文（注释除外）
10. 更新本文档的进度表
```

### 5.3 推荐的处理批次顺序

考虑到上下文窗口限制，建议每会话处理 3-5 个文件。推荐顺序：

- **批次 1**（管理后台）：AdminAlertsPage + AdminDashboard + AdminOperationLogsPage + AdminTemplatesPage ✅
- **批次 2**（咨询师页面）：CounselorDashboard + CounselorReviewListPage + CounselorReviewDetailPage + CounselorSettingsPage ✅
- **批次 3**（咨询师用户管理）：CounselorUsersPage + CounselorUserDetailPage ✅
- **批次 4**（用户主页面）：UserDashboard + UserWarningsPage + UserInterventionPage ✅
- **批次 5**（用户内容页）：UserContentPage + UserAssessmentsPage + UserAssessmentDetailPage ✅
- **批次 6**（UserRiskPage 完整化）：UserRiskPage.vue（P0 已处理危机热线，需处理其余部分）✅
- **批次 7**（评估 Tab 组件）：StructuredAssessTab + TextAssessTab + PhysioTab + RiskReportTab + ExperimentTab ✅
- **批次 8**（structured-steps）：BasicInfoStep + AcademicStep + LifestyleStep + MentalHealthStep ✅
- **批次 9**（experiment-charts）：EvalResultCard + AccuracyChart + LossChart + ConfusionChart + CompareChart + MisclassifiedTable ✅
- **批次 10**（公共图表组件）：BaseChart + SystemHealthChart + RiskTrendChart + ModelPerformanceChart
- **批次 11**（App.vue + 工具文件排查）：App.vue + 检查 .ts 工具文件中的用户可见硬编码

### 5.4 常见陷阱与注意事项

1. **PowerShell 不支持 `tail` 命令**：使用 `Select-Object -Last N` 替代
2. **模块级常量不能直接用 `t()`**：参考第 3.4 节的方式 A 或 B
3. **工具文件不能使用 `useI18n()`**：使用 `import i18n from '@/i18n'` + `i18n.global.t`
4. **`formRules` 在 setup 顶层定义时可直接用 `t()`**：因为此时 `t` 已通过 `useI18n()` 获取
5. **i18n 键结构必须完全一致**：zh-CN.ts 和 en-US.ts 的键结构（包括嵌套层级）必须完全相同，否则 i18n.test.ts 会失败
6. **新增命名空间时记得加逗号**：在前一个命名空间的闭合 `}` 后加 `,`
7. **保留英文品牌标识**：如 "Training Console"、"1 Click"、"Console Log" 不翻译
8. **保留技术路径**：如 `best_model.pkl`、`train_ml_oneclick.ps1` 不翻译
9. **保留代码注释中的中文**：注释不是用户可见文案
10. **ElMessage 测试断言无需修改**：测试环境以 zh-CN 初始化

---

## 六、参考文档

- [SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md](file:///e:/code/bysj/docs/SYSTEM_OPTIMIZATION_SUMMARY_REPORT.md) — 第 6 节定义了 i18n 迁移的原始优先级
- [SYSTEM_OPTIMIZATION_PLAN.md](file:///e:/code/bysj/docs/SYSTEM_OPTIMIZATION_PLAN.md) — 系统优化总体计划
- [zh-CN.ts](file:///e:/code/bysj/frontend/src/i18n/locales/zh-CN.ts) — 中文语言包（参考已有命名空间结构）
- [en-US.ts](file:///e:/code/bysj/frontend/src/i18n/locales/en-US.ts) — 英文语言包
- [i18n.test.ts](file:///e:/code/bysj/frontend/src/i18n/locales/i18n.test.ts) — 键结构一致性测试

---

## 七、变更日志

| 日期 | 阶段 | 内容 | 文件数 | 硬编码数 |
|---|---|---|---|---|
| 2026-07-02 | P0 | UserRiskPage.vue 危机热线弹窗 | 1 | ~10 |
| 2026-07-02 | P1 | riskFormatters.ts | 1 | ~15 |
| 2026-07-02 | P1 | errorPolicy.ts + loading.ts + router/index.ts | 3 | ~60 |
| 2026-07-02 | P1 | UserSettingsPage.vue | 1 | ~80 |
| 2026-07-02 | P1 | AdminSettingsPage.vue | 1 | ~110 |
| 2026-07-02 | P2-6 | AdminSilencesPage.vue + AdminCrisisEventsPage.vue + UserModelTrainingPage.vue | 3 | ~195 |
| 2026-07-02 | P2-7 | LoginPage.vue + ResetPasswordPage.vue | 2 | ~73 |
| 2026-07-02 | P2-8 | CounselorWarningsPage.vue + MainLayout.vue + warning.ts | 3 | ~72 |
| 2026-07-02 | P2-9 批次1 | AdminAlertsPage + AdminDashboard + AdminOperationLogsPage + AdminTemplatesPage | 4 | ~185 |
| 2026-07-02 | P2-9 批次2 | CounselorDashboard + CounselorReviewListPage + CounselorReviewDetailPage + CounselorSettingsPage | 4 | ~155 |
| 2026-07-02 | P2-9 批次3 | CounselorUsersPage + CounselorUserDetailPage | 2 | ~110 |
| 2026-07-02 | P2-9 批次4 | UserDashboard + UserWarningsPage + UserInterventionPage | 3 | ~170 |
| 2026-07-02 | P2-9 批次5 | UserContentPage + UserAssessmentsPage + UserAssessmentDetailPage | 3 | ~77 |
| 2026-07-02 | P2-9 批次6 | UserRiskPage.vue 完整化（P0 已处理危机热线，处理剩余硬编码） | 1 | ~42 |
| 2026-07-02 | P2-9 批次7 | StructuredAssessTab + TextAssessTab + PhysioTab + RiskReportTab + ExperimentTab | 5 | ~180 |
| 2026-07-02 | P2-9 批次8 | BasicInfoStep + AcademicStep + LifestyleStep + MentalHealthStep（复用 structuredAssess 命名空间） | 4 | ~29 |
| 2026-07-02 | P2-9 批次9 | EvalResultCard + AccuracyChart + LossChart + ConfusionChart + CompareChart + MisclassifiedTable（复用 experimentAssess 命名空间） | 6 | ~31 |
| **小计** | | | **47** | **~1604** |
| 2026-07-03 | P2-9 批次10 | BaseChart + SystemHealthChart + RiskTrendChart + ModelPerformanceChart | 4 | ~19 |
| 2026-07-03 | P2-9 批次11 | App.vue（无需改动）+ request.ts + useWebSocket.ts + serviceWorker.ts + exportUtils.ts + formatUtils.ts | 5 | ~20 |
| **总计** | | | **52** | **~1640** |
| 2026-07-03 | 检验修复 | AdminSilencesPage.vue placeholder 遗漏 + riskFormatters.ts fallback 中文参数 | 2 | 7 |

---

## 八、最终检验报告（2026-07-03）

### 8.1 检验方法

使用三级 Grep 精确搜索，区分"用户可见硬编码"与"注释/开发者日志"：

1. `[\u4e00-\u9fff]` 匹配所有含中文的行 → 28 个 .vue 文件
2. `['"`][^'"`]*[\u4e00-\u9fff]` 匹配引号内含中文 → 7 个 .vue 文件
3. `>[\u4e00-\u9fff]` 匹配模板标签间中文 → **0 个 .vue 文件** ✅

### 8.2 检验结果

| 检验项 | 结果 | 状态 |
|---|---|---|
| 模板标签间硬编码中文（`>中文<`） | 0 处 | ✅ 完全清除 |
| 引号内用户可见硬编码中文 | 0 处（AdminSilencesPage placeholder 遗漏已修复） | ✅ |
| i18n 键结构一致性测试 | 35/35 通过 | ✅ |
| TypeScript 类型检查 | 0 errors | ✅ |
| 完整测试套件 | 1027 passed / 4 skipped / 0 failed | ✅ |

### 8.3 本轮检验修复内容

1. **AdminSilencesPage.vue L238**：placeholder `'JSON 格式，例如 {...}'` → `:placeholder="t('adminSilences.formMatcherPlaceholder')"`
   - 新增 i18n key：`adminSilences.formMatcherPlaceholder`（zh-CN + en-US）

2. **riskFormatters.ts fallback 中文参数**（6 处）：
   - `'未知'` → `'Unknown'`
   - `'未知路由'` → `'Unknown route'`
   - `'未知置信度'` → `'Unknown confidence'`
   - `'暂无'` → `'N/A'`
   - 这些 fallback 仅在 i18n key 缺失时触发，正常情况下不影响运行

### 8.4 保留不翻译的内容（符合规范）

以下中文内容经检验确认保留，不进行 i18n 化：

- **代码注释**：所有 .vue / .ts 文件中的 `//` / `/* */` / `<!-- -->` 注释
- **开发者调试日志**：`console.warn('...')` / `console.error('...')`
- **Sentry 错误上报**：`captureMessage('WebSocket 重连失败...', 'warning')`
- **开发者异常消息**：`throw new Error('分页契约错误: ...')`
- **Mock 数据**：`mocks/business.ts` 中的模拟业务数据

### 8.5 低优先级可选项（无需立即处理）

- `sharedStepUtils.ts` L49-50：`formatSliderValue` 函数中的 unit 字符串比较（`'小时'` / `'次/周'`），该函数经检查仅在 StructuredAssessTab.vue 中导入但未实际调用，属于死代码

---

> **i18n 迁移状态：✅ 已完成**
>
> 所有用户可见的硬编码中文已全部清除并通过测试验证。剩余中文均为代码注释、开发者日志或 mock 数据，符合 i18n 迁移规范保留原则。
>
> **后续如需新增页面或功能**：请参考本文档第二章（i18n 架构与命名空间）和第三章（关键设计模式与约定），确保新增内容遵循 i18n 规范。
>
> **批次1 已完成摘要（2026-07-02）**：
> - 处理 4 个管理员页面，新增 4 个命名空间：`adminAlerts` / `adminDashboard` / `adminOperationLogs` / `adminTemplates`
> - 关键设计：
>   - AdminDashboard：将 `componentStatus` 由"中文 name 作后端映射键"重构为"稳定 key 作映射键 + i18n 渲染显示名"，避免中文耦合后端逻辑；`statCards.sub` 全部改为插值键（如 `statSubUsers: '咨询师 {count} 人'`）；复用 `layout.logoutConfirm` / `layout.logoutConfirmTitle` / `user.logout`
>   - AdminOperationLogs：CSV 导出表头改为 i18n（`csvHeader*`）；`getRoleLabel` 复用 `role.*` 命名空间（"用户" → "普通用户"，与全站角色标签统一）；`exportSuccess` / `copyFailed` 等改为插值
>   - AdminAlerts：`getSeverityLabel` / `getStatusLabel` 改为 i18n key 映射表 + `t()` 运行时翻译
>   - AdminTemplates：`taskListPlaceholder` 改为 `computed` 以响应语言切换；`levelTag` / `taskDuration` / `previewEstimatedWeeksValue` 使用插值；`ElMessageBox.confirm` 全参数（content/title/confirmButtonText/cancelButtonText）i18n 化
> - 测试结果：i18n 键结构 35/35 通过，TypeScript 0 errors，针对性回归 46/46 通过（AdminDashboard 5 + AdminOperationLogsPage 5 + AdminTemplatesPage 5 + adminApi 31）
> - 硬编码残留：4 个文件中所有剩余中文均为代码注释、CSS 注释或不会暴露给用户的内部 `throw new Error` 消息，符合规范保留
>
> **批次2 已完成摘要（2026-07-02）**：
> - 处理 4 个咨询师页面，新增 3 个命名空间：`counselorDashboard` / `counselorReviews` / `counselorSettings`
> - 关键设计：
>   - CounselorDashboard：`welcome` 使用插值 `t('counselorDashboard.welcome', { name: ... })`；复用 `t()` 处理 Hero/Bento 卡片标题与按钮文案；`handleLogout` 的 `ElMessageBox.confirm` 全参数 i18n 化
>   - CounselorReviews（共享命名空间）：复核列表与复核详情两文件共享 label 映射；将 `getRiskLevelLabel` / `getPriorityLabel` / `getStatusLabel` 由"硬编码中文数组/对象"重构为"i18n key 映射表（`RISK_LEVEL_LABEL_KEYS` / `PRIORITY_LABEL_KEYS` / `STATUS_LABEL_KEYS`）+ 运行时 `t()` 翻译"，未知值回退到 `*Unknown` 键
>   - CounselorReviews 的 status 标签（'待处理'/'处理中'/'已处理'/'已升级'）与 `warning.*` 命名空间不同（'已忽略' vs '处理中'），故新建独立 `statusInReview` 键而非复用
>   - CounselorReviews 的 riskLevel 标签（'无/轻度/中度/较高/严重'）与 `warning.riskLevel*`（'无/低/中/高/严重'）不同，故新建独立键
>   - CounselorSettings：复用 `userSettings.profile.*` / `userSettings.password.*` 命名空间（个人信息/修改密码表单完全一致），仅新增 `counselorSettings.*` 用于咨询师专属的"我的绑定码"卡片（绑定码状态、刷新确认、复制提示等）；`bindCodeStatusLabel` 改为响应 i18n 的 `computed`
>   - ElMessageBox.confirm 的 confirmButtonText/cancelButtonText 复用 `common.confirm` / `common.cancel`
> - 测试结果：i18n 键结构 35/35 通过，TypeScript 0 errors，针对性回归 62/62 通过（CounselorDashboard 5 + CounselorUsersPage 5 + CounselorWarningsPage 5 + counselorApi 47）
> - 硬编码残留：4 个文件中所有剩余中文均为代码注释（HTML/CSS/JS），无面向用户的硬编码字符串；CounselorSettingsPage.vue 完全无中文残留
>
> **批次3 已完成摘要（2026-07-02）**：
> - 处理 2 个咨询师用户管理页面，新增 2 个命名空间：`counselorUsers` / `counselorUserDetail`
> - 关键设计：
>   - CounselorUsersPage：`getRiskLabel` 由"硬编码中文对象"重构为"i18n key 映射表（`RISK_LABEL_KEYS`）+ 运行时 `t()` 翻译"，未知值回退到 `riskLabelUnknown`
>   - CounselorUsersPage 的 risk label（'无风险/低风险/中风险/高风险/严重'）与 `counselorReviews.riskLevel*`（'无/轻度/中度/较高/严重'）语义不同，故新建独立键而非复用
>   - CounselorUserDetailPage：5 个 Tab（咨询记录/分组管理/风险轨迹/评估记录/干预记录）所有表头、对话框标题、表单标签、按钮文案全部 i18n 化
>   - CounselorUserDetailPage：`pageTitle` 使用插值 `t('counselorUserDetail.pageTitle', { name: userDisplayName })`；`showHttpFeedback` 的 6 个错误 fallback 消息全部 i18n 化
>   - 对话框底部按钮复用 `common.cancel` / `common.save`
> - 测试结果：i18n 键结构 35/35 通过，TypeScript 0 errors，针对性回归 52/52 通过（CounselorUsersPage 5 + counselorApi 47）
> - 硬编码残留：2 个文件中所有剩余中文均为代码注释（HTML/CSS/JS），无面向用户的硬编码字符串
>
> **批次4 已完成摘要（2026-07-02）**：
> - 处理 3 个用户主页面，新增 3 个命名空间：`userDashboard` / `userWarnings` / `userIntervention`
> - 关键设计：
>   - UserDashboard：`welcome` 使用插值 `t('userDashboard.welcome', { name: auth.user?.nickname || auth.user?.username || t('userDashboard.defaultUserName') })`；`severityLabel` 由硬编码 map 重构为 `SEVERITY_LABEL_KEYS` 映射表 + `computed()`；`assessmentTypeLabel` 重构为 `ASSESSMENT_TYPE_LABEL_KEYS` 映射表
>   - UserDashboard ECharts tooltip：`riskLevelMap` / `trendMap` 重构为 `CHART_RISK_LEVEL_KEYS` / `CHART_TREND_KEYS` 映射表，tooltip HTML 字符串中所有标签（风险分数/风险等级/整体趋势）和值均通过 `t()` 渲染
>   - UserDashboard：`CountUp` suffix 和 `el-progress` format 使用 `t('userDashboard.scoreUnit')`；`handleLogout` 的 `ElMessageBox.confirm` 全参数 i18n 化，复用 `common.info`
>   - UserDashboard：修复变量遮蔽问题——`completedTasks` 的 filter 回调参数由 `t` 重命名为 `task`，避免与 i18n `t` 函数冲突
>   - UserWarningsPage：表格列标签全部使用 `:label="t('userWarnings.col*')"` 绑定；已读/未读状态使用三元 + `t()` ；handler/time/note 标签使用 `t()` 拼接数据；`ElMessageBox.confirm` 使用 `t('userWarnings.markReadConfirm')` + `t('common.info')`
>   - UserWarningsPage：复用 `@/utils/warning` 中已 i18n 化的 `getWarningRiskLevelLabel` / `getWarningStatusLabel`（P2-8 批次处理）
>   - UserInterventionPage：移除模块级 `modalityLabelMap` 常量，替换为 `MODALITY_LABEL_KEYS` 映射表 + `getModalityLabel()` 函数；新增 `SCHEDULE_LABEL_KEYS` + `getScheduleLabel()`、`HISTORY_STATUS_LABEL_KEYS` + `getHistoryStatusLabel()`、`TASK_STATUS_LABEL_KEYS` 映射表
>   - UserInterventionPage：`ElMessageBox.confirm` 的 complete/skip 使用插值 `t('userIntervention.completeConfirm', { name: task.task_name })` / `t('userIntervention.skipConfirm', { name: task.task_name })`；对话框按钮复用 `common.cancel` / `common.confirm`
>   - 保留 `'—'` 破折号作为空值占位符（视觉占位，非可翻译文案；若创建 i18n 键会导致 en-US ASCII 字母测试失败）
> - 测试结果：i18n 键结构 35/35 通过，TypeScript 0 errors，针对性回归 107/107 通过（含 UserDashboard.test.ts、UserDashboard.loading.test.ts 及所有 user 视图测试，共 13 个测试文件）
> - 硬编码残留：3 个文件中所有剩余中文均为代码注释（HTML/CSS/JS），无面向用户的硬编码字符串
>
> **批次5 已完成摘要（2026-07-02）**：
> - 处理 3 个用户内容页面，新增 3 个命名空间：`userContent` / `userAssessments` / `userAssessmentDetail`
> - 关键设计：
>   - UserContentPage：`contentTypeLabel` 由硬编码对象重构为 `CONTENT_TYPE_LABEL_KEYS` 映射表 + 运行时 `t()` 翻译；`durationMinutes` / `viewCount` / `recommendReason` 使用插值参数
>   - UserContentPage：3 个 Tab（内容浏览/我的收藏/推荐内容）的 `el-tab-pane` label、筛选器 `el-form-item` label、`el-option` label、`StatefulContainer` empty-text、卡片收藏按钮文案、对话框标题 fallback 和 footer 按钮全部 i18n 化
>   - UserContentPage：对话框关闭按钮复用 `common.close`；6 个 `showHttpFeedback` fallback 消息和 2 个 `ElMessage.success` 消息全部 i18n 化
>   - UserAssessmentsPage：表格 7 列 label（ID/类型/得分/风险等级/摘要/时间/操作）全部使用 `:label="t('userAssessments.col*')"` 绑定
>   - UserAssessmentsPage：`el-date-picker` 的 `range-separator` / `start-placeholder` / `end-placeholder` 改为 `:` 前缀绑定 `t()` 调用
>   - UserAssessmentsPage：`ActionColumn` 的 label / disabled-reason / `normalizeHttpError` fallback / `ElMessage.success/error` 全部 i18n 化
>   - UserAssessmentDetailPage：`assessmentTypeLabel` 由硬编码对象重构为 `ASSESSMENT_TYPE_LABEL_KEYS` 映射表，含 `typeRecord`（'记录'）独有键（其他命名空间无此类型）
>   - UserAssessmentDetailPage：7 个 `el-descriptions-item` label（记录ID/评估类型/得分/风险等级/时间/摘要/详情）、原始数据标题、返回列表按钮、`normalizeHttpError` fallback 全部 i18n 化
> - 测试结果：i18n 键结构 35/35 通过，TypeScript 0 errors，全量回归 1027/1027 通过（66 个测试文件，4 skipped）
> - 硬编码残留：3 个文件中所有剩余中文均为代码注释（HTML/CSS/JS），无面向用户的硬编码字符串
>
> **批次6 已完成摘要（2026-07-02）**：
> - 处理 1 个文件（UserRiskPage.vue 完整化），扩展 1 个命名空间：`userRisk`（新增 ~42 个键）
> - 关键设计：
>   - P0 已建立独立的 `crisis.*` 命名空间用于危机热线弹窗（dialogTitle / detectedTitle / detectedSubtitle / seekHelp / hotlines.* / contactNearby / acknowledge），本轮保留不动
>   - 本轮为 `userRisk` 命名空间新增 6 个 tab 标签键（tabReport / tabStructured / tabText / tabFusion / tabExperiment / tabPhysiological）
>   - 融合预测表单：3 个 `el-form-item` label（fusionTextLabel / fusionFeaturesLabel / fusionPhysiologicalLabel）+ 3 个 `:placeholder` 绑定 + 1 个按钮文本（btnFusion）全部 i18n 化
>   - 融合结果卡片：标题（fusionResultTitle）、2 个 tag 文本（fusionCrisisOverride / fusionReviewRequired）、4 个子标题 label（fusionScoreLabel / fusionSeverityLabel / fusionModelVersionLabel / fusionModelNameLabel）、8 个 `el-descriptions-item` label（labelReviewStatus / labelCrisisOverride / labelReviewReason / labelInterventionLevel / labelGateWeights / labelModalityScores / labelWeightsInfo / labelModelName / labelModelVersion）全部 i18n 化
>   - `notAvailable`（'暂无'）作为 6 处空值的回退文案：`fusionResult.model_version || t('userRisk.notAvailable')` 等
>   - 导出消息使用插值：`t('userRisk.exportSuccess', { format: format.toUpperCase() })` / `t('userRisk.exportFailed', { format: format.toUpperCase() })`
>   - 融合成功/失败消息使用条件三元：`auto ? t('userRisk.fusionAutoSuccess') : t('userRisk.fusionSuccess')` / `auto ? t('userRisk.fusionAutoFailed') : t('userRisk.fusionFailed')`
>   - `normalizeHttpError` 的 fallback 消息 i18n 化（reportLoadFailed）
>   - `console.warn('风险趋势接口调用失败，使用空趋势图占位', error)` 保留硬编码（开发者调试日志，按约定 3.6 不翻译）
>   - `severityFromLevel` / `formatArrayText`（来自 `@/utils/riskFormatters`）已在 P1 完成 i18n 化，本轮无需修改其调用
> - 测试结果：i18n 键结构 35/35 通过，TypeScript 0 errors，全量回归 1027/1031 通过（66 个测试文件，4 skipped；含 UserRiskPage.structured 7 / experiment 6 / report 4 / physio 5 / text 5 共 27 个 UserRiskPage 测试）
> - 硬编码残留：1 个文件中剩余 12 处中文均为代码注释（HTML/CSS/JS）和 1 处 `console.warn` 开发者调试日志，无面向用户的硬编码字符串
>
> **批次7 已完成摘要（2026-07-02）**：
> - 处理 5 个评估 Tab 组件文件，新增 5 个命名空间：`textAssess` / `experimentAssess` / `riskReport` / `physioAssess` / `structuredAssess`（共 ~180 个键）
> - 关键设计：
>   - StructuredAssessTab（本批次最复杂，~70 键）：
>     - 表单卡片标题、模式切换（单页/分步）、提交/重置按钮、4 个 step 标题、上一步/下一步按钮、结果卡片（路由信息、模型概览 9 个 descriptions、业务概览）、历史表格 5 列全部 i18n 化
>     - `structuredRules` 中 15 条校验规则 message 全部使用 `t()` 调用（如 `ruleIdentityType` / `ruleAge` / `ruleIdentityType` 等）
>     - CSV 导出表头使用 `t('structuredAssess.csvHeader*')` 调用
>     - 6+ 个 `ElMessage` 调用、`normalizeHttpError` fallback 全部 i18n 化
>     - 新增 `notAvailable: '暂无'` 键用于 `model_version` 空值回退
>     - `console.warn('结构化模型预测接口调用失败，继续保存评估结果', error)` 保留硬编码（按约定 3.6）
>   - TextAssessTab（~20 键）：
>     - 记录类型、情绪标签选项、文本输入框 placeholder、按钮文案、历史区域标题全部 i18n 化
>     - `ElMessage` 调用（historyCleared / noHistoryToExport / historyCsvExported / analyzeSuccess / predictSuccess）和 `normalizeHttpError` fallback（analyzeFailed / predictFailed）全部 i18n 化
>     - CSV 表头混合处理：中文表头（时间 / 文本片段）i18n 化，英文技术名称（`prediction(0/1)` / `probability(%)` / `sentiment_label` / `sentiment_score` / `model_used`）保留不翻译（按约定 3.6）
>   - ExperimentTab（~25 键）：
>     - 面板标题、5 个表单 label、2 个数据源选项、4 个按钮文案、模板卡片（标题/告警/路径/列表项）全部 i18n 化
>     - `experimentActionLabel` computed 使用映射表（import/train/evaluate/compare → `t('experimentAssess.action*')`），未知值回退到 `actionDefault`
>     - 进度标签使用插值：`t('experimentAssess.progressLabel', { action: experimentActionLabel })`
>     - 8 个 `ElMessage` 调用和 4 个 `normalizeHttpError` fallback 全部 i18n 化
>     - 品牌名 "HuggingFace Trainer"、"BERT" 和路径 `bert_training_template.csv` 保留不翻译（按约定 3.6）
>   - RiskReportTab（~35 键）：
>     - 骨架屏/错误状态/正常报告三种状态下的所有文案（标题、分数标签、严重程度、趋势、导出按钮、空状态）全部 i18n 化
>     - **`severityLabel` 命名冲突解决**：原本地 `severityLabel` computed 与 `@/utils/riskFormatters` 导出的 `severityLabel` 函数同名。解决方式：导入全局函数并重命名本地 computed 为 `severityLabelText`，复用 P1 已建立的 `riskFormatter.severity.*` 命名空间（避免重复定义）
>     - ECharts 图表内部标签全部 i18n 化：
>       - `sourceLabelMap`（fusion/structured/text/physiological → `t('riskReport.source*')`）用于 legend data 和 series name
>       - `riskLevelMap`（0-4 → `t('riskReport.chartRiskLevel*')`）用于 tooltip 标签
>       - graphic text、tooltip HTML 字符串中所有标签均通过 `t()` 渲染
>     - `notAvailable` 用于空值回退（如 `report.main_factors` 为空时）
>   - PhysioTab（~30 键）：
>     - 表单标题、数据来源选项、各字段 label 和 placeholder、合理性提示、提交按钮、历史区域、清空/导出按钮全部 i18n 化
>     - `physioRules` 校验 message 全部使用 `t()` 调用
>     - CSV 导出表头使用 `t('physioAssess.csvHeader*')` 调用
>     - `ElMessage` 调用和 `normalizeHttpError` fallback 全部 i18n 化
>   - 测试文件修改（5 个 .test.ts 文件）：
>     - 所有 5 个 Tab 组件测试文件添加 `import i18n from '@/i18n'` 和 `plugins: [i18n]` 到 mountOptions
>     - 原因：组件现在使用 `useI18n()`，需要 i18n 插件安装到 Vue 实例，否则报 "Need to install with `app.use` function" 错误
>     - PhysioTab/TextAssessTab/StructuredAssessTab 测试：在已有 `mountOptions.global` 中添加 `plugins: [i18n]`
>     - ExperimentTab/RiskReportTab 测试：新建 `mountOptions` 含 `plugins: [i18n]`，更新所有 `mount()` 调用
> - 测试结果：
>   - i18n 键结构 35/35 通过
>   - TypeScript 0 errors
>   - 5 个 Tab 组件针对性回归 35/35 通过
>   - 全量回归 1027/1031 通过（66 个测试文件，4 skipped）
> - 硬编码残留：5 个文件中剩余中文均为代码注释（HTML/CSS/JS）和开发者调试日志（如 `console.warn`），无面向用户的硬编码字符串
> - 累计进度：37/~55 文件，~1544/~1749 硬编码字符串已迁移（实际超过初始估算，因子组件复杂度高于预估）
>
> **批次8 已完成摘要（2026-07-02）**：
> - 处理 4 个 structured-steps 组件文件，复用 `structuredAssess` 命名空间（批次7 已建立），新增 26 个键
> - 关键设计：
>   - **复用命名空间**：4 个 Step 组件均为结构化评估的分步表单，与 StructuredAssessTab 紧密相关，故复用 `structuredAssess` 命名空间而非新建独立命名空间
>   - **键命名规范**：
>     - 字段 label 使用 `field*` 前缀（如 `fieldIdentityType` / `fieldAge` / `fieldCgpa` / `fieldStressLevel`）
>     - 选项文本使用 `option*` 前缀（如 `optionStudent` / `optionMale` / `optionNone` / `optionHave`）
>     - 滑块单位使用 `sliderValue*` 前缀（如 `sliderValueCgpa` / `sliderValuePressure` / `sliderValueSleep` / `sliderValueExercise` / `sliderValueSupport`）
>   - **滑块单位插值化**：原硬编码的 `{{ form.cgpa.toFixed(1) }} / 10` / `{{ form.sleep_duration }} 小时` / `{{ form.exercise_frequency }} 次/周` 等改为插值键 `t('structuredAssess.sliderValueCgpa', { value: form.cgpa.toFixed(1) })`，支持多语言单位文案
>   - **选项语义区分**：
>     - `optionNone`（'无'）和 `optionHave`（'有'）用于 family_history / panic_attack（"有/无"语义）
>     - 复用已有 `yesOption`（'是'）和 `noOption`（'否'）用于 treatment_seeking（"是/否"语义）
>     - 避免将"有/无"与"是/否"混用，保持语义准确性
>   - **GPA 保留英文**：`fieldCgpa: 'GPA'` 为英文缩写，按约定 3.6 保留不翻译（en-US 也是 'GPA'）
>   - **sliderValuePressure 复用**：AcademicStep 的 academic_pressure/financial_pressure 和 MentalHealthStep 的 stress_level/anxiety 都使用 0-5 范围，复用同一 `sliderValuePressure` 键（`'{value} / 5'`）
>   - 无对应测试文件，无需修改测试
> - 测试结果：
>   - i18n 键结构 35/35 通过
>   - TypeScript 0 errors
>   - 全量回归 1027/1031 通过（66 个测试文件，4 skipped）
> - 硬编码残留：4 个文件中剩余中文均为代码注释（CSS），无面向用户的硬编码字符串
> - 累计进度：41/~55 文件，~1573/~1748 硬编码字符串已迁移
>
> **批次9 已完成摘要（2026-07-02）**：
> - 处理 6 个 experiment-charts 组件文件，复用 `experimentAssess` 命名空间（批次7 已建立），新增 28 个键
> - 关键设计：
>   - **复用命名空间**：6 个图表组件均为实验对比的子组件，与 ExperimentTab 紧密相关，故复用 `experimentAssess` 命名空间而非新建独立命名空间
>   - **EvalResultCard（~15 处）**：
>     - 卡片标题、复制按钮、4 个 `el-descriptions-item` label（训练损失/验证损失/验证准确率/模型状态）、2 个日志查看器标题、过滤 placeholder、复制日志按钮、样本数列标签全部 i18n 化
>     - `ElMessage.success` / `ElMessage.error` 的复制结果消息 i18n 化
>     - 表格列标签保留英文技术术语：Epoch / Loss / Eval Loss / Eval F1 / Eval Acc / LR / Split / Acc / Prec / Recall / F1 / AUC（按约定 3.6 不翻译）
>   - **4 个图表组件（AccuracyChart/LossChart/ConfusionChart/CompareChart）**：
>     - 仅卡片标题需要 i18n 化（`accuracyChartTitle` / `lossChartTitle` / `confusionChartTitle` / `compareChartTitle`）
>     - ECharts 配置中的 `xAxis.data`（`E${i+1}`）、`yAxis.data`（`Pred 0` / `Pred 1` / `True 0` / `True 1`）、`legend.data`（COMPARE_METRICS 英文指标名）均为技术标识符，保留不翻译
>   - **MisclassifiedTable（~12 处）**：
>     - 卡片标题、3 个 select placeholder、搜索框 placeholder、导出按钮、3 个表格列标签全部 i18n 化
>     - **插值键设计**：`trueLabelOption`（'真实 {value}'）/ `predLabelOption`（'预测 {value}'）使用插值参数，避免重复定义 `trueLabel0` / `trueLabel1` / `predLabel0` / `predLabel1` 四个键
>     - 概率区间 option label（`0.0 - 0.3` 等）为数字范围，保留不翻译
>     - CSV 表头 `index,true_label,pred_label,score` 为技术字段名，保留不翻译
>   - 无对应测试文件，无需修改测试
> - 测试结果：
>   - i18n 键结构 35/35 通过
>   - TypeScript 0 errors
>   - 全量回归 1027/1031 通过（66 个测试文件，4 skipped）
> - 硬编码残留：6 个文件中剩余中文均为代码注释（CSS），无面向用户的硬编码字符串
> - 累计进度：47/~55 文件，~1604/~1749 硬编码字符串已迁移
>
> **批次10 已完成摘要（2026-07-03）**：
> - 处理 4 个公共图表组件，新建 1 个命名空间：`charts`（16 个键）
> - 关键设计：
>   - **复用命名空间**：4 个图表组件共享 `charts.*` 命名空间，避免每个组件重复定义 `saveImage` / `zoomIn` / `zoomReset` 等通用键
>   - **默认 prop 与 useI18n() 冲突解决**：`withDefaults` 在模块级执行，无法访问 `useI18n()` 返回的 `t`。解决方式：将默认值改为 `undefined`，新增 `computed` 在 setup 内进行回退：`const effectiveTitle = computed(() => props.title ?? t('charts.systemHealthTitle'))`
>   - **BaseChart（~1 处）**：仅 `aria-label` 默认值需要 i18n 化（`baseAriaLabel`），通过 computed 回退实现
>   - **SystemHealthChart（~9 处）**：标题、2 个 yAxis 名称（成功率/延迟 ms）、3 个 series 名称（成功率/回退率/延迟）、toolbox saveImage、2 个 dataZoom 标题全部 i18n 化
>   - **RiskTrendChart（~7 处）**：标题、3 个 series 名称（风险值/上限/下限）、复用 `charts.saveImage` / `charts.zoomIn` / `charts.zoomReset`
>   - **ModelPerformanceChart（~2 处）**：仅标题和 saveImage 需要本地化；系列名 Accuracy / Precision / Recall / F1 / AUC 为英文技术术语，按约定 3.6 保留不翻译
>   - 无对应测试文件，无需修改测试
> - 测试结果：
>   - i18n 键结构 35/35 通过
>   - TypeScript 0 errors
>   - 全量回归 1027/1031 通过（66 个测试文件，4 skipped）
> - 硬编码残留：4 个文件中剩余中文均为代码注释，无面向用户的硬编码字符串
> - 累计进度：51/~55 文件，~1623/~1749 硬编码字符串已迁移
>
> **批次11 已完成摘要（2026-07-03）**：
> - 处理 1 个 Vue 根组件 + 5 个 .ts 工具文件，扩展 1 个命名空间（`errorPolicy.*` +3 键），新建 3 个命名空间（`webSocket.*` / `serviceWorker.*` / `exportUtils.*` / `formatUtils.*`）
> - 关键设计：
>   - **App.vue 排查**：仅含代码注释，无用户可见硬编码，无需改动
>   - **工具文件 i18n 模式**：`import i18n from '@/i18n'` → `const t = i18n.global.t.bind(i18n.global)`（模块级，非 `useI18n()`）
>   - **request.ts（~8 处）**：
>     - `redirectToLogin(message = t('errorPolicy.loginExpired'))` — 默认参数在调用时求值，可使用 `t()`
>     - `reject(new Error(t('errorPolicy.tokenRefreshTimeout')))` — Promise reject 错误消息
>     - 6 处 `ElMessage.warning/error(detail || '中文')` 替换为 `t('errorPolicy.*')` 调用
>     - 复用 `errorPolicy.*` 已有键（noPermission / notFound / validationFailed / serverError），新增 3 个键（loginExpired / tokenRefreshTimeout / requestFailed）以保留原文案，避免破坏 test 断言
>   - **useWebSocket.ts（~2 处）**：`ElNotification` 标题和消息 i18n 化；`captureMessage('WebSocket 重连失败：...')` 为 Sentry 开发者日志，按约定 3.6 保留
>   - **serviceWorker.ts（~2 处）**：PWA 更新 `ElNotification` 标题和消息 i18n 化；`console.log/error` 保留为开发者日志
>   - **exportUtils.ts（~2 处）**：2 处 `throw new Error('导出数据为空')` 替换为 `throw new Error(t('exportUtils.emptyData'))`
>   - **formatUtils.ts（~6 处）**：`formatRelativeTime` 6 个分支返回值全部 i18n 化，使用插值键（如 `t('formatUtils.minutesAgo', { count: minutes })`）
>   - **37 个 .ts 文件全量排查**：29 个文件仅含注释/console/类型定义/英文内容，确认无需迁移；3 个文件跳过（contracts.ts 开发者断言 / business.ts mock 数据 / sharedStepUtils.ts 死代码）
>   - **测试兼容性**：i18n 实例在 `index.ts` 同步加载 zh-CN messages，`t()` 在测试环境返回中文，与原有断言兼容，无需修改测试
> - 测试结果：
>   - i18n 键结构 35/35 通过
>   - TypeScript 0 errors
>   - 全量回归 1027/1031 通过（66 个测试文件，4 skipped）
> - 硬编码残留：5 个文件中剩余中文均为代码注释、Sentry captureMessage、console 日志，无面向用户的硬编码字符串
> - 累计进度：51 个 .vue 文件 + 10 个 .ts 工具文件，~1640 处硬编码字符串已迁移（全部完成）
>
> **i18n 迁移项目最终验收（2026-07-03）**：
> - ✅ 全部 11 个批次完成（P0 + P1 + P2-6/7/8 + P2-9 批次1~11）
> - ✅ 51 个 .vue 文件 + 10 个 .ts 工具文件迁移完毕
> - ✅ ~1640 处硬编码字符串全部替换为 `t()` 调用
> - ✅ TypeScript 类型检查通过（exit code 0）
> - ✅ 全量回归测试 1027/1031 通过（66 个测试文件，4 skipped）
> - ✅ i18n 键结构一致性测试 35/35 通过（zh-CN.ts 与 en-US.ts 完全对齐）
> - ✅ 28 个顶层命名空间建立，覆盖所有业务模块
> - ✅ 无面向用户的硬编码中文字符串残留（剩余中文均为代码注释、Sentry 日志、console 调试日志、英文技术术语保留项）
