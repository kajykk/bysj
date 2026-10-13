# P2-32 SSOT 重复现状全仓审计清单

- 生成时间：2026-10-13 11:30 UTC
- 方法：机制扫描（AST / 正则判据），不靠目测。判定「真重复」的标准是
  **内容集合完全相同**（可 re-export），仅「有重叠词」不算重复 ——
  `crisis_detector` 与 `config.crisis_keywords` 有交集但职责不同
  （前者是 6 分类危机分类器，后者是布尔命中词表），不能合并。

## 本轮改动前后对照

| 类目 | 改前 | 改后 | 处置 |
|---|---|---|---|
| Blob 下载 | 14 处链路 / 2 种变体（**4 处同步 revoke**） | **1 处 / 1 种变体** | 建 `exportUtils.downloadBlob()` SSOT，11 处改调|
| 危机词表 | 5 处 / **1 组字面完全相同** | 4 处 / 0 组 | 删除 `inference.CRISIS_KEYWORDS`（实测无生产消费点的死副本）|

剩余类目（风险等级 / 文件名清洗 / CSV 转义 / 角色 / 模型元数据）本轮**只审计不改**，
理由见各类目结论与文末局限说明。

## 汇总

| 类目 | 结论 |
|---|---|
| 危机词表 | 4 处定义 / 4 种内容；0 组完全相同 |
| 风险等级标签 | 4 处等级集合定义 / 4 种词表 |
| 文件名清洗 | 12 处（清洗定义 + Content-Disposition 使用点） |
| CSV 转义 | 33 处引用 / 4 处绕过 SSOT |
| Blob 下载 | 1 处下载链路 / 1 种变体 |
| 角色定义 | 57 处 |
| 模型元数据 | 145 处引用 |

## 危机词表（`crisis_keywords`）

**结论**：4 处定义 / 4 种内容；0 组完全相同

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `app/core/config.py:514` | 10 词：想死, 自杀, 自残, 活不下去, 不想活, 结束生命… | `crisis_keywords: list[str] = [` |
| `app/core/crisis_detector.py:17` | 58 词：suicide, self_harm, despair, internet_slang, planning, help_seeking… | `CRISIS_KEYWORDS: dict[str, list[str]] = {` |
| `app/models/review.py:136` | 1 词：[]… | `crisis_keywords: Mapped[str \| None] = mapped_column(` |
| `app/schemas/model_predict.py:49` | 1 词：命中的危机关键词… | `crisis_keywords: list[str] = Field(` |

## 风险等级标签（`risk_levels`）

**结论**：4 处等级集合定义 / 4 种词表

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `app/core/contracts.py:37` | RISK_LEVEL_MAP：['critical', 'high', 'low', 'medium', 'none'] | `RISK_LEVEL_MAP: dict[int, str] = {` |
| `app/core/contracts.py:50` | RISK_LEVEL_DISPLAY_ZH：['critical', 'high', 'low', 'medium', 'none', 'unknown'] | `RISK_LEVEL_DISPLAY_ZH: dict[str, str] = {` |
| `app/core/risk_thresholds.py:8` | RISK_LEVEL_THRESHOLDS：['critical', 'high', 'mild', 'moderate'] | `RISK_LEVEL_THRESHOLDS: dict[str, int] = {` |
| `app/core/risk_thresholds.py:42` | RISK_LEVEL_LABELS：['critical', 'high', 'mild', 'moderate', 'none'] | `RISK_LEVEL_LABELS: dict[int, str] = {` |

## 文件名清洗（`filename_sanitize`）

**结论**：12 处（清洗定义 + Content-Disposition 使用点）

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `app/api/v1/admin.py:42` | 清洗实现定义处 | `def _sanitize_filename(name: str) -> str:` |
| `app/api/v1/gdpr.py:182` | Content-Disposition 使用点：**行内无清洗痕迹** | `"Content-Disposition": f'attachment; filename="my_data_{current_user.id}.json"',` |
| `app/api/v1/gdpr.py:295` | Content-Disposition 使用点：**行内无清洗痕迹** | `"Content-Disposition": f'attachment; filename="user_{user_id}_data_{export_id[:8]}.json"',` |
| `app/api/v1/reports.py:110` | Content-Disposition 使用点：行内见清洗痕迹 | `"Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",` |
| `app/api/v1/reports.py:141` | 清洗实现定义处 | `def _safe_export_filename(raw_name: str \| None) -> str:` |
| `app/api/v1/reports.py:266` | Content-Disposition 使用点：行内见清洗痕迹 | `"Content-Disposition": f"attachment; filename={safe_name}.xlsx",` |
| `app/api/v1/reports.py:300` | Content-Disposition 使用点：行内见清洗痕迹 | `"Content-Disposition": f"attachment; filename={safe_name}.xlsx",` |
| `app/api/v1/reports.py:482` | Content-Disposition 使用点：行内见清洗痕迹 | `"Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",` |
| `app/api/v1/uploads.py:58` | 清洗实现定义处 | `_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,8}$")` |
| `app/api/v1/user_risk.py:24` | 清洗实现定义处 | `def _sanitize_filename(name: str) -> str:` |
| `app/api/v1/user_risk.py:96` | Content-Disposition 使用点：行内见清洗痕迹 | `"Content-Disposition": f'attachment; filename="{_sanitize_filename(data["filename"])}"'` |
| `app/api/v1/user_risk.py:106` | Content-Disposition 使用点：行内见清洗痕迹 | `"Content-Disposition": f'attachment; filename="{_sanitize_filename(data["filename"])}"'` |

## CSV 转义（`csv_escape`）

**结论**：33 处引用 / 4 处绕过 SSOT

- 绕过 SSOT 的重复点：4 处（测试文件不计入）

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `src/utils/exportUtils.test.ts:30` | 测试断言/期望值（非重复点） | `return `"${String(value ?? '').replace(/"/g, '""')}"`` |
| `src/utils/exportUtils.test.ts:122` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('')).toBe('')` |
| `src/utils/exportUtils.test.ts:126` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('hello')).toBe('hello')` |
| `src/utils/exportUtils.test.ts:127` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('123')).toBe('123')` |
| `src/utils/exportUtils.test.ts:131` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('=SUM(A1)')).toBe("'=SUM(A1)")` |
| `src/utils/exportUtils.test.ts:135` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('+1+1')).toBe("'+1+1")` |
| `src/utils/exportUtils.test.ts:139` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('@admin')).toBe("'@admin")` |
| `src/utils/exportUtils.test.ts:143` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('\tdata')).toBe("'\tdata")` |
| `src/utils/exportUtils.test.ts:147` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('\rdata')).toBe("'\rdata")` |
| `src/utils/exportUtils.test.ts:151` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('-123')).toBe('-123')` |
| `src/utils/exportUtils.test.ts:152` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('-3.14')).toBe('-3.14')` |
| `src/utils/exportUtils.test.ts:153` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('-1e5')).toBe('-1e5')` |
| `src/utils/exportUtils.test.ts:154` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('-.5')).toBe('-.5')` |
| `src/utils/exportUtils.test.ts:158` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('-abc')).toBe("'-abc")` |
| `src/utils/exportUtils.test.ts:159` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('- 12abc')).toBe("'- 12abc")` |
| `src/utils/exportUtils.test.ts:646` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('   ')).toBe('   ')` |
| `src/utils/exportUtils.test.ts:650` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('0')).toBe('0')` |
| `src/utils/exportUtils.test.ts:651` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('3.14159')).toBe('3.14159')` |
| `src/utils/exportUtils.test.ts:655` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('1e10')).toBe('1e10')` |
| `src/utils/exportUtils.test.ts:656` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('1.5e-3')).toBe('1.5e-3')` |
| `src/utils/exportUtils.test.ts:660` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('- abc')).toBe("'- abc")` |
| `src/utils/exportUtils.test.ts:667` | 测试断言/期望值（非重复点） | `expect(sanitizeCellForExcel('-')).toBe('-')` |
| `src/utils/exportUtils.ts:18` | **转义规则定义**（SSOT 本体） | `export function sanitizeCellForExcel(value: string): string {` |
| `src/utils/exportUtils.ts:20` | **转义规则定义**（SSOT 本体） | `const dangerousPrefixes = ['=', '+', '@', '\t', '\r']` |
| `src/utils/exportUtils.ts:43` | SSOT 内部调用 | `const sanitized = sanitizeCellForExcel(value)` |
| `src/utils/exportUtils.ts:44` | SSOT 内部调用 | `return `"${sanitized.replace(/"/g, '""')}"`` |
| `src/utils/exportUtils.ts:115` | SSOT 内部调用 | `.map((col) => `<th>${escapeXml(sanitizeCellForExcel(col.label))}</th>`)` |
| `src/utils/exportUtils.ts:126` | SSOT 内部调用 | `const sanitized = sanitizeCellForExcel(String(value ?? ''))` |
| `src/views/admin/AdminOperationLogsPage.test.ts:53` | 测试断言/期望值（非重复点） | `].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))` |
| `src/views/user/components/PhysioTab.vue:314` | **内联重复转义链**（绕过 SSOT） | `.map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))` |
| `src/views/user/components/composables/useTextPredictionHistory.ts:130` | **内联重复转义链**（绕过 SSOT） | `.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`)` |
| `src/views/user/components/experiment-charts/MisclassifiedTable.vue:157` | **内联重复转义链**（绕过 SSOT） | `const csvEscape = (value: string \| number) => `"${String(value).replace(/"/g, '""')}"`` |
| `src/views/user/components/structured-steps/usePredictionHistory.ts:74` | **内联重复转义链**（绕过 SSOT） | `.map((line) => line.map((cell) => `"${sanitizeCellForExcel(String(cell)).replace(/"/g, '""')}"`).join(','))` |

## Blob 下载（`blob_download`）

**结论**：1 处下载链路 / 1 种变体

- 延迟 revoke（setTimeout）：1 处

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `src/utils/exportUtils.ts:65` | 延迟 revoke（setTimeout）（SSOT 本体） | `const link = document.createElement('a')` |

## 角色定义（`roles`）

**结论**：57 处

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `app/api/v1/counselor.py:29` | **裸字面量角色**（未走常量） | `router = APIRouter(prefix="/counselor", tags=["counselor"])` |
| `app/api/v1/counselor.py:36` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:53` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:71` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:113` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:134` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:185` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:210` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:251` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:275` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:321` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:352` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:369` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:389` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:415` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/counselor.py:429` | **裸字面量角色**（未走常量） | `current_user: Annotated[User, Depends(require_role("counselor"))],` |
| `app/api/v1/review.py:94` | **裸字面量角色**（未走常量） | `assigned_to = current_user.id if current_user.role == "counselor" else None` |
| `app/api/v1/review.py:302` | **裸字面量角色**（未走常量） | `if current_user.role == "counselor":` |
| `app/api/v1/review.py:341` | **裸字面量角色**（未走常量） | `if current_user.role == "counselor" and task.assigned_to != current_user.id:` |
| `app/api/v1/review.py:424` | **裸字面量角色**（未走常量） | `if current_user.role == "counselor" and task.assigned_to != current_user.id:` |
| `app/api/v1/review.py:461` | **裸字面量角色**（未走常量） | `if current_user.role == "counselor" and task.assigned_to != current_user.id:` |
| `app/core/contracts.py:101` | 后端角色常量定义 | `USER_ROLE_SUPER_ADMIN = "super_admin"` |
| `app/core/contracts.py:102` | 后端角色常量定义 | `USER_ROLE_ADMIN = "admin"` |
| `app/core/contracts.py:103` | 后端角色常量定义 | `USER_ROLE_COUNSELOR = "counselor"` |
| `app/core/contracts.py:104` | 后端角色常量定义 | `USER_ROLE_USER = "user"` |
| `app/core/deps.py:27` | 后端角色常量定义 | `ROLE_HIERARCHY: dict[str, set[str]] = {` |
| `app/core/deps.py:28` | 后端角色常量定义 | `USER_ROLE_SUPER_ADMIN: {` |
| `app/core/deps.py:34` | 后端角色常量定义 | `USER_ROLE_ADMIN: {USER_ROLE_ADMIN, USER_ROLE_COUNSELOR, USER_ROLE_USER},` |
| `app/core/deps.py:35` | 后端角色常量定义 | `USER_ROLE_COUNSELOR: {USER_ROLE_COUNSELOR},` |
| `app/core/deps.py:36` | 后端角色常量定义 | `USER_ROLE_USER: {USER_ROLE_USER},` |
| `app/core/deps.py:40` | 后端角色常量定义 | `USER_ROLE_USER: {` |
| `app/core/deps.py:51` | 后端角色常量定义 | `USER_ROLE_COUNSELOR: {` |
| `app/core/seed.py:605` | **裸字面量角色**（未走常量） | `"role": "counselor",` |
| `app/core/seed.py:808` | **裸字面量角色**（未走常量） | `(await db.execute(select(User).where(User.role == "counselor"))).scalars().all()` |
| `app/services/admin_service_log.py:137` | **裸字面量角色**（未走常量） | `.filter(OperationLog.operator_role == "counselor")` |
| `app/services/admin_service_log.py:138` | **裸字面量角色**（未走常量） | `.label("counselor"),` |
| `app/services/admin_service_log.py:141` | **裸字面量角色**（未走常量） | `.filter(OperationLog.operator_role == "super_admin")` |
| `app/services/admin_service_log.py:142` | **裸字面量角色**（未走常量） | `.label("super_admin"),` |
| `app/services/admin_service_log.py:148` | **裸字面量角色**（未走常量） | `"counselor": int(row.counselor or 0),` |
| `app/services/admin_service_log.py:150` | **裸字面量角色**（未走常量） | `"super_admin": int(row.super_admin or 0),` |
| `app/services/admin_service_stats.py:48` | **裸字面量角色**（未走常量） | `.where(User.role == "counselor")` |
| `app/services/anomaly_detection_service.py:90` | **裸字面量角色**（未走常量） | `"counselor": 7,` |
| `app/services/anomaly_detection_service.py:323` | **裸字面量角色**（未走常量） | `OperationLog.operator_role.in_(["admin", "counselor"]),` |
| `app/services/counselor_service_binding.py:70` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_binding.py:84` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_binding.py:131` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_binding.py:147` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_binding.py:211` | **裸字面量角色**（未走常量） | `or counselor.role != "counselor"` |
| `app/services/counselor_service_consultation.py:61` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_consultation.py:105` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_group.py:41` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_group.py:144` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_user.py:35` | **裸字面量角色**（未走常量） | `counselor_id 过滤，**没有任何租户条件**。路由层的 ``require_role("counselor")``` |
| `app/services/counselor_service_warning.py:170` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/counselor_service_warning.py:231` | **裸字面量角色**（未走常量） | `operator_role="counselor",` |
| `app/services/review_service.py:320` | **裸字面量角色**（未走常量） | `operator_role="admin" if is_admin else "counselor",` |
| `src/views/counselor/CounselorReviewListPage.vue:285` | 前端角色判定函数 | `const isAdmin = computed(() => auth.role === 'admin' \|\| auth.role === 'super_admin')` |

## 模型元数据（`model_meta`）

**结论**：145 处引用

| 位置 | 说明 | 证据（源码行） |
|---|---|---|
| `backend/app/api/v1/metrics_helpers.py:202` | 模型元数据引用 | `# model_version 标签用真实产物所在目录名，避免声称一个无法追溯的版本号` |
| `backend/app/api/v1/metrics_helpers.py:209` | 模型元数据引用 | `gauge.set(float(value), modality=modality, model_version=version)` |
| `backend/app/api/v1/monitoring.py:95` | 模型元数据引用 | `model_version: Annotated[str \| None, Query(description="模型版本过滤")] = None,` |
| `backend/app/api/v1/monitoring.py:138` | 模型元数据引用 | `if model_version:` |
| `backend/app/api/v1/monitoring.py:139` | 模型元数据引用 | `stmt = stmt.where(MonitoringLog.model_version == model_version)` |
| `backend/app/api/v1/monitoring.py:166` | 模型元数据引用 | `model_version: Annotated[str \| None, Query(description="模型版本过滤")] = None,` |
| `backend/app/api/v1/monitoring.py:197` | 模型元数据引用 | `if model_version:` |
| `backend/app/api/v1/monitoring.py:198` | 模型元数据引用 | `stmt = stmt.where(MonitoringLog.model_version == model_version)` |
| `backend/app/api/v1/monitoring.py:228` | 模型元数据引用 | `model_version: Annotated[str \| None, Query(description="模型版本过滤")] = None,` |
| `backend/app/api/v1/monitoring.py:244` | 模型元数据引用 | `if model_version:` |
| `backend/app/api/v1/monitoring.py:245` | 模型元数据引用 | `stmt = stmt.where(DriftAlert.model_version == model_version)` |
| `backend/app/api/v1/monitoring.py:266` | 模型元数据引用 | `"model_version": alert.model_version,` |
| `backend/app/api/v1/monitoring.py:378` | 模型元数据引用 | `model_version=log.model_version,` |
| `backend/app/api/v1/monitoring.py:411` | 模型元数据引用 | `model_version: Annotated[str \| None, Query(description="模型版本过滤")] = None,` |
| `backend/app/api/v1/monitoring.py:422` | 模型元数据引用 | `if model_version:` |
| `backend/app/api/v1/monitoring.py:423` | 模型元数据引用 | `stmt = stmt.where(MonitoringLog.model_version == model_version)` |
| `backend/app/api/v1/monitoring.py:445` | 模型元数据引用 | `"model_version": log.model_version,` |
| `backend/app/api/v1/validation.py:376` | 模型元数据引用 | `"model_version": payload.model_version,` |
| `backend/app/api/v1/validation.py:407` | 模型元数据引用 | `model_version=payload.model_version,` |
| `backend/app/api/v1/validation.py:433` | 模型元数据引用 | `model_version=job["model_version"],` |
| `backend/app/api/v1/validation.py:484` | 模型元数据引用 | `model_version=job["model_version"],` |
| `backend/app/api/v1/validation.py:531` | 模型元数据引用 | `"model_version": job["model_version"],` |
| `backend/app/core/config.py:478` | 模型元数据引用 | `# 回滚方式: 环境变量 STRUCTURED_DEFAULT_MODEL=v1.20 (无需改代码)。` |
| `backend/app/core/config.py:483` | 模型元数据引用 | `structured_default_model: str = "v1.23"  # "v1.20" \| "v1.23"` |
| `backend/app/core/metrics.py:650` | 模型元数据引用 | `#   model_version: v1.20 / v1.23 / m2_bert / v2_dl / stacking_gbdt 等` |
| `backend/app/core/metrics.py:654` | 模型元数据引用 | `"Model AUC-ROC, labeled by modality and model_version. S4 P3 ML quality metric.",` |
| `backend/app/core/metrics.py:655` | 模型元数据引用 | `labelnames=("modality", "model_version"),` |
| `backend/app/core/metrics.py:660` | 模型元数据引用 | `"Model F1 score, labeled by modality and model_version. S4 P3 ML quality metric.",` |
| `backend/app/core/metrics.py:661` | 模型元数据引用 | `labelnames=("modality", "model_version"),` |
| `backend/app/core/metrics.py:666` | 模型元数据引用 | `"Model Expected Calibration Error (ECE), labeled by modality and model_version. "` |
| `backend/app/core/metrics.py:668` | 模型元数据引用 | `labelnames=("modality", "model_version"),` |
| `backend/app/core/metrics.py:673` | 模型元数据引用 | `"Model inference P95 latency in milliseconds, labeled by modality and model_version. "` |
| `backend/app/core/metrics.py:675` | 模型元数据引用 | `labelnames=("modality", "model_version"),` |
| `backend/app/core/metrics.py:680` | 模型元数据引用 | `"Model high-risk recall, labeled by modality and model_version. S4 P3 G5 metric.",` |
| `backend/app/core/metrics.py:681` | 模型元数据引用 | `labelnames=("modality", "model_version"),` |
| `backend/app/core/metrics.py:686` | 模型元数据引用 | `"Model precision, labeled by modality and model_version. S4 P3 G5 metric.",` |
| `backend/app/core/metrics.py:687` | 模型元数据引用 | `labelnames=("modality", "model_version"),` |
| `backend/app/core/model_engine/__init__.py:112` | 模型元数据引用 | `# S-02: v1.23 external LR (structured_default_model=v1.23 时主路径模型),` |
| `backend/app/core/model_engine/fallback.py:242` | 模型元数据引用 | `"model_version": "v1.25",` |
| `backend/app/core/model_engine/fusion.py:183` | 模型元数据引用 | `"model_version": "v1.16-risk-calibration",` |
| `backend/app/core/model_engine/predict.py:126` | 模型元数据引用 | `"model_version": None,` |
| `backend/app/core/model_engine/predict.py:135` | 模型元数据引用 | `model_version = "v1.20"` |
| `backend/app/core/model_engine/predict.py:145` | 模型元数据引用 | `# S-02: 根据 structured_default_model 配置选择默认结构化模型` |
| `backend/app/core/model_engine/predict.py:148` | 模型元数据引用 | `default_model_version = getattr(settings, "structured_default_model", "v1.20")` |
| `backend/app/core/model_engine/predict.py:149` | 模型元数据引用 | `if default_model_version == "v1.23":` |
| `backend/app/core/model_engine/predict.py:152` | 模型元数据引用 | `primary_model_version = "v1.23"` |
| `backend/app/core/model_engine/predict.py:157` | 模型元数据引用 | `primary_model_version = "v1.20"` |
| `backend/app/core/model_engine/predict.py:165` | 模型元数据引用 | `model_version = primary_model_version` |
| `backend/app/core/model_engine/predict.py:274` | 模型元数据引用 | `"model_version": model_version,` |
| `backend/app/core/model_engine/predict.py:843` | 模型元数据引用 | `"model_version": "v1.25",` |
| `backend/app/core/model_registry.py:192` | 模型元数据引用 | `# 通过 settings.structured_default_model 配置开关选择 v1.20 或 v1.23 作为默认` |
| `backend/app/core/model_registry.py:193` | 模型元数据引用 | `# 金丝雀发布时通过环境变量 STRUCTURED_DEFAULT_MODEL=v1.23 切换` |
| `backend/app/core/model_registry.py:220` | 模型元数据引用 | `"status": "default — candidate model, enable via STRUCTURED_DEFAULT_MODEL=v1.23",` |
| `backend/app/ml/model_monitor.py:42` | 模型元数据引用 | `model_version: str` |
| `backend/app/ml/model_monitor.py:66` | 模型元数据引用 | `model_version: Version of the model.` |
| `backend/app/ml/model_monitor.py:74` | 模型元数据引用 | `model_version: str,` |
| `backend/app/ml/model_monitor.py:80` | 模型元数据引用 | `self.model_version = model_version` |
| `backend/app/ml/model_monitor.py:96` | 模型元数据引用 | `model_version,` |
| `backend/app/ml/model_monitor.py:170` | 模型元数据引用 | `model_version=self.model_version,` |
| `backend/app/ml/model_monitor.py:254` | 模型元数据引用 | `"model_version": self.model_version,` |
| `backend/app/ml/model_monitor.py:286` | 模型元数据引用 | `"model_version": self.model_version,` |
| `backend/app/ml/model_monitor.py:323` | 模型元数据引用 | `model_version=state["model_version"],` |
| `backend/app/ml/model_monitor.py:338` | 模型元数据引用 | `model_version=state["model_version"],` |
| `backend/app/ml/unified_model_interface.py:34` | 模型元数据引用 | `def __init__(self, model_name: str, model_version: str):` |
| `backend/app/ml/unified_model_interface.py:39` | 模型元数据引用 | `model_version: Version string.` |
| `backend/app/ml/unified_model_interface.py:42` | 模型元数据引用 | `self.model_version = model_version` |
| `backend/app/ml/unified_model_interface.py:90` | 模型元数据引用 | `"model_version": self.model_version,` |
| `backend/app/models/monitoring.py:43` | 模型元数据引用 | `model_version: Mapped[str \| None] = mapped_column(` |
| `backend/app/models/monitoring.py:83` | 模型元数据引用 | `Index("ix_monitoring_logs_model_version_created_at", "model_version", "created_at"),` |
| `backend/app/models/monitoring.py:174` | 模型元数据引用 | `model_version: Mapped[str] = mapped_column(` |
| `backend/app/models/monitoring.py:212` | 模型元数据引用 | `Index("ix_validation_results_model_version_created_at", "model_version", "created_at"),` |
| `backend/app/models/monitoring.py:221` | 模型元数据引用 | `model_version: Mapped[str \| None] = mapped_column(` |
| `backend/app/models/monitoring.py:286` | 模型元数据引用 | `Index("ix_drift_alerts_model_version_created_at", "model_version", "created_at"),` |
| `backend/app/schemas/model_predict.py:186` | 模型元数据引用 | `model_version: str \| None = None` |
| `backend/app/schemas/model_predict.py:220` | 模型元数据引用 | `model_version: str = Field(default="v1.16-risk-calibration", description="模型版本")` |
| `backend/app/schemas/monitoring.py:70` | 模型元数据引用 | `model_version: str \| None` |
| `backend/app/schemas/monitoring.py:101` | 模型元数据引用 | `model_version: str \| None` |
| `backend/app/schemas/validation.py:11` | 模型元数据引用 | `model_version: str = Field(..., description="Model version to validate")` |
| `backend/app/schemas/validation.py:27` | 模型元数据引用 | `model_version: str` |
| `backend/app/schemas/validation.py:34` | 模型元数据引用 | `model_version: str` |
| `backend/app/services/alert_lifecycle_service.py:204` | 模型元数据引用 | `model_version=alert.model_version,` |
| `backend/app/services/alert_lifecycle_service.py:257` | 模型元数据引用 | `"model_version": alert.model_version,` |
| `backend/app/services/alert_lifecycle_service.py:346` | 模型元数据引用 | `f"Model: {alert.model_version or 'unknown'}\n"` |
| `backend/app/services/auto_rollback_service.py:27` | 模型元数据引用 | `# drift_monitoring_service 按 (feature_name, drift_type, model_version, 未解决) 去重，` |
| `backend/app/services/auto_rollback_service.py:33` | 模型元数据引用 | `# 可达性论证：去重键加入 model_version 后，一次漂移检测（每小时 1 次）对某个金丝雀版本` |
| `backend/app/services/auto_rollback_service.py:247` | 模型元数据引用 | `MonitoringLog.model_version == canary.version,` |
| `backend/app/services/auto_rollback_service.py:255` | 模型元数据引用 | `MonitoringLog.model_version == canary.version,` |
| `backend/app/services/auto_rollback_service.py:278` | 模型元数据引用 | `# model_version 过滤保留：PSI > 2.0 的疑似版本失配告警按既有设计 model_version=None，` |
| `backend/app/services/auto_rollback_service.py:282` | 模型元数据引用 | `DriftAlert.model_version == canary.version,` |
| `backend/app/services/auto_rollback_service.py:295` | 模型元数据引用 | `"Canary %d 漂移告警超阈值: %d > %d (窗口=1h, model_version=%s)",` |
| `backend/app/services/auto_rollback_service.py:315` | 模型元数据引用 | `MonitoringLog.model_version == canary.version,` |
| `backend/app/services/canary_manager.py:323` | 模型元数据引用 | `model_version=version,` |
| `backend/app/services/canary_manager.py:463` | 模型元数据引用 | `model_version=canary.version,` |
| `backend/app/services/drift_monitoring_service.py:31` | 模型元数据引用 | `# 此阈值下将 severity 限制为 HIGH 并标注 possible_model_version_mismatch, 等待人工确认.` |
| `backend/app/services/drift_monitoring_service.py:218` | 模型元数据引用 | `"""返回当前运行中的金丝雀版本, 用于 DriftAlert.model_version 归属.` |
| `backend/app/services/drift_monitoring_service.py:254` | 模型元数据引用 | `- 创建单条 MEDIUM 人工复核告警 (details 标注 possible_model_version_mismatch),` |
| `backend/app/services/drift_monitoring_service.py:256` | 模型元数据引用 | `- model_version=None, auto_rollback_service 按 canary.version 统计` |
| `backend/app/services/drift_monitoring_service.py:277` | 模型元数据引用 | `# P0 修复：去重键必须包含 model_version。旧实现只按 feature_name+drift_type+未解决` |
| `backend/app/services/drift_monitoring_service.py:278` | 模型元数据引用 | `# 去重, 金丝雀启动前的历史未解决告警 (含 model_version=None 的版本失配告警)` |
| `backend/app/services/drift_monitoring_service.py:280` | 模型元数据引用 | `# 注意 PSI>2.0 的版本失配告警 model_version=None, 用 is_(None) 与真实版本告警` |
| `backend/app/services/drift_monitoring_service.py:292` | 模型元数据引用 | `DriftAlert.model_version.is_(None),` |
| `backend/app/services/drift_monitoring_service.py:304` | 模型元数据引用 | `DriftAlert.model_version == target_version,` |
| `backend/app/services/drift_monitoring_service.py:326` | 模型元数据引用 | `# model_version=None: auto_rollback_service 按 canary.version 统计` |
| `backend/app/services/drift_monitoring_service.py:329` | 模型元数据引用 | `model_version=None,` |
| `backend/app/services/drift_monitoring_service.py:341` | 模型元数据引用 | `"possible_model_version_mismatch": True,` |
| `backend/app/services/drift_monitoring_service.py:354` | 模型元数据引用 | `# model_version 归属 = 当前运行中的金丝雀版本 (已在去重阶段解析并复用)。` |
| `backend/app/services/drift_monitoring_service.py:355` | 模型元数据引用 | `# 修复: 此前将 modality 存入 model_version, 导致 auto_rollback_service 按` |
| `backend/app/services/drift_monitoring_service.py:361` | 模型元数据引用 | `model_version=canary_version,` |
| `backend/app/services/drift_monitoring_service.py:373` | 模型元数据引用 | `"possible_model_version_mismatch": False,` |
| `backend/app/services/drift_monitoring_service.py:396` | 模型元数据引用 | `model_version 存 canary 版本——原实现按 model_version == modality` |
| `backend/app/services/drift_monitoring_service.py:399` | 模型元数据引用 | `- model_version == modality (历史遗留告警)` |
| `backend/app/services/drift_monitoring_service.py:416` | 模型元数据引用 | `DriftAlert.model_version == modality,` |
| `backend/app/services/model_predict/fusion.py:142` | 模型元数据引用 | `model_version=canary_version,` |
| `backend/app/services/model_predict/fusion.py:152` | 模型元数据引用 | `result["model_version"] = f"{canary_version} (canary)"` |
| `backend/app/services/model_predict/fusion.py:167` | 模型元数据引用 | `model_version=canary_version,` |
| `backend/app/services/model_predict/fusion.py:193` | 模型元数据引用 | `model_version: str,` |
| `backend/app/services/model_predict/fusion.py:214` | 模型元数据引用 | `model_version=model_version,` |
| `backend/app/services/model_predict/fusion.py:226` | 模型元数据引用 | `model_version,` |
| `backend/app/services/observability_service.py:176` | 模型元数据引用 | `model_version: str \| None = None,` |
| `backend/app/services/observability_service.py:185` | 模型元数据引用 | `model_version=model_version,` |
| `backend/app/services/observability_service.py:194` | 模型元数据引用 | `model_version: str \| None = None,` |
| `backend/app/services/observability_service.py:213` | 模型元数据引用 | `model_version=model_version,` |
| `backend/app/services/observability_service.py:225` | 模型元数据引用 | `model_version: str \| None = None,` |
| `backend/app/services/observability_service.py:235` | 模型元数据引用 | `model_version=model_version,` |
| `backend/app/services/observability_service.py:245` | 模型元数据引用 | `model_version: str \| None = None,` |
| `backend/app/services/observability_service.py:259` | 模型元数据引用 | `model_version=model_version,` |
| `backend/app/services/validation_engine.py:57` | 模型元数据引用 | `model_version: str` |
| `backend/app/services/validation_engine.py:66` | 模型元数据引用 | `"model_version": self.model_version,` |
| `backend/app/services/validation_engine.py:352` | 模型元数据引用 | `model_version: str,` |
| `backend/app/services/validation_engine.py:358` | 模型元数据引用 | `model_version: 模型版本标签（如 "v1.20"）。` |
| `backend/app/services/validation_engine.py:364` | 模型元数据引用 | `model_id = self._VERSION_TO_MODEL_ID.get(model_version)` |
| `backend/app/services/validation_engine.py:367` | 模型元数据引用 | `"ValidationEngine: model_version '%s' 未映射到任何 model_id，"` |
| `backend/app/services/validation_engine.py:369` | 模型元数据引用 | `model_version,` |
| `backend/app/services/validation_engine.py:416` | 模型元数据引用 | `"ValidationEngine: 模型推理失败 (model_version=%s, model_id=%s): %s",` |
| `backend/app/services/validation_engine.py:417` | 模型元数据引用 | `model_version,` |
| `backend/app/services/validation_engine.py:425` | 模型元数据引用 | `model_version: str,` |
| `backend/app/services/validation_engine.py:433` | 模型元数据引用 | `model_version: Model version to validate.` |
| `backend/app/services/validation_engine.py:442` | 模型元数据引用 | `model_version=model_version, metrics=ValidationMetrics()` |
| `backend/app/services/validation_engine.py:453` | 模型元数据引用 | `inference_result = await self._run_model_inference(model_version, features)` |
| `backend/app/services/validation_engine.py:456` | 模型元数据引用 | `f"Model inference unavailable for version '{model_version}': "` |
| `frontend/src/api/modelApi.ts:26` | 模型元数据引用 | `model_version?: string \| null` |
| `frontend/src/api/modelApi.ts:92` | 模型元数据引用 | `model_version: string` |
| `frontend/src/views/user/components/FusionAssessTab.vue:95` | 模型元数据引用 | `<p>{{ t('userRisk.fusionModelVersionLabel') }}{{ result.model_version \|\| t('userRisk.notAvailable') }}</p>` |
| `frontend/src/views/user/components/FusionAssessTab.vue:153` | 模型元数据引用 | `{{ result.model_version \|\| t('userRisk.notAvailable') }}` |
| `frontend/src/views/user/components/structured-steps/StructuredResultPanel.vue:89` | 模型元数据引用 | `{{ modelTabResult.model_version \|\| t('structuredAssess.notAvailable') }}` |

## 已知局限（如实记账）

1. 风险等级 / 角色 / 模型元数据三类只扫描**定义处**与字面量出现，
   不做语义等价判定（如 `mild/moderate` 与 `low/medium` 是否同义需
   业务确认，不属机械可判范围）。
2. 类别 2/6/7 的 verdict 是「发现数量」而非「重复数量」—— 真正需要
   re-export 的子集需人工判定后写进本文件第X 节，闸门按该子集把守。
