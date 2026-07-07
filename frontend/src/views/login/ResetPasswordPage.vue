<template>
  <div class="auth-shell">
    <!-- 左侧品牌面板：与登录页共享视觉语言 -->
    <AuthBrandPanel
      :headline="[t('auth.brandResetHeadline1'), t('auth.brandResetHeadline2')]"
      :lede="t('auth.brandResetLede')"
      :signals="brandSignals"
      :foot-status="t('auth.brandResetFootStatus')"
    />

    <!-- 右侧表单面板 -->
    <main class="auth-form-panel">
      <div class="auth-form-card">
        <div class="auth-form-card__head">
          <div>
            <p class="auth-form-card__eyebrow">
              {{ t('auth.resetEyebrow') }}
            </p>
            <h2 class="auth-form-card__title">
              {{ t('auth.resetTitle') }}
            </h2>
          </div>
          <el-tag
            type="warning"
            effect="light"
            round
          >
            {{ t('auth.resetTag') }}
          </el-tag>
        </div>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="auth-form"
          @submit.prevent
        >
          <el-form-item
            :label="t('auth.fieldEmail')"
            prop="email"
            class="auth-field"
          >
            <el-input
              v-model="form.email"
              :placeholder="t('auth.placeholderEmail')"
              clearable
              size="large"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldResetToken')"
            prop="reset_token"
            class="auth-field"
          >
            <el-input
              v-model="form.reset_token"
              type="textarea"
              :rows="3"
              :placeholder="t('auth.placeholderResetToken')"
            />
          </el-form-item>
          <el-form-item
            :label="t('auth.fieldNewPassword')"
            prop="new_password"
            class="auth-field"
          >
            <el-input
              v-model="form.new_password"
              type="password"
              show-password
              :placeholder="t('auth.placeholderNewPassword')"
              size="large"
            />
          </el-form-item>

          <el-button
            type="primary"
            :loading="loading"
            class="submit-btn magnetic-press"
            @click="handleSubmit"
          >
            {{ t('auth.confirmResetBtn') }}
          </el-button>

          <el-button
            link
            type="primary"
            class="back-link"
            @click="router.push('/login')"
          >
            {{ t('auth.backToLogin') }}
          </el-button>
        </el-form>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { authApi } from '@/api/auth'
import { getErrorDetail } from '@/utils/errorDetail'
import { validatePasswordBytes } from '@/utils/passwordValidation'
import AuthBrandPanel, { type BrandSignal } from '@/components/common/AuthBrandPanel.vue'

const { t } = useI18n()
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
    { required: true, message: t('auth.ruleRequiredEmail'), trigger: 'blur' },
    { type: 'email', message: t('auth.ruleEmailFormat'), trigger: ['blur', 'change'] }
  ],
  reset_token: [{ required: true, message: t('auth.ruleRequiredResetToken'), trigger: 'blur' }],
  new_password: [
    { required: true, message: t('auth.ruleRequiredNewPassword'), trigger: 'blur' },
    { min: 8, message: t('auth.rulePasswordMin'), trigger: 'blur' },
    { pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/, message: t('auth.rulePasswordPattern'), trigger: 'blur' },
    { validator: validatePasswordBytes, trigger: 'blur' }
  ]
}

// 品牌面板信号列表：重置场景的安全提示
const brandSignals: BrandSignal[] = [
  { key: 'token', label: t('auth.signalToken'), live: true },
  { key: 'strong', label: t('auth.signalStrong'), live: false },
  { key: 'safe', label: t('auth.signalSafe'), live: true },
]

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
    ElMessage.success(t('auth.resetSuccess'))
    await router.push('/login')
  } catch (error) {
    ElMessage.error(getErrorDetail(error, t('auth.resetFailed')))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ===== 非对称分屏容器（与登录页一致） ===== */
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
  margin-bottom: 1.75rem;
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

/* 表单字段阶梯式入场（规则 4：Staggered Orchestration） */
.auth-form :deep(.auth-field) {
  animation: field-in 0.45s var(--transition-ease-out) both;
}

.auth-form :deep(.auth-field:nth-child(1)) { animation-delay: 80ms; }
.auth-form :deep(.auth-field:nth-child(2)) { animation-delay: 140ms; }
.auth-form :deep(.auth-field:nth-child(3)) { animation-delay: 200ms; }

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

.back-link {
  width: 100%;
  margin-top: 0.75rem;
  height: 36px;
}

/* ===== 响应式：移动端隐藏品牌面板，单列表单 ===== */
/* ISS-085 修复：断点统一为 768px，与全局 useBreakpoint (isMobile < 768px) 保持一致 */
@media (max-width: 768px) {
  .auth-shell {
    grid-template-columns: 1fr;
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
