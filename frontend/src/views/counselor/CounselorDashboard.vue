<template>
  <div class="layout">
    <div class="layout__header">
      <div>
        <h2>咨询师工作台</h2>
        <p>欢迎，{{ auth.user?.nickname || auth.user?.username || '咨询师' }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="success">
          咨询师端
        </el-tag>
        <el-button @click="handleLogout">
          退出登录
        </el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-header">
            <el-icon class="stat-icon warning">
              <Warning />
            </el-icon>
            <h3>今日待处理预警</h3>
          </div>
          <div
            v-if="statsLoading"
            class="stat-loading"
          >
            <el-skeleton
              :rows="1"
              animated
            />
          </div>
          <div
            v-else
            class="stat warning"
          >
            <CountUp
              :end="unhandledCount"
              :duration="1200"
            />
          </div>
          <el-button
            v-if="canHandleWarnings"
            type="warning"
            plain
            @click="router.push('/counselor/warnings')"
          >
            <el-icon><Bell /></el-icon> 进入处理队列
          </el-button>
          <el-tag
            v-else
            type="info"
            size="small"
          >
            无预警处理权限
          </el-tag>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-header">
            <el-icon class="stat-icon primary">
              <User />
            </el-icon>
            <h3>绑定用户数</h3>
          </div>
          <div
            v-if="statsLoading"
            class="stat-loading"
          >
            <el-skeleton
              :rows="1"
              animated
            />
          </div>
          <div
            v-else
            class="stat primary"
          >
            <CountUp
              :end="userCount"
              :duration="1200"
            />
          </div>
          <el-button
            v-if="canViewConsultations"
            type="primary"
            plain
            @click="router.push('/counselor/users')"
          >
            <el-icon><Management /></el-icon> 查看用户列表
          </el-button>
          <el-tag
            v-else
            type="info"
            size="small"
          >
            无用户查看权限
          </el-tag>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-header">
            <el-icon class="stat-icon primary">
              <CopyDocument />
            </el-icon>
            <h3>绑定码</h3>
          </div>
          <div
            v-if="bindCodeLoading"
            class="stat-loading"
          >
            <el-skeleton
              :rows="1"
              animated
            />
          </div>
          <div
            v-else
            class="stat primary bind-code"
          >
            {{ bindCode || '—' }}
          </div>
          <div class="bind-actions">
            <el-button
              v-if="bindCode"
              type="success"
              plain
              size="small"
              @click="copyBindCode"
            >
              <el-icon><CopyDocument /></el-icon> 复制
            </el-button>
            <el-button
              v-if="canViewConsultations"
              plain
              size="small"
              :loading="bindCodeLoading"
              @click="refreshBindCode"
            >
              刷新
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-header">
            <el-icon class="stat-icon success">
              <Management />
            </el-icon>
            <h3>快捷操作</h3>
          </div>
          <div class="quick-actions">
            <el-button
              type="primary"
              plain
              @click="router.push('/counselor/warnings')"
            >
              <el-icon><Warning /></el-icon> 处理预警
            </el-button>
            <el-button
              type="success"
              plain
              @click="router.push('/counselor/users')"
            >
              <el-icon><User /></el-icon> 用户管理
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permission'
import { counselorApi } from '@/api/counselorApi'
import CountUp from '@/components/common/CountUp.vue'
import { Warning, User, CopyDocument, Bell, Management } from '@element-plus/icons-vue'

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
    ElMessage.success('绑定码已刷新')
  } catch {
    ElMessage.error('刷新绑定码失败')
  } finally {
    bindCodeLoading.value = false
  }
}

const copyBindCode = async () => {
  if (!bindCode.value) return
  try {
    await navigator.clipboard.writeText(bindCode.value)
    ElMessage.success('绑定码已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

const handleLogout = async () => {
  await ElMessageBox.confirm('确认退出当前账号吗？', '提示', { type: 'warning' })
  await auth.logout()
  await router.push('/login')
}

onMounted(() => {
  loadStats()
  loadBindCode()
})
</script>

<style scoped>
.layout {
  padding: 24px;
}

.layout__header {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.layout__header h2 {
  margin: 0;
}

.layout__header p {
  margin: 6px 0 0;
  color: #6b7280;
}

.layout__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stat {
  font-size: 32px;
  font-weight: 700;
  margin: 8px 0 14px;
}

.stat.warning {
  color: #e6a23c;
}

.stat.primary {
  color: #409eff;
}

.stat-loading {
  min-height: 50px;
}

.quick-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.stat-card {
  height: 100%;
}

.stat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.stat-header h3 {
  margin: 0;
  font-size: 14px;
  color: #606266;
}

.stat-icon {
  font-size: 18px;
}

.stat-icon.warning {
  color: #e6a23c;
}

.stat-icon.primary {
  color: #409eff;
}

.stat-icon.success {
  color: #67c23a;
}

.bind-code {
  font-size: 24px;
  letter-spacing: 2px;
}

.bind-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
</style>
