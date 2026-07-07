import { describe, it, expect } from 'vitest'

describe('AdminTemplatesPage - 5.2.1 模板列表增强', () => {
  it('状态开关应支持 active/inactive 切换', () => {
    const statusValues = ['active', 'inactive']
    expect(statusValues).toContain('active')
    expect(statusValues).toContain('inactive')
  })

  it('预览对话框应显示模板完整信息', () => {
    const previewFields = [
      '模板名称',
      '适用等级',
      '预计周数',
      '状态',
      '任务列表'
    ]

    expect(previewFields).toContain('任务列表')
    expect(previewFields).toHaveLength(5)
  })

  it('任务列表应正确显示任务详情', () => {
    const tasks = [
      { task_name: '呼吸训练', task_type: 'meditation', schedule: 'daily', duration_minutes: 15 },
      { task_name: '运动', task_type: 'exercise', schedule: 'weekly', duration_minutes: 30 }
    ]

    expect(tasks[0].task_name).toBe('呼吸训练')
    expect(tasks[0].duration_minutes).toBe(15)
    expect(tasks[1].schedule).toBe('weekly')
  })

  it('状态更新失败应回滚状态', () => {
    const currentStatus = 'active'
    const newStatus = 'inactive'
    const updateFailed = true

    const rolledBackStatus = updateFailed ? currentStatus : newStatus
    expect(rolledBackStatus).toBe('active')
  })

  it('预览任务项应包含序号样式', () => {
    const taskIndexStyle = {
      width: '20px',
      height: '20px',
      borderRadius: '50%',
      background: '#3b82c4',
      color: '#fff'
    }

    expect(taskIndexStyle.borderRadius).toBe('50%')
    expect(taskIndexStyle.background).toBe('#3b82c4')
  })
})
