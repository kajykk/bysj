import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import ExperimentTab from './ExperimentTab.vue'
import i18n from '@/i18n'

// 模拟 ECharts（使用 vi.hoisted 避免 mock 工厂引用未初始化变量）
const { setOptionMock, disposeMock, resizeMock } = vi.hoisted(() => ({
  setOptionMock: vi.fn(),
  disposeMock: vi.fn(),
  resizeMock: vi.fn(),
}))
vi.mock('@/utils/echarts', () => ({
  echarts: {
    init: vi.fn(() => ({
      setOption: setOptionMock,
      resize: resizeMock,
      dispose: disposeMock,
    })),
    graphic: { LinearGradient: vi.fn() },
  },
}))

// 模拟 modelApi
const { importDatasetMock, trainModelMock, evaluateModelMock, compareModelsMock } = vi.hoisted(() => ({
  importDatasetMock: vi.fn(),
  trainModelMock: vi.fn(),
  evaluateModelMock: vi.fn(),
  compareModelsMock: vi.fn(),
}))
vi.mock('@/api/modelApi', () => ({
  modelApi: {
    importDataset: importDatasetMock,
    trainModel: trainModelMock,
    evaluateModel: evaluateModelMock,
    compareModels: compareModelsMock,
  },
}))

const mountOptions = {
  global: {
    plugins: [i18n, createPinia()],
  },
}

describe('ExperimentTab', () => {
  beforeEach(() => {
    setOptionMock.mockClear()
    disposeMock.mockClear()
    importDatasetMock.mockClear()
    trainModelMock.mockClear()
    evaluateModelMock.mockClear()
    compareModelsMock.mockClear()
  })

  it('挂载后应显示实验评估面板标题与动作选项', () => {
    const wrapper = mount(ExperimentTab, mountOptions)
    expect(wrapper.text()).toContain('导入数据集')
    expect(wrapper.text()).toContain('训练 BERT')
    expect(wrapper.text()).toContain('验证集概览')
    expect(wrapper.text()).toContain('对比概览')
  })

  it('应包含数据集名称表单项', () => {
    const wrapper = mount(ExperimentTab, mountOptions)
    expect(wrapper.text()).toContain('数据集')
  })

  it('挂载时无实验数据不应初始化图表', async () => {
    // 无实验数据时 renderExperimentCharts 不会调用 echarts.init
    mount(ExperimentTab, mountOptions)
    await flushPromises()
    expect(setOptionMock).not.toHaveBeenCalled()
  })

  it('BERT 入口禁用: 训练/评估按钮不可点且不发起请求', async () => {
    // AUDIT-2026-10-04 (P0-1 衍生): BERT 权重已归档、注册条目移除, 训练/评估必然失败。
    // 入口显式禁用 -> 按钮 disabled, 点击不调用 trainModel/evaluateModel。
    const wrapper = mount(ExperimentTab, mountOptions)
    await flushPromises()
    const trainBtn = wrapper.findAll('button').find(b => b.text().includes('训练 BERT'))
    const evalBtn = wrapper.findAll('button').find(b => b.text().includes('验证集概览'))
    expect(trainBtn).toBeTruthy()
    expect(evalBtn).toBeTruthy()
    // Element Plus 渲染为 disabled=""（空字符串，falsy），故断言属性**存在**而非取真值
    expect('disabled' in trainBtn!.attributes()).toBe(true)
    expect('disabled' in evalBtn!.attributes()).toBe(true)
    await trainBtn!.trigger('click')
    await evalBtn!.trigger('click')
    await flushPromises()
    expect(trainModelMock).not.toHaveBeenCalled()
    expect(evaluateModelMock).not.toHaveBeenCalled()
  })

  it('对比动作仍可用且会初始化图表, 卸载时释放', async () => {
    // 覆盖图表生命周期: 走未被禁用的「对比概览」, 避免依赖已下线的 BERT 训练
    // applyCompareResult 取 res.results（不是 models）
    compareModelsMock.mockResolvedValue({
      results: [
        { model_name: 'text_depression_model', accuracy: 0.86, f1: 0.83 },
        { model_name: 'fusion_dnn_best', accuracy: 0.84, f1: 0.81 },
      ],
      status: 'ok',
    })
    const wrapper = mount(ExperimentTab, mountOptions)
    await flushPromises()
    const cmpBtn = wrapper.findAll('button').find(b => b.text().includes('对比概览'))
    expect(cmpBtn).toBeTruthy()
    expect(cmpBtn!.attributes('disabled')).toBeFalsy()
    await cmpBtn!.trigger('click')
    await flushPromises()
    expect(compareModelsMock).toHaveBeenCalled()
    // 对比列表不应再包含已归档的 BERT 模型
    const payload = compareModelsMock.mock.calls[0][0] as { model_names: string[] }
    expect(payload.model_names).not.toContain('text_bert_classifier')
    wrapper.unmount()
    expect(disposeMock).toHaveBeenCalled()
  })

  it('未执行实验时应显示空状态或占位', () => {
    const wrapper = mount(ExperimentTab, mountOptions)
    // 实验摘要区在无结果时不应显示具体数值
    expect(wrapper.text()).not.toContain('训练损失')
  })

  it('BERT 入口禁用时不再调用 trainModel（权重已归档）', async () => {
    trainModelMock.mockResolvedValue({
      train_loss: [0.5],
      val_loss: [0.4],
      val_accuracy: [0.85],
      status: 'ok',
      trainer_log_history: [],
      eval_history: [],
    })
    const wrapper = mount(ExperimentTab, mountOptions)
    await flushPromises()
    const trainBtn = wrapper.findAll('button').find(b => b.text().includes('训练 BERT'))
    expect(trainBtn).toBeTruthy()
    await trainBtn!.trigger('click')
    await flushPromises()
    // 入口禁用: 不发请求, 避免用户点了才收到「未注册」报错
    expect(trainModelMock).not.toHaveBeenCalled()
  })
})
