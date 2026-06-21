# 审计导出 UI 报告 — v1.19-ci-e2e-audit-export

> **执行时间**: 2026-05-01  
> **对应任务**: Phase 5 (Task 5.1-5.6)

---

## 1. 创建文件

| 文件 | 操作 | 状态 |
|---|---|---|
| `frontend/src/views/admin/AdminCrisisEventsPage.vue` | 新建 | ✅ |
| `frontend/src/router/index.ts` | 修改 (添加路由) | ✅ |

---

## 2. 功能实现

| 功能 | 状态 | 说明 |
|---|---|---|
| 危机事件列表表格 | ✅ | 展示 id/user_id/触发来源/危机分数/状态/关键词/复核任务/创建时间/处理人/动作 |
| 状态筛选 | ✅ | detected/reviewed/escalated/resolved 下拉选择 |
| 日期范围选择器 | ✅ | el-date-picker daterange, 默认30天 |
| 导出 CSV 按钮 | ✅ | el-button, 带 Download 图标, loading 状态 |
| CSV blob 下载 | ✅ | Blob + URL.createObjectURL + <a> download |
| 文件名格式 | ✅ | crisis_events_YYYYMMDD_YYYYMMDD.csv |
| Loading 状态 | ✅ | loading ref + el-button :loading |
| Error Toast | ✅ | 403 权限提示, 通用错误提示 |
| Empty 提示 | ✅ | ListPageScaffold empty-text="暂无危机事件" |
| 用户 ID 脱敏 | ✅ | maskUserId() 保留前2位 |
| 危机分数颜色 | ✅ | ≥80=红色, ≥50=黄色, <50=绿色 |
| 中文标签 | ✅ | 触发来源/状态/关键词等全部汉化 |
| 分页 | ✅ | PageTable 组件集成 |

---

## 3. API 集成

| API | 方法 | 用途 |
|---|---|---|
| `/reviews/crisis-events` | GET | 列表查询 (status, start_date, end_date, page, page_size) |
| `/admin/crisis-events/export` | GET | CSV 导出 (start_date, end_date, responseType: blob) |

---

## 4. 构建验证

| 项目 | 状态 |
|---|---|
| npm run build | ✅ (2543 modules, dist/ 150 items) |
| Circular chunk warning | ⚠️ 非阻塞 |
| 前端单元测试 | ⚠️ Windows 环境限制 |

---

## 5. 设计模式一致性

- ✅ 使用 `ListPageScaffold` + `FilterBar` + `PageTable` 标准组件
- ✅ 参考 `AdminOperationLogsPage.vue` 模式
- ✅ 使用 `useListQueryState` composable 管理查询状态
- ✅ 使用 `showHttpFeedback` 处理 HTTP 错误
- ✅ 使用 Element Plus (`el-table`, `el-date-picker`, `el-dialog`, `el-tag`)

---

> **文档版本**: v1.0  
> **最后更新**: 2026-05-01
