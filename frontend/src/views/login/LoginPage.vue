<template>
  <div class="auth-page">
    <div class="auth-page__bg" />

    <el-card
      class="auth-card"
      shadow="hover"
    >
      <template #header>
        <div class="auth-card__header">
          <div>
            <h2>心理健康预警系统</h2>
            <p>欢迎使用，请先登录或注册账号</p>
          </div>
          <el-tag
            :type="isLogin ? 'primary' : 'success'"
            effect="light"
          >
            {{ isLogin ? '登录' : '注册' }}
          </el-tag>
        </div>
      </template>

      <el-tabs
        v-model="activeTab"
        class="auth-tabs"
        stretch
        @tab-change="clearActiveFormValidation"
      >
        <el-tab-pane
          name="login"
          label="登录"
        />
        <el-tab-pane
          name="register"
          label="注册"
        />
      </el-tabs>

      <el-form
        v-if="isLogin"
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        label-position="top"
        @submit.prevent
      >
        <el-form-item
          label="用户名"
          prop="username"
        >
          <el-input
            v-model="loginForm.username"
            placeholder="请输入用户名"
            clearable
            @keyup.enter="focusPassword"
          />
        </el-form-item>
        <el-form-item
          label="密码"
          prop="password"
        >
          <el-input
            v-model="loginForm.password"
            type="password"
            show-password
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <div class="login-extra-actions">
          <el-checkbox
            v-model="rememberMe"
            size="small"
          >
            记住我
          </el-checkbox>
          <el-button
            link
            type="primary"
            @click="goResetPassword"
          >
            忘记密码？
          </el-button>
        </div>

        <el-button
          type="primary"
          :loading="loading"
          class="submit-btn"
          @click="handleLogin"
        >
          登录
        </el-button>
      </el-form>

      <el-form
        v-else
        ref="registerFormRef"
        :model="registerForm"
        :rules="registerRules"
        label-position="top"
        @submit.prevent
      >
        <el-form-item
          label="用户名"
          prop="username"
        >
          <el-input
            v-model="registerForm.username"
            placeholder="3~20位字母数字下划线"
            clearable
          />
        </el-form-item>
        <el-form-item
          label="昵称"
          prop="nickname"
        >
          <el-input
            v-model="registerForm.nickname"
            placeholder="可选"
            clearable
          />
        </el-form-item>
        <el-form-item
          label="邮箱"
          prop="email"
        >
          <el-input
            v-model="registerForm.email"
            placeholder="请输入邮箱"
            clearable
          />
        </el-form-item>
        <el-form-item
          label="角色"
          prop="role"
        >
          <el-radio-group v-model="registerForm.role">
            <el-radio value="user">
              普通用户
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item
          label="密码"
          prop="password"
        >
          <el-input
            v-model="registerForm.password"
            type="password"
            show-password
            placeholder="至少8位，含字母和数字"
          />
        </el-form-item>
        <el-form-item
          label="确认密码"
          prop="confirmPassword"
        >
          <el-input
            v-model="registerForm.confirmPassword"
            type="password"
            show-password
            placeholder="请再次输入密码"
          />
        </el-form-item>

        <el-button
          type="success"
          :loading="loading"
          class="submit-btn"
          @click="handleRegister"
        >
          注册
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getErrorDetail } from '@/utils/errorDetail'
import { validatePasswordBytes } from '@/utils/passwordValidation'
import type { UserInfo } from '@/api/auth'

const loading = ref(false)
const activeTab = ref<'login' | 'register'>('login')

const authStore = useAuthStore()
const router = useRouter()

const isLogin = computed(() => activeTab.value === 'login')

const clearActiveFormValidation = () => {
  // 切换登录/注册页签时清除当前表单校验态，避免错误提示遗留到另一个流程。
  if (isLogin.value) loginFormRef.value?.clearValidate()
  else registerFormRef.value?.clearValidate()
}

const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

const rememberMe = ref(false)
const savedUsername = localStorage.getItem('dws_remember_username')

const loginForm = reactive({
  username: savedUsername || '',
  password: ''
})

const registerForm = reactive({
  username: '',
  nickname: '',
  email: '',
  role: 'user' as const,
  password: '',
  confirmPassword: ''
})

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度需为3~20', trigger: 'blur' },
    { pattern: /^\w+$/, message: '用户名仅支持字母数字下划线', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: ['blur', 'change'] }
  ],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少8位', trigger: 'blur' },
    { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: '密码需包含字母和数字', trigger: 'blur' },
    { validator: validatePasswordBytes, trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入密码不一致'))
          return
        }
        callback()
      },
      trigger: 'blur'
    }
  ]
}

const resolveRoleHome = (role: UserInfo['role'] | '') => {
  if (role === 'admin') return '/admin/dashboard'
  if (role === 'counselor') return '/counselor/dashboard'
  return '/user/dashboard'
}

const goResetPassword = async () => {
  await router.push('/reset-password')
}

const focusPassword = () => {
  const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement
  passwordInput?.focus()
}

const handleLogin = async () => {
  if (!loginFormRef.value) return

  try {
    await loginFormRef.value.validate()
    loading.value = true
    const data = await authStore.login(loginForm.username, loginForm.password)
    if (rememberMe.value) {
      localStorage.setItem('dws_remember_username', loginForm.username)
    } else {
      localStorage.removeItem('dws_remember_username')
    }
    ElMessage.success('登录成功')
    await router.push(resolveRoleHome(data.user.role))
  } catch (error) {
    ElMessage.error(getErrorDetail(error, '登录失败，请检查账号密码'))
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  if (!registerFormRef.value) return

  try {
    await registerFormRef.value.validate()
    loading.value = true
    await authStore.register({
      username: registerForm.username,
      nickname: registerForm.nickname || undefined,
      email: registerForm.email,
      role: registerForm.role,
      password: registerForm.password
    })
    ElMessage.success('注册成功，请使用新账号登录')
    activeTab.value = 'login'
    loginForm.username = registerForm.username
    loginForm.password = ''
    registerFormRef.value.resetFields()
    loginFormRef.value?.clearValidate()
  } catch (error) {
    ElMessage.error(getErrorDetail(error, '注册失败，请稍后重试'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
  background: linear-gradient(140deg, #f3f7ff 0%, #f6fff7 60%, #f7f7ff 100%);
}

.auth-page__bg {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle at 20% 20%, rgba(64, 158, 255, 0.16), transparent 30%),
    radial-gradient(circle at 80% 80%, rgba(103, 194, 58, 0.12), transparent 30%);
  pointer-events: none;
}

.auth-card {
  width: 100%;
  max-width: 480px;
  z-index: 1;
}

.auth-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.auth-card__header h2 {
  margin: 0 0 4px;
  font-size: 20px;
}

.auth-card__header p {
  margin: 0;
  font-size: 13px;
  color: #606266;
}

.auth-tabs {
  margin-bottom: 16px;
}

.submit-btn {
  width: 100%;
  margin-top: 8px;
}

.login-extra-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
</style>
