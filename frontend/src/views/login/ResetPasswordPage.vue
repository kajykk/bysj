<template>
  <div class="reset-page">
    <el-card
      class="reset-card"
      shadow="hover"
    >
      <template #header>
        <div>
          <h2>重置密码</h2>
          <p>请输入新密码完成重置</p>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent
      >
        <el-form-item
          label="邮箱"
          prop="email"
        >
          <el-input
            v-model="form.email"
            placeholder="请输入邮箱"
            clearable
          />
        </el-form-item>
        <el-form-item
          label="重置令牌"
          prop="reset_token"
        >
          <el-input
            v-model="form.reset_token"
            type="textarea"
            :rows="3"
            placeholder="请粘贴邮件中的重置令牌"
          />
        </el-form-item>
        <el-form-item
          label="新密码"
          prop="new_password"
        >
          <el-input
            v-model="form.new_password"
            type="password"
            show-password
            placeholder="至少8位，包含字母和数字"
          />
        </el-form-item>

        <el-button
          type="primary"
          :loading="loading"
          class="submit-btn"
          @click="handleSubmit"
        >
          确认重置
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { authApi } from '@/api/auth'
import { getErrorDetail } from '@/utils/errorDetail'
import { validatePasswordBytes } from '@/utils/passwordValidation'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const formRef = ref<FormInstance>()

const form = reactive({
  email: '',
  reset_token: '',
  new_password: ''
})

const rules: FormRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: ['blur', 'change'] }
  ],
  reset_token: [{ required: true, message: '请输入重置令牌', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少8位', trigger: 'blur' },
    { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码需包含字母和数字', trigger: 'blur' },
    { validator: validatePasswordBytes, trigger: 'blur' }
  ]
}

onMounted(() => {
  // 支持从邮件链接直接回填邮箱与 token，减少用户粘贴错误的概率。
  form.email = typeof route.query.email === 'string' ? route.query.email : ''
  form.reset_token = typeof route.query.token === 'string' ? route.query.token : ''
})

const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    loading.value = true
    await authApi.resetPassword(form)
    ElMessage.success('密码重置成功，请使用新密码登录')
    await router.push('/login')
  } catch (error) {
    ElMessage.error(getErrorDetail(error, '密码重置失败，请检查链接是否有效'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.reset-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
  background: linear-gradient(140deg, #f3f7ff 0%, #f6fff7 60%, #f7f7ff 100%);
}

.reset-card {
  width: 100%;
  max-width: 460px;
}

.submit-btn {
  width: 100%;
}
</style>
