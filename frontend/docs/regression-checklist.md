# 回归 Checklist（关键流程最低保障）

## A. 认证与路由
- [ ] 未登录访问 `/user/warnings` 被拦截到 `/login`
- [ ] 角色不匹配访问路由（如 user 访问 `/admin/operation-logs`）被重定向到对应首页
- [ ] 无权限访问按钮显示明确 UI（`无权限`/`无审计权限`），不出现静默失败

## B. 接口契约与字段一致性
- [ ] 所有分页接口返回结构固定为 `items/total/page/page_size`
- [ ] `warning.risk_level` 返回值固定为 `low/medium/high`
- [ ] `warning.status` 返回值固定为 `pending/handled/ignored`
- [ ] 操作日志 `action_type` 对预警动作固定为 `warning_handle/warning_ignore/warning_read`

## C. 用户端闭环
- [ ] 用户可查看预警列表并看到统一字段（`risk_level/status/created_at`）
- [ ] 单条“标记已读”成功后状态变化正确，失败时行内错误可见
- [ ] 已读动作写入操作日志，可按 `action_type=warning_read` 检索

## D. 咨询师端闭环
- [ ] 咨询师可执行“处理/忽略”并生成可审计日志
- [ ] 批量处理失败时前端状态回滚（原子回滚）
- [ ] 创建咨询记录支持 `warning_id`，且仅允许绑定当前咨询师-用户关系下的预警
- [ ] 咨询记录列表返回 `warning_id/warning_status/warning_risk_level`

## E. 管理端审计
- [ ] 操作日志支持筛选并可查看详情
- [ ] 无审计权限时“查看详情”按钮替换为明确无权限提示

## F. 错误处理策略
- [ ] 401 -> 登录失效处理（清理登录态并跳转登录）
- [ ] 403 -> 无权限提示
- [ ] 404 -> 资源不存在提示 + 可重试
- [ ] 422 -> 参数校验失败提示
- [ ] 500 -> 服务异常提示 + 可重试
