<template>
  <div class="layout">
    <div class="layout__header">
      <div>
        <h2>管理员工作台</h2>
        <p>欢迎，{{ auth.user?.nickname || auth.user?.username || '管理员' }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="danger">
          管理员端
        </el-tag>
        <el-button @click="handleLogout">
          退出登录
        </el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-label">
            注册用户
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
            {{ stats.total_users }}
          </div>
          <div class="stat-trend">
            <el-tag
              :type="userTrend >= 0 ? 'success' : 'danger'"
              size="small"
              effect="plain"
            >
              <el-icon><ArrowUp v-if="userTrend >= 0" /><ArrowDown v-else /></el-icon>
              {{ Math.abs(userTrend) }}%
            </el-tag>
            <span class="trend-label">环比昨日</span>
          </div>
          <span class="stat-sub">咨询师 {{ stats.total_counselors }} 人</span>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-label">
            今日预警
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
            {{ stats.today_warnings }}
          </div>
          <div class="stat-trend">
            <el-tag
              :type="warningTrend <= 0 ? 'success' : 'danger'"
              size="small"
              effect="plain"
            >
              <el-icon><ArrowUp v-if="warningTrend >= 0" /><ArrowDown v-else /></el-icon>
              {{ Math.abs(warningTrend) }}%
            </el-tag>
            <span class="trend-label">环比昨日</span>
          </div>
          <span class="stat-sub">未处理 {{ stats.today_unhandled_warnings }} 条</span>
          <el-button
            type="warning"
            link
            @click="router.push('/admin/operation-logs')"
          >
            查看日志
          </el-button>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-label">
            评估总量
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
            class="stat danger"
          >
            {{ stats.total_assessments }}
          </div>
          <div class="stat-trend">
            <el-tag
              :type="assessmentTrend >= 0 ? 'success' : 'danger'"
              size="small"
              effect="plain"
            >
              <el-icon><ArrowUp v-if="assessmentTrend >= 0" /><ArrowDown v-else /></el-icon>
              {{ Math.abs(assessmentTrend) }}%
            </el-tag>
            <span class="trend-label">环比昨日</span>
          </div>
          <span class="stat-sub">高风险用户 {{ stats.high_risk_users }} 人</span>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card">
          <div class="stat-label">
            干预模板
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
            class="stat success"
          >
            {{ stats.active_templates }}/{{ stats.total_templates }}
          </div>
          <div class="stat-trend">
            <el-tag
              :type="templateTrend >= 0 ? 'success' : 'danger'"
              size="small"
              effect="plain"
            >
              <el-icon><ArrowUp v-if="templateTrend >= 0" /><ArrowDown v-else /></el-icon>
              {{ Math.abs(templateTrend) }}%
            </el-tag>
            <span class="trend-label">环比昨日</span>
          </div>
          <el-button
            type="success"
            link
            @click="router.push('/admin/templates')"
          >
            管理模板
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <el-row
      :gutter="16"
      style="margin-top: 16px"
    >
      <el-col :span="12">
        <el-card>
          <template #header>
            <span class="card-title">快捷操作</span>
          </template>
          <div class="quick-actions">
            <el-button
              type="primary"
              @click="router.push('/admin/templates')"
            >
              模板管理
            </el-button>
            <el-button
              type="warning"
              @click="router.push('/admin/settings')"
            >
              系统设置
            </el-button>
            <el-button
              type="info"
              @click="router.push('/admin/operation-logs')"
            >
              操作日志
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">系统状态</span>
              <el-button
                type="primary"
                link
                size="small"
                @click="router.push('/admin/settings')"
              >
                查看配置
              </el-button>
            </div>
          </template>
          <div
            v-if="healthLoading"
            style="padding: 20px"
          >
            <el-skeleton
              :rows="3"
              animated
            />
          </div>
          <template v-else>
            <el-result
              :icon="systemHealthy ? 'success' : 'warning'"
              :title="systemHealthy ? '服务运行正常' : '部分服务异常'"
              :sub-title="systemHealthy ? '所有核心服务运行正常' : '请检查系统配置'"
            />
            <el-divider />
            <div class="component-list">
              <div
                v-for="comp in componentStatus"
                :key="comp.name"
                class="component-item"
              >
                <div class="component-info">
                  <el-icon
                    :size="16"
                    :color="comp.healthy ? '#67c23a' : '#f56c6c'"
                  >
                    <CircleCheck v-if="comp.healthy" />
                    <CircleClose v-else />
                  </el-icon>
                  <span class="component-name">{{ comp.name }}</span>
                </div>
                <el-tag
                  :type="comp.healthy ? 'success' : 'danger'"
                  size="small"
                >
                  {{ comp.healthy ? '正常' : '异常' }}
                </el-tag>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { adminApi } from '@/api/adminApi'
import { ArrowUp, ArrowDown, CircleCheck, CircleClose } from '@element-plus/icons-vue'

const auth = useAuthStore()
const router = useRouter()

const statsLoading = ref(true)
const healthLoading = ref(true)
const systemHealthy = ref(true)
const stats = reactive({
  total_users: 0,
  total_counselors: 0,
  today_warnings: 0,
  today_unhandled_warnings: 0,
  total_assessments: 0,
  high_risk_users: 0,
  total_templates: 0,
  active_templates: 0,
  yesterday_users: 0,
  yesterday_warnings: 0,
  yesterday_assessments: 0,
  yesterday_templates: 0,
})

const userTrend = computed(() => {
  if (stats.yesterday_users === 0) return 0
  return Math.round(((stats.total_users - stats.yesterday_users) / stats.yesterday_users) * 100)
})

const warningTrend = computed(() => {
  if (stats.yesterday_warnings === 0) return 0
  return Math.round(((stats.today_warnings - stats.yesterday_warnings) / stats.yesterday_warnings) * 100)
})

const assessmentTrend = computed(() => {
  if (stats.yesterday_assessments === 0) return 0
  return Math.round(((stats.total_assessments - stats.yesterday_assessments) / stats.yesterday_assessments) * 100)
})

const templateTrend = computed(() => {
  if (stats.yesterday_templates === 0) return 0
  return Math.round(((stats.active_templates - stats.yesterday_templates) / stats.yesterday_templates) * 100)
})

const componentStatus = ref([
  { name: 'API 服务', healthy: true },
  { name: '数据库', healthy: true },
  { name: 'Redis 缓存', healthy: true },
  { name: '消息队列', healthy: true },
  { name: '文件存储', healthy: true },
])

const loadStats = async () => {
  statsLoading.value = true
  try {
    const data = await adminApi.getAdminStats()
    Object.assign(stats, data)
  } catch {
    // keep defaults
  } finally {
    statsLoading.value = false
  }
}

const checkHealth = async () => {
  healthLoading.value = true
  try {
    const data = await adminApi.getHealthStatus()
    systemHealthy.value = data.status === 'ok'
    const checks = data.checks || {}
    // /health 接口返回的 checks 字段映射到组件状态；
    // API 服务能否拿到响应即代表其健康；文件存储不在 /health 检查范围内，保持默认健康
    const keyMap: Record<string, string> = {
      '数据库': 'database',
      'Redis 缓存': 'redis',
      '消息队列': 'celery_worker',
    }
    componentStatus.value = componentStatus.value.map((comp) => {
      const key = keyMap[comp.name]
      if (!key) return comp
      return { ...comp, healthy: checks[key] === 'ok' }
    })
  } catch {
    systemHealthy.value = false
    componentStatus.value = componentStatus.value.map((comp) => ({ ...comp, healthy: false }))
  } finally {
    healthLoading.value = false
  }
}

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确认退出登录吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await auth.logout()
  await router.push('/login')
}

onMounted(() => {
  loadStats()
  checkHealth()
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

.stat-card {
  text-align: center;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-bottom: 4px;
}

.stat {
  font-size: 32px;
  font-weight: 700;
  margin: 4px 0 4px;
}

.stat.primary {
  color: #409eff;
}

.stat.warning {
  color: #e6a23c;
}

.stat.danger {
  color: #f56c6c;
}

.stat.success {
  color: #67c23a;
}

.stat-sub {
  font-size: 12px;
  color: #c0c4cc;
}

.stat-loading {
  min-height: 44px;
}

.card-title {
  font-weight: 600;
}

.quick-actions {
  display: flex;
  gap: 8px;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-trend {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 6px 0;
}

.trend-label {
  font-size: 12px;
  color: #909399;
}

.component-list {
  padding: 0 20px 20px;
}

.component-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}

.component-item:last-child {
  border-bottom: none;
}

.component-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.component-name {
  font-size: 14px;
  color: #606266;
}
</style>
