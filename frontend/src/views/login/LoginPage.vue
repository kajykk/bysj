<template>
  <div class="auth-shell">
    <!-- 左侧品牌面板：非对称分屏（规则 3：DESIGN_VARIANCE>4 禁止居中 Hero） -->
    <AuthBrandPanel
      :headline="[t('auth.brandLoginHeadline1'), t('auth.brandLoginHeadline2')]"
      :lede="t('auth.brandLoginLede')"
      :signals="brandSignals"
    />

    <!-- 右侧表单面板 -->
    <main class="auth-form-panel">
      <div class="auth-form-card">
        <div class="auth-form-card__head">
          <div>
            <p class="auth-form-card__eyebrow">
              {{ isLogin ? t('auth.welcomeBack') : t('auth.createAccount') }}
            </p>
            <h2 class="auth-form-card__title">
              {{ isLogin ? t('auth.loginTitle') : t('auth.joinMindwatch') }}
            </h2>
            <p class="auth-form-card__lede">
              {{ isLogin ? t('auth.brandLoginLede') : t('auth.brandLoginLede') }}
            </p>
          </div>
          <el-tag
            :type="isLogin ? 'primary' : 'success'"
            effect="light"
            round
          >
            {{ isLogin ? t('auth.loginTag') : t('auth.registerTag') }}
          </el-tag>
        </div>

        <el-tabs
          v-model="activeTab"
          class="auth-tabs"
          stretch
          @tab-change="clearActiveFormValidation"
        >
          <el-tab-pane
            name="login"
            :label="t('auth.loginTab')"
          />
          <el-tab-pane
            name="register"
            :label="t('auth.registerTab')"
          />
        </el-tabs>

        <el-form
          v-if="isLogin"
          ref="loginFormRef"
          :model="loginForm"
          :rules="loginRules"
          label-position="top"
          class="auth-form"
          @submit.prevent
        >
          <el-form-item
            :label="t('auth.fieldUsername')"
            prop="username"
            class="auth-field"
          >
            <el-input
              v-model="loginForm.username"
              :placeholder="t('auth.placeholderUsername')"
              clearable
              size="large"
              @keyup.enter="focusPassword"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldPassword')"
            prop="password"
            class="auth-field"
          >
            <el-input
              v-model="loginForm.password"
              type="password"
              show-password
              :placeholder="t('auth.placeholderPassword')"
              size="large"
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <div class="login-extra-actions">
            <el-checkbox
              v-model="rememberMe"
              size="small"
            >
              {{ t('auth.rememberMe') }}
            </el-checkbox>
            <el-button
              link
              type="primary"
              @click="goResetPassword"
            >
              {{ t('auth.forgotPassword') }}
            </el-button>
          </div>

          <el-button
            type="primary"
            :loading="loading"
            class="submit-btn magnetic-press"
            @click="handleLogin"
          >
            {{ t('auth.loginBtn') }}
          </el-button>
        </el-form>

        <el-form
          v-else
          ref="registerFormRef"
          :model="registerForm"
          :rules="registerRules"
          label-position="top"
          class="auth-form"
          @submit.prevent
        >
          <el-form-item
            :label="t('auth.fieldUsername')"
            prop="username"
            class="auth-field"
          >
            <el-input
              v-model="registerForm.username"
              :placeholder="t('auth.placeholderRegisterUsername')"
              clearable
              size="large"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldNickname')"
            prop="nickname"
            class="auth-field"
          >
            <el-input
              v-model="registerForm.nickname"
              :placeholder="t('auth.placeholderNickname')"
              clearable
              size="large"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldEmail')"
            prop="email"
            class="auth-field"
          >
            <el-input
              v-model="registerForm.email"
              :placeholder="t('auth.placeholderEmail')"
              clearable
              size="large"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldRole')"
            prop="role"
            class="auth-field"
          >
            <el-radio-group v-model="registerForm.role">
              <el-radio value="user">
                {{ t('auth.roleUser') }}
              </el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldPassword')"
            prop="password"
            class="auth-field"
          >
            <el-input
              v-model="registerForm.password"
              type="password"
              show-password
              :placeholder="t('auth.placeholderRegisterPassword')"
              size="large"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldConfirmPassword')"
            prop="confirmPassword"
            class="auth-field"
          >
            <el-input
              v-model="registerForm.confirmPassword"
              type="password"
              show-password
              :placeholder="t('auth.placeholderConfirmPassword')"
              size="large"
            />
          </el-form-item>

          <el-button
            type="success"
            :loading="loading"
            class="submit-btn magnetic-press"
            @click="handleRegister"
          >
            {{ t('auth.registerBtn') }}
          </el-button>
        </el-form>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getErrorDetail } from '@/utils/errorDetail'
import { validatePasswordBytes } from '@/utils/passwordValidation'
import type { UserInfo } from '@/types/auth'
import AuthBrandPanel, { type BrandSignal } from '@/components/common/AuthBrandPanel.vue'

const { t } = useI18n()
const loading = ref(false)
const activeTab = ref<'login' | 'register'>('login')

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

const isLogin = computed(() => activeTab.value === 'login')

// 品牌面板信号列表：左侧“Live Status”永动指示器（规则 9-C：The Live Status）
const brandSignals: BrandSignal[] = [
  { key: 'multimodal', label: t('auth.signalMultimodal'), live: true },
  { key: 'realtime', label: t('auth.signalRealtime'), live: true },
  { key: 'intervention', label: t('auth.signalIntervention'), live: false },
]

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
  username: [{ required: true, message: t('auth.ruleRequiredUsername'), trigger: 'blur' }],
  password: [{ required: true, message: t('auth.ruleRequiredPassword'), trigger: 'blur' }]
}

const registerRules: FormRules = {
  username: [
    { required: true, message: t('auth.ruleRequiredUsername'), trigger: 'blur' },
    { min: 3, max: 20, message: t('auth.ruleUsernameLength'), trigger: 'blur' },
    { pattern: /^\w+$/, message: t('auth.ruleUsernamePattern'), trigger: 'blur' }
  ],
  email: [
    { required: true, message: t('auth.ruleRequiredEmail'), trigger: 'blur' },
    { type: 'email', message: t('auth.ruleEmailFormat'), trigger: ['blur', 'change'] }
  ],
  role: [{ required: true, message: t('auth.ruleRequiredRole'), trigger: 'change' }],
  password: [
    { required: true, message: t('auth.ruleRequiredPassword'), trigger: 'blur' },
    { min: 8, message: t('auth.rulePasswordMin'), trigger: 'blur' },
    { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: t('auth.rulePasswordPattern'), trigger: 'blur' },
    { validator: validatePasswordBytes, trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: t('auth.ruleRequiredConfirmPassword'), trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error(t('auth.rulePasswordMismatch')))
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

// R-002 修复：登录成功后恢复原始 URL（含 query/hash），避免复杂页面恢复体验丢失。
// 安全策略：仅允许同源相对路径，拒绝外部 URL（//host、https://、http://）和 /login 自身（避免循环）。
const resolveRedirectTarget = (role: UserInfo['role'] | ''): string => {
  const raw = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  if (!raw) return resolveRoleHome(role)
  // 拒绝外部 URL 与协议相对 URL（防止开放重定向）
  if (/^(https?:)?\/\//i.test(raw)) return resolveRoleHome(role)
  // 拒绝登录页自身（避免循环跳转）
  if (raw === '/login' || raw.startsWith('/login?') || raw.startsWith('/login#')) {
    return resolveRoleHome(role)
  }
  return raw
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
    ElMessage.success(t('auth.loginSuccess'))
    // R-002 修复：优先恢复 redirect 指定的原始 URL，使用 replace 避免登录页留在历史记录。
    await router.replace(resolveRedirectTarget(data.user.role))
  } catch (error) {
    ElMessage.error(getErrorDetail(error, t('auth.loginFailed')))
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
    ElMessage.success(t('auth.registerSuccess'))
    activeTab.value = 'login'
    loginForm.username = registerForm.username
    loginForm.password = ''
    registerFormRef.value.resetFields()
    loginFormRef.value?.clearValidate()
  } catch (error) {
    ElMessage.error(getErrorDetail(error, t('auth.registerFailed')))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ===== 非对称分屏容器（规则 3：DESIGN_VARIANCE=8 禁止居中 Hero） ===== */
.auth-shell {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  min-height: 100dvh;
  background: var(--bg-page);
}

/* ===== 右侧表单面板 ===== */
.auth-form-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3rem 2rem;
  background: var(--bg-primary);
}

.auth-form-card {
  width: 100%;
  max-width: 440px;
  animation: auth-card-in 0.55s var(--transition-ease-out);
}

@keyframes auth-card-in {
  from {
    opacity: 0;
    transform: translateY(16px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.auth-form-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.auth-form-card__eyebrow {
  margin: 0 0 0.375rem;
  font-family: var(--font-family-mono);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.auth-form-card__title {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: 1.625rem;
  font-weight: 600;
  letter-spacing: -0.025em;
  line-height: 1.15;
  color: var(--text-primary);
}

.auth-form-card__lede {
  margin: 0.625rem 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: 1.6;
}

.auth-tabs {
  margin-bottom: 1.25rem;
}

/* 表单字段阶梯式入场（规则 4：Staggered Orchestration） */
.auth-form :deep(.auth-field) {
  animation: field-in 0.45s var(--transition-ease-out) both;
}

.auth-form :deep(.auth-field:nth-child(1)) { animation-delay: 80ms; }
.auth-form :deep(.auth-field:nth-child(2)) { animation-delay: 140ms; }
.auth-form :deep(.auth-field:nth-child(3)) { animation-delay: 200ms; }
.auth-form :deep(.auth-field:nth-child(4)) { animation-delay: 260ms; }
.auth-form :deep(.auth-field:nth-child(5)) { animation-delay: 320ms; }
.auth-form :deep(.auth-field:nth-child(6)) { animation-delay: 380ms; }

@keyframes field-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.submit-btn {
  width: 100%;
  margin-top: 0.5rem;
  height: 46px;
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.01em;
  border-radius: 10px;
}

.login-extra-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
}

/* ===== 响应式：移动端隐藏品牌面板，单列表单 ===== */
/* ISS-085 修复：断点统一为 768px，与全局 useBreakpoint (isMobile < 768px) 保持一致 */
@media (max-width: 768px) {
  .auth-shell {
    grid-template-columns: 1fr;
  }

  .auth-brand {
    display: none;
  }

  .auth-form-panel {
    min-height: 100dvh;
    padding: 2rem 1.25rem;
  }
}

@media (max-width: 480px) {
  .auth-form-card {
    max-width: 100%;
  }
}
</style>
