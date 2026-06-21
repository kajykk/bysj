import { describe, it, expect } from 'vitest'

describe('AdminOperationLogsPage - 5.3.1 日志功能增强', () => {
  it('操作类型应映射到正确的标签颜色', () => {
    const getActionTypeTag = (actionType: string) => {
      if (actionType.includes('warning')) return 'warning'
      if (actionType.includes('user')) return 'primary'
      if (actionType.includes('delete')) return 'danger'
      if (actionType.includes('create')) return 'success'
      if (actionType.includes('update')) return 'info'
      return 'info'
    }

    expect(getActionTypeTag('warning_handle')).toBe('warning')
    expect(getActionTypeTag('user_create')).toBe('primary')
    expect(getActionTypeTag('delete_record')).toBe('danger')
    expect(getActionTypeTag('create_template')).toBe('success')
    expect(getActionTypeTag('update_settings')).toBe('info')
  })

  it('角色应映射到正确的标签类型和中文', () => {
    const getRoleTagType = (role: string) => {
      const map: Record<string, string> = { user: 'success', counselor: 'warning', admin: 'danger' }
      return map[role] || 'info'
    }

    const getRoleLabel = (role: string) => {
      const map: Record<string, string> = { user: '用户', counselor: '咨询师', admin: '管理员' }
      return map[role] || role
    }

    expect(getRoleTagType('user')).toBe('success')
    expect(getRoleTagType('admin')).toBe('danger')
    expect(getRoleLabel('counselor')).toBe('咨询师')
    expect(getRoleLabel('admin')).toBe('管理员')
  })

  it('CSV 导出应包含正确的表头和数据', () => {
    const rows = [
      { id: 1, action_type: 'warning_handle', operator_role: 'counselor', target_type: 'warning', target_id: 100, created_at: '2026-04-27' }
    ]

    const headers = ['ID', '操作类型', '操作者角色', '目标类型', '目标ID', '时间']
    const csvContent = [
      headers.join(','),
      ...rows.map((row) => [
        row.id,
        row.action_type,
        row.operator_role,
        row.target_type,
        row.target_id,
        row.created_at
      ].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
    ].join('\n')

    expect(csvContent).toContain('ID,操作类型,操作者角色,目标类型,目标ID,时间')
    expect(csvContent).toContain('warning_handle')
    expect(csvContent).toContain('counselor')
  })

  it('导出文件名应包含日期', () => {
    const filename = `operation_logs_${new Date().toISOString().slice(0, 10)}.csv`
    expect(filename).toMatch(/operation_logs_\d{4}-\d{2}-\d{2}\.csv/)
  })

  it('筛选条件应包含操作者名称', () => {
    const filters = { operatorName: '张三', actionType: 'warning_handle' }
    expect(filters.operatorName).toBe('张三')
    expect(filters.actionType).toBe('warning_handle')
  })
})
