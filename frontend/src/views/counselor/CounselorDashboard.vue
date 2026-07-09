<template>
  <div class="layout">
    <div class="layout__header">
      <div>
        <p class="layout__eyebrow">
          <span
            class="layout__eyebrow-dot breathe-dot"
            aria-hidden="true"
          />
          {{ t('counselorDashboard.eyebrow') }}
        </p>
        <h2>{{ t('counselorDashboard.title') }}</h2>
        <p>{{ t('counselorDashboard.lede') }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="success">
          {{ t('counselorDashboard.tagCounselor') }}
        </el-tag>
        <el-button @click="handleLogout">
          {{ t('counselorDashboard.btnLogout') }}
        </el-button>
      </div>
    </div>

    <!-- Bento 统计区：今日预警 Hero + 副卡堆叠（绑定用户数 / 绑定码） -->
    <div class="bento-stats">
      <!-- Hero：今日待处理预警 -->
      <BentoCell
        hero
        shimmer
        :live-dot="unhandledCount > 0 ? 'alert' : 'primary'"
        :title="t('counselorDashboard.heroTitle')"
        class="bento-item"
      >
        <template #actions>
          <el-tag
            v-if="unhandledCount > 0"
            type="danger"
            size="small"
            effect="light"
            round
          >
            {{ t('counselorDashboard.heroTagNeedHandle') }}
          </el-tag>
        </template>
        <div
          v-if="statsLoading"
          class="stat-loading"
        >
          <el-skeleton
            :rows="2"
            animated
          />
        </div>
        <template v-else>
          <div class="stat stat--hero stat--warning tabular-nums">
            <CountUp
              :end="unhandledCount"
              :duration="1200"
            />
            <span class="stat-unit">{{ t('counselorDashboard.heroUnit') }}</span>
          </div>
          <p class="stat-sub">
            {{ t('counselorDashboard.heroSub') }}
          </p>
        </template>
        <template #footer>
          <el-button
            v-if="canHandleWarnings"
            type="warning"
            plain
            class="magnetic-press"
            @click="router.push('/counselor/warnings')"
          >
            <el-icon><Bell /></el-icon> {{ t('counselorDashboard.heroBtnEnterQueue') }}
          </el-button>
          <el-tag
            v-else
            type="info"
            size="small"
          >
            {{ t('counselorDashboard.heroNoPermission') }}
          </el-tag>
        </template>
      </BentoCell>

      <!-- 副卡堆叠：绑定用户数 + 绑定码 -->
      <div class="bento-stat-stack">
        <BentoCell
          shimmer
          :title="t('counselorDashboard.userCountTitle')"
          class="bento-item"
        >
          <template #actions>
            <el-icon class="stat-icon stat-icon--primary">
              <User />
            </el-icon>
          </template>
          <div
            v-if="statsLoading"
            class="stat-loading"
          >
            <el-skeleton
              :rows="1"
              animated
            />
          </div>
          <template v-else>
            <div class="stat stat--primary tabular-nums">
              <CountUp
                :end="userCount"
                :duration="1200"
              />
              <span class="stat-unit">{{ t('counselorDashboard.userCountUnit') }}</span>
            </div>
          </template>
          <template #footer>
            <el-button
              v-if="canViewConsultations"
              type="primary"
              plain
              size="small"
              class="magnetic-press"
              @click="router.push('/counselor/users')"
            >
              <el-icon><Management /></el-icon> {{ t('counselorDashboard.userCountBtnViewList') }}
            </el-button>
            <el-tag
              v-else
              type="info"
              size="small"
            >
              {{ t('counselorDashboard.userCountNoPermission') }}
            </el-tag>
          </template>
        </BentoCell>

        <BentoCell
          shimmer
          :title="t('counselorDashboard.bindCodeTitle')"
          class="bento-item"
        >
          <template #actions>
            <el-icon class="stat-icon stat-icon--primary">
              <CopyDocument />
            </el-icon>
          </template>
          <div
            v-if="bindCodeLoading"
            class="stat-loading"
          >
            <el-skeleton
              :rows="1"
              animated
            />
          </div>
          <template v-else>
            <div class="stat stat--primary bind-code tabular-nums">
              {{ bindCode || '—' }}
            </div>
          </template>
          <template #footer>
            <div class="bind-actions">
              <el-button
                v-if="bindCode"
                type="success"
                plain
                size="small"
                class="magnetic-press"
                @click="copyBindCode"
              >
                <el-icon><CopyDocument /></el-icon> {{ t('counselorDashboard.bindCodeBtnCopy') }}
              </el-button>
              <el-button
                v-if="canViewConsultations"
                plain
                size="small"
                :loading="bindCodeLoading"
                class="magnetic-press"
                @click="refreshBindCode"
              >
                {{ t('counselorDashboard.bindCodeBtnRefresh') }}
              </el-button>
            </div>
          </template>
        </BentoCell>
      </div>
    </div>

    <!-- 第二行：快捷操作（全宽） -->
    <BentoCell
      :title="t('counselorDashboard.quickActionsTitle')"
      class="bento-item"
    >
      <template #actions>
        <el-icon class="stat-icon stat-icon--success">
          <Management />
        </el-icon>
      </template>
      <div class="quick-actions">
        <el-button
          type="primary"
          plain
          class="magnetic-press"
          @click="router.push('/counselor/warnings')"
        >
          <el-icon><Warning /></el-icon> {{ t('counselorDashboard.quickActionHandleWarning') }}
        </el-button>
        <el-button
          type="success"
          plain
          class="magnetic-press"
          @click="router.push('/counselor/users')"
        >
          <el-icon><User /></el-icon> {{ t('counselorDashboard.quickActionUserManagement') }}
        </el-button>
      </div>
    </BentoCell>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/config/permissions'
import { counselorApi } from '@/api/counselorApi'
import CountUp from '@/components/common/CountUp.vue'
import BentoCell from '@/components/common/BentoCell.vue'
import { Warning, User, CopyDocument, Bell, Management } from '@element-plus/icons-vue'

const { t } = useI18n()
const auth = useAuthStore()
const router = useRouter()

const canHandleWarnings = hasPermission(auth.role, 'counselor.warning.handle')
const canViewConsultations = hasPermission(auth.role, 'counselor.user.consultation.view')

const statsLoading = ref(true)
const unhandledCount = ref(0)
const userCount = ref(0)
const bindCodeLoading = ref(false)
const bindCode = ref('')

const loadStats = async () => {
  statsLoading.value = true
  try {
    const [warnings, users] = await Promise.all([counselorApi.getCounselorUnhandledWarningCount(), counselorApi.getCounselorUserCount()])
    unhandledCount.value = warnings
    userCount.value = users
  } catch {
    // keep defaults
  } finally {
    statsLoading.value = false
  }
}

const loadBindCode = async () => {
  bindCodeLoading.value = true
  try {
    const data = await counselorApi.getCounselorBindCode()
    bindCode.value = data.bind_code
  } catch {
    bindCode.value = ''
  } finally {
    bindCodeLoading.value = false
  }
}

const refreshBindCode = async () => {
  bindCodeLoading.value = true
  try {
    const data = await counselorApi.refreshCounselorBindCode()
    bindCode.value = data.bind_code
    ElMessage.success(t('counselorDashboard.bindCodeRefreshed'))
  } catch {
    ElMessage.error(t('counselorDashboard.bindCodeRefreshFailed'))
  } finally {
    bindCodeLoading.value = false
  }
}

const copyBindCode = async () => {
  if (!bindCode.value) return
  try {
    await navigator.clipboard.writeText(bindCode.value)
    ElMessage.success(t('counselorDashboard.bindCodeCopied'))
  } catch {
    ElMessage.error(t('counselorDashboard.bindCodeCopyFailed'))
  }
}

const handleLogout = async () => {
  // P1-F8 修复：原代码无 try/catch，用户取消确认框或 logout API 失败时
  // 会抛出未处理的 Promise rejection，导致控制台报错和用户体验异常。
  try {
    await ElMessageBox.confirm(t('counselorDashboard.logoutConfirm'), t('counselorDashboard.logoutConfirmTitle'), { type: 'warning' })
  } catch {
    // 用户点击取消，静默处理
    return
  }
  try {
    await auth.logout()
  } catch {
    // logout API 失败不阻塞跳转，避免用户被困在当前页面
    ElMessage.warning(t('counselorDashboard.logoutFailed'))
  }
  await router.push('/login')
}

onMounted(() => {
  loadStats()
  loadBindCode()
})
</script>

<style scoped>
.layout {
  padding: var(--spacing-xl);
  max-width: var(--layout-content-max-width);
  margin: 0 auto;
}

/* ===== 头部 ===== */
.layout__header {
  margin-bottom: var(--spacing-2xl);
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--spacing-md);
}

.layout__eyebrow {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.375rem;
  font-family: var(--font-family-mono);
  font-size: var(--font-size-extra-small);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.layout__eyebrow-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success-color);
  box-shadow: 0 0 8px rgba(90, 158, 58, 0.6);
}

.layout__header h2 {
  margin: 0;
  font-family: var(--font-family-display);
  font-size: var(--font-size-stat);
  font-weight: 600;
  letter-spacing: -0.025em;
  line-height: 1.15;
  color: var(--text-primary);
}

.layout__header p {
  margin: 0.375rem 0 0;
  color: var(--text-secondary);
  font-size: var(--font-size-small);
  line-height: var(--line-height-normal);
}

.layout__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}

/* ===== Bento 统计区：Hero（1.3fr）+ 副卡堆叠（2fr） ===== */
.bento-stats {
  display: grid;
  grid-template-columns: 1.3fr 2fr;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.bento-stat-stack {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: var(--spacing-lg);
}

/* ===== 统计数字 ===== */
.stat {
  font-family: var(--font-family-display);
  font-size: var(--font-size-stat);
  font-weight: 700;
  letter-spacing: -0.03em;
  margin: 0.25rem 0 0.5rem;
  line-height: 1;
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
  color: var(--text-primary);
}

.stat--hero {
  font-size: 3.25rem;
}

.stat--warning { color: var(--warning-color); }
.stat--primary { color: var(--primary-color); }

.stat-unit {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-secondary);
  letter-spacing: 0;
}

.stat-sub {
  margin: 0 0 0.5rem;
  font-size: var(--font-size-extra-small);
  color: var(--text-secondary);
}

.stat-loading {
  min-height: 44px;
}

/* 图标 */
.stat-icon {
  font-size: var(--font-size-large);
}

.stat-icon--primary { color: var(--primary-color); }
.stat-icon--success { color: var(--success-color); }

/* 绑定码 */
.bind-code {
  font-size: var(--font-size-stat);
  letter-spacing: 0.15em;
  font-family: var(--font-family-mono);
}

.bind-actions {
  display: flex;
  gap: var(--spacing-sm);
}

/* 快捷操作 */
.quick-actions {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .bento-stats {
    grid-template-columns: 1fr;
  }

  .bento-stat-stack {
    grid-template-rows: auto auto;
  }
}

@media (max-width: 768px) {
  .layout {
    padding: var(--spacing-md);
  }

  .layout__header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }

  .stat {
    font-size: var(--font-size-stat);
  }

  .stat--hero {
    font-size: 2.5rem;
  }
}
</style>
