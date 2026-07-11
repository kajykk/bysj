<template>
  <div class="monitoring-dashboard">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>{{ $t('monitoring.title') }}</h1>
      <div class="header-actions">
        <el-radio-group
          v-model="timeRange"
          size="small"
          @change="handleTimeRangeChange"
        >
          <el-radio-button label="1h">
            {{ $t('monitoring.timeRange.hour1') }}
          </el-radio-button>
          <el-radio-button label="6h">
            {{ $t('monitoring.timeRange.hour6') }}
          </el-radio-button>
          <el-radio-button label="24h">
            {{ $t('monitoring.timeRange.hour24') }}
          </el-radio-button>
          <el-radio-button label="7d">
            {{ $t('monitoring.timeRange.day7') }}
          </el-radio-button>
        </el-radio-group>
        <el-button
          :icon="Refresh"
          size="small"
          :loading="isRefreshing"
          @click="refreshData"
        >
          {{ $t('monitoring.refresh') }}
        </el-button>
        <el-switch
          v-model="autoRefresh"
          :active-text="$t('monitoring.autoRefresh')"
          size="small"
        />
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row
      :gutter="16"
      class="stat-cards"
    >
      <el-col
        :xs="24"
        :sm="12"
        :md="6"
      >
        <el-card class="stat-card">
          <div
            class="stat-value"
            :class="getSuccessRateClass"
          >
            {{ formatPercent(metrics.modelSuccessRate) }}
          </div>
          <div class="stat-label">
            {{ $t('monitoring.modelSuccessRate') }}
          </div>
          <TrendArrow :value="metrics.successRateDelta" />
        </el-card>
      </el-col>
      <el-col
        :xs="24"
        :sm="12"
        :md="6"
      >
        <el-card class="stat-card">
          <div
            class="stat-value"
            :class="getFallbackRateClass"
          >
            {{ formatPercent(metrics.fallbackRate) }}
          </div>
          <div class="stat-label">
            {{ $t('monitoring.fallbackRate') }}
          </div>
          <TrendArrow :value="-metrics.fallbackRateDelta" />
        </el-card>
      </el-col>
      <el-col
        :xs="24"
        :sm="12"
        :md="6"
      >
        <el-card class="stat-card">
          <div class="stat-value">
            {{ formatNumber(metrics.avgLatency) }}ms
          </div>
          <div class="stat-label">
            {{ $t('monitoring.avgLatency') }}
          </div>
          <TrendArrow :value="-metrics.latencyDelta" />
        </el-card>
      </el-col>
      <el-col
        :xs="24"
        :sm="12"
        :md="6"
      >
        <el-card class="stat-card">
          <div class="stat-value">
            {{ formatNumber(metrics.requestCount) }}
          </div>
          <div class="stat-label">
            {{ $t('monitoring.requestCount') }}
          </div>
          <TrendArrow :value="metrics.requestCountDelta" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row
      :gutter="16"
      class="chart-section"
    >
      <el-col
        :xs="24"
        :lg="12"
      >
        <el-card>
          <SystemHealthChart
            :data="healthData"
            height="350px"
            :title="$t('monitoring.title')"
          />
        </el-card>
      </el-col>
      <el-col
        :xs="24"
        :lg="12"
      >
        <el-card>
          <RiskTrendChart
            :data="riskTrendData"
            height="350px"
            :show-bounds="true"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 漂移告警列表 -->
    <el-card class="alert-section">
      <template #header>
        <div class="card-header">
          <span>{{ $t('monitoring.driftAlerts') }}</span>
          <el-tag
            v-if="activeAlerts.length > 0"
            type="danger"
          >
            {{ activeAlerts.length }} {{ $t('monitoring.recentAlerts') }}
          </el-tag>
        </div>
      </template>

      <el-skeleton
        v-if="loading"
        :rows="5"
        animated
      />

      <el-table
        v-else
        :data="activeAlerts"
        style="width: 100%"
      >
        <el-table-column
          prop="severity"
          :label="$t('monitoring.alertLevel')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)">
              {{ $t(`monitoring.alertLevel.${row.severity.toLowerCase()}`) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="message"
          :label="$t('monitoring.driftAlerts')"
        />
        <el-table-column
          prop="modelVersion"
          label="模型版本"
          width="120"
        />
        <el-table-column
          prop="createdAt"
          :label="$t('report.createdAt')"
          width="180"
        >
          <template #default="{ row }">
            {{ formatDate(row.createdAt) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="status"
          :label="$t('monitoring.alertStatus')"
          width="100"
        >
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ $t(`monitoring.alertStatus.${row.status.toLowerCase()}`) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import SystemHealthChart from '@/components/charts/SystemHealthChart.vue'
import RiskTrendChart from '@/components/charts/RiskTrendChart.vue'
import TrendArrow from '@/components/common/TrendArrow.vue'

interface AlertItem {
  id: number
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  message: string
  modelVersion: string
  createdAt: string
  status: 'TRIGGERED' | 'ACKNOWLEDGED' | 'RESOLVED' | 'CLOSED'
}

interface HealthDataPoint {
  time: string
  successRate: number
  fallbackRate: number
  latency: number
}

interface RiskDataPoint {
  date: string
  value: number
  upperBound?: number
  lowerBound?: number
}

// 状态
const loading = ref(false)
const isRefreshing = ref(false)
const autoRefresh = ref(false)
const timeRange = ref('1h')
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null)

// 指标数据
const metrics = ref({
  modelSuccessRate: 0.985,
  successRateDelta: 0.02,
  fallbackRate: 0.015,
  fallbackRateDelta: -0.005,
  avgLatency: 145,
  latencyDelta: -20,
  requestCount: 12580,
  requestCountDelta: 0.15,
})

// 健康数据
const healthData = ref<HealthDataPoint[]>([])

// 风险趋势数据
const riskTrendData = ref<RiskDataPoint[]>([])

// 告警列表
const activeAlerts = ref<AlertItem[]>([])

// 计算属性
const getSuccessRateClass = computed(() => ({
  'text-success': metrics.value.modelSuccessRate >= 0.95,
  'text-warning': metrics.value.modelSuccessRate >= 0.9 && metrics.value.modelSuccessRate < 0.95,
  'text-danger': metrics.value.modelSuccessRate < 0.9,
}))

const getFallbackRateClass = computed(() => ({
  'text-success': metrics.value.fallbackRate <= 0.02,
  'text-warning': metrics.value.fallbackRate > 0.02 && metrics.value.fallbackRate <= 0.05,
  'text-danger': metrics.value.fallbackRate > 0.05,
}))

// 方法
const formatPercent = (value: number): string => {
  return `${(value * 100).toFixed(1)}%`
}

const formatNumber = (value: number): string => {
  if (value >= 10000) {
    return `${(value / 10000).toFixed(1)}w`
  }
  return value.toLocaleString()
}

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleString('zh-CN')
}

const getSeverityType = (severity: string): 'danger' | 'warning' | 'info' | 'success' | 'primary' => {
  const map: Record<string, 'danger' | 'warning' | 'info' | 'success' | 'primary'> = {
    CRITICAL: 'danger',
    HIGH: 'warning',
    MEDIUM: 'info',
    LOW: 'info',
  }
  return map[severity] || 'info'
}

const getStatusType = (status: string): 'danger' | 'warning' | 'info' | 'success' | 'primary' => {
  const map: Record<string, 'danger' | 'warning' | 'info' | 'success' | 'primary'> = {
    TRIGGERED: 'danger',
    ACKNOWLEDGED: 'warning',
    RESOLVED: 'success',
    CLOSED: 'info',
  }
  return map[status] || 'info'
}

// 生成模拟数据
const generateMockData = () => {
  // 生成健康数据
  const now = new Date()
  healthData.value = Array.from({ length: 12 }, (_, i) => {
    const time = new Date(now.getTime() - (11 - i) * 5 * 60 * 1000)
    return {
      time: `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`,
      successRate: 95 + Math.random() * 5,
      fallbackRate: Math.random() * 3,
      latency: 100 + Math.random() * 100,
    }
  })

  // 生成风险趋势数据
  riskTrendData.value = Array.from({ length: 30 }, (_, i) => {
    const date = new Date(now.getTime() - (29 - i) * 24 * 60 * 60 * 1000)
    const value = 0.2 + Math.random() * 0.3
    return {
      date: `${date.getMonth() + 1}/${date.getDate()}`,
      value,
      upperBound: 0.6,
      lowerBound: 0.1,
    }
  })

  // 生成告警数据
  activeAlerts.value = [
    {
      id: 1,
      severity: 'HIGH',
      message: '检测到模型输入分布漂移，PSI = 0.35',
      modelVersion: 'v2.1.0',
      createdAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      status: 'TRIGGERED',
    },
    {
      id: 2,
      severity: 'MEDIUM',
      message: '模型延迟超过阈值，P99 = 520ms',
      modelVersion: 'v2.1.0',
      createdAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      status: 'ACKNOWLEDGED',
    },
    {
      id: 3,
      severity: 'LOW',
      message: '回退率轻微上升，当前 2.1%',
      modelVersion: 'v2.0.5',
      createdAt: new Date(Date.now() - 6 * 60 * 60 * 1000).toISOString(),
      status: 'RESOLVED',
    },
  ]
}

// 刷新数据
const refreshData = async () => {
  isRefreshing.value = true
  loading.value = true

  try {
    // 模拟 API 调用
    await new Promise((resolve) => setTimeout(resolve, 500))
    generateMockData()
  } finally {
    isRefreshing.value = false
    loading.value = false
  }
}

const handleTimeRangeChange = () => {
  refreshData()
}

// 自动刷新
watch(autoRefresh, (val) => {
  if (val) {
    refreshTimer.value = setInterval(() => {
      refreshData()
    }, 5000)
  } else {
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value)
      refreshTimer.value = null
    }
  }
})

onMounted(() => {
  generateMockData()
})

onUnmounted(() => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
  }
})
</script>

<style scoped>
.monitoring-dashboard {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 12px;
}

.page-header h1 {
  margin: 0;
  font-size: var(--font-size-display);
  font-weight: var(--font-weight-bold);
  letter-spacing: var(--letter-spacing-tight);
  line-height: var(--line-height-tight);
  color: var(--text-primary);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.stat-cards {
  margin-bottom: 20px;
}

.stat-card {
  text-align: center;
  padding: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: var(--info-color);
  margin-bottom: 8px;
}

.text-success {
  color: var(--success-color);
}

.text-warning {
  color: var(--warning-color);
}

.text-danger {
  color: var(--danger-color);
}

.chart-section {
  margin-bottom: 20px;
}

.chart-section .el-col {
  margin-bottom: 16px;
}

.alert-section {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
  }

  .stat-value {
    font-size: 22px;
  }
}
</style>
