import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import TrainingRegistryCard from './TrainingRegistryCard.vue'
import i18n from '@/i18n'

const {
  getModelRegistryMock,
  activateRegistryModelMock,
  rollbackRegistryModelMock,
  runAutoRollbackCheckMock,
} = vi.hoisted(() => ({
  getModelRegistryMock: vi.fn(),
  activateRegistryModelMock: vi.fn(),
  rollbackRegistryModelMock: vi.fn(),
  runAutoRollbackCheckMock: vi.fn(),
}))

vi.mock('@/api/modelApi', () => ({
  modelApi: {
    getModelRegistry: getModelRegistryMock,
    activateRegistryModel: activateRegistryModelMock,
    rollbackRegistryModel: rollbackRegistryModelMock,
    runAutoRollbackCheck: runAutoRollbackCheckMock,
  },
}))

const makeRecord = (overrides: Record<string, unknown> = {}) => ({
  model_id: 'bert_finetune_run1',
  name: 'bert_finetune_run1',
  version: 'v1',
  model_type: 'logistic_regression',
  status: 'candidate',
  fallback_id: null,
  performance_threshold: {},
  metrics: { accuracy: 0.9123, f1: 0.8871, shadow_total: 25, shadow_agreement_rate: 0.83 },
  artifact_path: 'models/trained/bert_finetune_run1/model.pkl',
  training_config: {},
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  ...overrides,
})

// el-tooltip 在 jsdom 中直接渲染插槽内容；el-table/el-table-column 保持真实组件以渲染数据行
const mountOptions = {
  global: {
    plugins: [i18n],
    stubs: {
      'el-tooltip': { template: '<span><slot /></span>' },
    },
  },
}

describe('TrainingRegistryCard 模型注册表', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getModelRegistryMock.mockResolvedValue([])
  })

  it('canTrain=false 时不渲染注册表卡片', () => {
    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: false }, ...mountOptions })
    expect(wrapper.find('.registry-card').exists()).toBe(false)
  })

  it('挂载后加载注册表记录并展示状态与指标', async () => {
    getModelRegistryMock.mockResolvedValue([makeRecord(), makeRecord({ model_id: 'xgb_v2', status: 'production' })])
    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: true }, ...mountOptions })
    await flushPromises()

    expect(getModelRegistryMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('bert_finetune_run1')
    expect(wrapper.text()).toContain('候选')
    const prodButtons = wrapper.findAll('button').filter(b => b.text().includes('人工回退'))
    expect(prodButtons.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('样本：25')
  })

  it('无注册记录时展示空态说明', async () => {
    getModelRegistryMock.mockResolvedValue([])
    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: true }, ...mountOptions })
    await flushPromises()
    expect(wrapper.text()).toContain('暂无训练产物注册记录')
  })

  it('注册表加载失败时提示并展示空态', async () => {
    const warnSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined)
    getModelRegistryMock.mockRejectedValue(new Error('network'))
    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: true }, ...mountOptions })
    await flushPromises()

    expect(warnSpy).toHaveBeenCalled()
    expect(wrapper.text()).toContain('暂无训练产物注册记录')
    warnSpy.mockRestore()
  })

  it('点击激活按钮应调用激活 API 并刷新列表', async () => {
    getModelRegistryMock.mockResolvedValue([makeRecord()])
    activateRegistryModelMock.mockResolvedValue({ model: makeRecord({ status: 'production' }), shadow_decision: 'ok' })
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined)

    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: true }, ...mountOptions })
    await flushPromises()

    const activateBtn = wrapper.findAll('button').find(b => b.text().includes('激活上线'))
    expect(activateBtn).toBeTruthy()
    await activateBtn!.trigger('click')
    await flushPromises()

    expect(confirmSpy).toHaveBeenCalled()
    expect(activateRegistryModelMock).toHaveBeenCalledWith('bert_finetune_run1')
    expect(successSpy).toHaveBeenCalled()
    expect(getModelRegistryMock).toHaveBeenCalledTimes(2)

    confirmSpy.mockRestore()
    successSpy.mockRestore()
  })

  it('点击人工回退需调用回退 API', async () => {
    getModelRegistryMock.mockResolvedValue([makeRecord({ status: 'production' })])
    rollbackRegistryModelMock.mockResolvedValue(makeRecord({ status: 'candidate' }))
    const confirmSpy = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)

    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: true }, ...mountOptions })
    await flushPromises()

    const rollbackBtn = wrapper.findAll('button').find(b => b.text().includes('人工回退'))
    expect(rollbackBtn).toBeTruthy()
    await rollbackBtn!.trigger('click')
    await flushPromises()

    expect(rollbackRegistryModelMock).toHaveBeenCalledWith('bert_finetune_run1')
    expect(getModelRegistryMock).toHaveBeenCalledTimes(2)
    confirmSpy.mockRestore()
  })

  it('点击回退检查并展示回退结果', async () => {
    getModelRegistryMock.mockResolvedValue([])
    runAutoRollbackCheckMock.mockResolvedValue({ results: [{ model_id: 'x1', rolled_back: true }] })
    const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined)

    const wrapper = mount(TrainingRegistryCard, { props: { canTrain: true }, ...mountOptions })
    await flushPromises()

    const checkBtn = wrapper.findAll('button').find(b => b.text().includes('回退检查'))
    expect(checkBtn).toBeTruthy()
    if (!checkBtn) return
    await checkBtn.trigger('click')
    await flushPromises()

    expect(runAutoRollbackCheckMock).toHaveBeenCalledTimes(1)
    expect(successSpy).toHaveBeenCalled()
    successSpy.mockRestore()
  })
})