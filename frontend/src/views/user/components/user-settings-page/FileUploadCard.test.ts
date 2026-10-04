import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { genFileId, type UploadRawFile } from 'element-plus'
import FileUploadCard from './FileUploadCard.vue'
import i18n from '@/i18n'

// 模拟 userApi（上传走 userApi.uploadFile / userApi.uploadFiles）
const { uploadFileMock, uploadFilesMock } = vi.hoisted(() => ({
  uploadFileMock: vi.fn(),
  uploadFilesMock: vi.fn(),
}))
vi.mock('@/api/userApi', () => ({
  userApi: {
    uploadFile: uploadFileMock,
    uploadFiles: uploadFilesMock,
  },
}))

// 部分模拟 element-plus：仅拦截消息组件；ElUpload 等保留真实实现
const { messageSuccessMock, messageErrorMock, messageWarningMock } = vi.hoisted(() => ({
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn(),
}))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: {
      success: messageSuccessMock,
      error: messageErrorMock,
      warning: messageWarningMock,
    },
  }
})

const mountOptions = {
  global: {
    plugins: [i18n],
  },
}

const makeRawFile = (name: string, sizeBytes: number): UploadRawFile => {
  const file = new File([new Uint8Array(Math.min(sizeBytes, 1024))], name) as UploadRawFile
  Object.defineProperty(file, 'size', { value: sizeBytes })
  file.uid = genFileId()
  return file
}

const addFiles = async (wrapper: ReturnType<typeof mount>, files: UploadRawFile[]) => {
  // jsdom 下以原生 input change 事件驱动 el-upload（组件未把 handleStart 暴露到 vm）
  const input = wrapper.find('input[type="file"]')
  expect(input.exists()).toBe(true)
  const fileList = files.map(f => Object.defineProperty(f, 'target', { value: null }))
  Object.defineProperty(input.element, 'files', { value: fileList, configurable: true })
  await input.trigger('change')
  await flushPromises()
}

describe('FileUploadCard（AUDIT-2026-10-01 决策三 P6）', () => {
  beforeEach(() => {
    uploadFileMock.mockReset()
    uploadFilesMock.mockReset()
    messageSuccessMock.mockClear()
    messageErrorMock.mockClear()
    messageWarningMock.mockClear()
  })

  it('渲染标题、分类选择与拖拽上传区', () => {
    const wrapper = mount(FileUploadCard, mountOptions)
    expect(wrapper.text()).toContain('文件上传')
    expect(wrapper.text()).toContain('文件分类')
    expect(wrapper.text()).toContain('点击或拖拽文件到此处')
  })

  it('未选文件时上传按钮禁用', () => {
    const wrapper = mount(FileUploadCard, mountOptions)
    const uploadBtn = wrapper.findAll('button').find(b => b.text() === '上传')
    expect(uploadBtn).toBeDefined()
    expect(uploadBtn!.attributes('disabled')).toBeDefined()
  })

  it('单个文件走 POST /user/upload，默认不携带 category', async () => {
    uploadFileMock.mockResolvedValue({
      url: '/uploads/1/a.jpg',
      filename: 'a.jpg',
      original_name: '风景.jpg',
      size: 1024,
      content_type: 'image/jpeg'
    })
    const wrapper = mount(FileUploadCard, mountOptions)
    await addFiles(wrapper, [makeRawFile('风景.jpg', 1024)])

    const uploadBtn = wrapper.findAll('button').find(b => b.text() === '上传')
    await uploadBtn!.trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledTimes(1)
    const [formData, category] = uploadFileMock.mock.calls[0]
    expect(formData).toBeInstanceOf(FormData)
    expect(formData.get('file')).toBeTruthy()
    expect(category).toBeUndefined()
    // 结果表展示保存名与大小
    expect(wrapper.text()).toContain('a.jpg')
    expect(messageSuccessMock).toHaveBeenCalled()
  })

  it('多个文件走批量接口，失败项带 error 展示为失败行', async () => {
    uploadFilesMock.mockResolvedValue({
      items: [
        { url: '/uploads/1/b.png', filename: 'b.png', original_name: '图.png', size: 2048 },
        { filename: 'c.txt', error: '不支持的文件类型: .txt' }
      ],
      count: 2
    })
    const wrapper = mount(FileUploadCard, mountOptions)
    await addFiles(wrapper, [makeRawFile('图.png', 2048), makeRawFile('c.txt', 10)])

    const batchBtn = wrapper.findAll('button').find(b => b.text().includes('批量上传'))
    await batchBtn!.trigger('click')
    await flushPromises()

    expect(uploadFilesMock).toHaveBeenCalledTimes(1)
    const [formData] = uploadFilesMock.mock.calls[0]
    expect(formData).toBeInstanceOf(FormData)
    // files 字段名（与后端批量接口一致），两条记录
    expect(formData.getAll('files').length).toBe(2)
    // 逐项结果：成功行与失败行都在结果表里
    expect(wrapper.text()).toContain('图.png')
    expect(wrapper.text()).toContain('不支持的文件类型: .txt')
    expect(messageWarningMock).toHaveBeenCalled()
  })

  it('超过 20MB 的文件前端直接标记跳过，不发请求', async () => {
    const wrapper = mount(FileUploadCard, mountOptions)
    await addFiles(wrapper, [makeRawFile('huge.bin', 21 * 1024 * 1024)])

    const uploadBtn = wrapper.findAll('button').find(b => b.text() === '上传')
    await uploadBtn!.trigger('click')
    await flushPromises()

    expect(uploadFileMock).not.toHaveBeenCalled()
    expect(uploadFilesMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('超过 20MB，已跳过')
  })

  it('批量接口整体失败（如超 10 个 400）→ 每个文件都有失败归属行', async () => {
    uploadFilesMock.mockRejectedValue({ response: { status: 400, data: { detail: '最多同时上传10个文件' } } })
    const wrapper = mount(FileUploadCard, mountOptions)
    await addFiles(wrapper, [makeRawFile('a.txt', 5), makeRawFile('b.txt', 5)])

    const batchBtn = wrapper.findAll('button').find(b => b.text().includes('批量上传'))
    await batchBtn!.trigger('click')
    await flushPromises()

    expect(uploadFilesMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('a.txt')
    expect(wrapper.text()).toContain('b.txt')
  })
})
