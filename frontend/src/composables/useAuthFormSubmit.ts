import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import type { FormInstance } from 'element-plus'
import { getErrorDetail } from '@/utils/errorDetail'

/**
 * 认证类表单的统一提交骨架（M-27）。
 * 与原先各页面内联的 try/catch/finally 等价：
 *   表单校验 → loading=true → 业务动作 → 成功提示 → 成功后回调
 *   → 任何异常统一 getErrorDetail + ElMessage.error → finally loading=false。
 * loading 由本 composable 暴露，供模板按钮 :loading 绑定。
 */
interface SubmitOptions<T> {
  successMessage: string
  errorMessage: string
  onSuccess?: (result: T) => void | Promise<void>
}

export function useAuthFormSubmit() {
  const loading = ref(false)

  const submit = async <T>(
    formRef: Ref<FormInstance | undefined>,
    action: () => Promise<T>,
    options: SubmitOptions<T>
  ): Promise<void> => {
    if (!formRef.value) return
    try {
      await formRef.value.validate()
      loading.value = true
      const result = await action()
      ElMessage.success(options.successMessage)
      await options.onSuccess?.(result)
    } catch (error) {
      ElMessage.error(getErrorDetail(error, options.errorMessage))
    } finally {
      loading.value = false
    }
  }

  return { loading, submit }
}
