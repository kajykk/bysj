import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
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
    plugins: [i18n],
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

  it('训练后应初始化图表且卸载时释放', async () => {
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
    // 训练完成后应初始化图表并调用 setOption
    expect(setOptionMock).toHaveBeenCalled()
    // 卸载时应释放图表
    wrapper.unmount()
    expect(disposeMock).toHaveBeenCalled()
  })

  it('未执行实验时应显示空状态或占位', () => {
    const wrapper = mount(ExperimentTab, mountOptions)
    // 实验摘要区在无结果时不应显示具体数值
    expect(wrapper.text()).not.toContain('训练损失')
  })

  it('点击训练按钮应调用 trainModel 接口', async () => {
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
    expect(trainModelMock).toHaveBeenCalled()
  })
})
