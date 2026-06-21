<template>
  <div class="layout">
    <div class="layout__header">
      <div>
        <h2>用户仪表盘</h2>
        <p>欢迎回来，{{ auth.user?.nickname || auth.user?.username || '同学' }}</p>
      </div>
      <div class="layout__actions">
        <el-tag type="primary">
          用户端
        </el-tag>
        <el-button @click="handleLogout">
          退出登录
        </el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :span="8">
        <el-card class="dash-card">
          <template #header>
            <span class="card-title">最近测评</span>
          </template>
          <div
            v-if="assessmentLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <EmptyState
            v-else-if="assessmentError"
            title="加载失败"
            :description="assessmentError"
            :image-size="40"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadLatestAssessment"
              >
                重新加载
              </el-button>
            </template>
          </EmptyState>
          <template v-else-if="latestAssessment">
            <div class="stat-row">
              <span class="stat-label">评估类型</span>
              <el-tag size="small">
                {{ assessmentTypeLabel(getAssessmentType(latestAssessment)) }}
              </el-tag>
            </div>
            <div class="stat-row">
              <span class="stat-label">评估时间</span>
              <span class="stat-value">{{ formatDate(latestAssessment.created_at) }}</span>
            </div>
            <el-button
              type="primary"
              plain
              style="margin-top: 12px"
              @click="router.push('/user/risk')"
            >
              开始测评
            </el-button>
          </template>
          <template v-else>
            <EmptyState
              title="暂无记录"
              description="点击开始你的首次心理评估"
              :image-size="40"
            >
              <template #action>
                <el-button
                  type="primary"
                  plain
                  @click="router.push('/user/risk')"
                >
                  开始测评
                </el-button>
              </template>
            </EmptyState>
          </template>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="dash-card">
          <template #header>
            <span class="card-title">风险状态</span>
          </template>
          <div
            v-if="riskLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <EmptyState
            v-else-if="riskError"
            title="加载失败"
            :description="riskError"
            :image-size="40"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadRiskReport"
              >
                重新加载
              </el-button>
            </template>
          </EmptyState>
          <template v-else>
            <div class="risk-score-display">
              <CountUp
                :end="riskReport.risk_score"
                :duration="1500"
                suffix="分"
              />
            </div>
            <el-progress
              :percentage="riskReport.risk_score"
              :color="riskColor"
              :stroke-width="18"
              :text-inside="true"
              :format="(p: number) => p + '分'"
            />
            <div class="risk-meta">
              <el-tag
                :type="severityTagType"
                size="small"
              >
                {{ severityLabel }}
              </el-tag>
              <span class="trend-label">
                趋势：
                <el-icon
                  v-if="riskReport.trend === 'up'"
                  color="#f56c6c"
                ><Top /></el-icon>
                <el-icon
                  v-else-if="riskReport.trend === 'down'"
                  color="#67c23a"
                ><Bottom /></el-icon>
                <span v-else>稳定</span>
              </span>
            </div>
            <p class="risk-advice">
              {{ riskReport.advice?.[0] || '请保持规律作息，持续关注自身状态。' }}
            </p>
          </template>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="dash-card">
          <template #header>
            <span class="card-title">干预计划</span>
          </template>
          <div
            v-if="interventionLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <EmptyState
            v-else-if="interventionError"
            title="加载失败"
            :description="interventionError"
            :image-size="40"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadActiveIntervention"
              >
                重新加载
              </el-button>
            </template>
          </EmptyState>
          <template v-else-if="activeIntervention.plan.id">
            <div class="stat-row">
              <span class="stat-label">方案名称</span>
              <span class="stat-value">{{ activeIntervention.plan.plan_name }}</span>
            </div>
            <el-progress
              :percentage="activeIntervention.plan.progress"
              :stroke-width="12"
              style="margin: 8px 0"
            />
            <div class="stat-row">
              <span class="stat-label">今日任务</span>
              <span class="stat-value">{{ completedTasks }}/{{ activeIntervention.tasks.length }}</span>
            </div>
            <el-button
              type="primary"
              plain
              style="margin-top: 8px"
              @click="router.push('/user/intervention')"
            >
              查看详情
            </el-button>
          </template>
          <template v-else>
            <EmptyState
              title="暂无活跃方案"
              description="完成评估后将为您推荐干预方案"
              :image-size="40"
            >
              <template #action>
                <el-button
                  type="primary"
                  plain
                  @click="router.push('/user/risk')"
                >
                  先进行评估
                </el-button>
              </template>
            </EmptyState>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <el-row
      :gutter="16"
      style="margin-top: 16px"
    >
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="trend-header">
              <span class="card-title">风险趋势</span>
              <el-radio-group
                v-model="trendDays"
                size="small"
                @change="handleTrendDaysChange"
              >
                <el-radio-button :value="7">
                  7天
                </el-radio-button>
                <el-radio-button :value="30">
                  30天
                </el-radio-button>
                <el-radio-button :value="90">
                  90天
                </el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div
            v-if="trendLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="4"
              animated
            />
          </div>
          <EmptyState
            v-else-if="trendError"
            title="加载失败"
            :description="trendError"
            :image-size="60"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadRiskTrend"
              >
                重新加载
              </el-button>
            </template>
          </EmptyState>
          <EmptyState
            v-else-if="!riskTrend.points.length"
            title="暂无趋势数据"
            description="完成更多评估后将生成风险趋势图"
            :image-size="60"
          />
          <div
            v-else
            ref="trendChartRef"
            style="height: 280px"
          />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>
            <span class="card-title">未读预警</span>
          </template>
          <div
            v-if="warningLoading"
            class="card-loading"
          >
            <el-skeleton
              :rows="3"
              animated
            />
          </div>
          <EmptyState
            v-else-if="warningError"
            title="加载失败"
            :description="warningError"
            :image-size="60"
          >
            <template #action>
              <el-button
                type="primary"
                plain
                @click="loadWarnings"
              >
                重新加载
              </el-button>
            </template>
          </EmptyState>
          <template v-else-if="unreadWarnings.length > 0">
            <div
              v-for="w in unreadWarnings.slice(0, 5)"
              :key="w.id"
              class="warning-item"
            >
              <el-tag
                :type="w.risk_level >= 3 ? 'danger' : w.risk_level === 2 ? 'warning' : 'info'"
                size="small"
              >
                {{ w.risk_level >= 3 ? '高' : w.risk_level === 2 ? '中' : '低' }}
              </el-tag>
              <span class="warning-title">{{ w.title }}</span>
              <span class="warning-time">{{ formatDate(w.created_at) }}</span>
            </div>
            <el-button
              type="primary"
              link
              style="margin-top: 8px"
              @click="router.push('/user/warnings')"
            >
              查看全部
            </el-button>
          </template>
          <EmptyState
            v-else
            title="暂无未读预警"
            description="当前没有新的风险预警通知"
            :image-size="60"
          />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Top, Bottom } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { useAuthStore } from '@/stores/auth'
import { userApi } from '@/api/userApi'
import EmptyState from '@/components/common/EmptyState.vue'
import CountUp from '@/components/common/CountUp.vue'
import type { ActiveIntervention, RiskReport, RiskTrend } from '@/api/userRiskApi'
import type { WarningItem, DataHistoryItem } from '@/api/userTypes'
// P2-D 修复：复用 riskFormatters 的 getRiskScoreColor，消除魔法数字
import { getRiskScoreColor } from '@/utils/riskFormatters'

const auth = useAuthStore()
const router = useRouter()

const riskReport = ref<RiskReport>({
  risk_level: 0,
  risk_score: 0,
  severity: 'none',
  trend: 'stable',
  main_factors: [],
  advice: [],
  assessed_at: null
})
const riskLoading = ref(true)
const riskError = ref('')

const activeIntervention = ref<ActiveIntervention>({
  plan: { id: null, plan_name: '暂无活跃方案', risk_level: 0, start_date: null, progress: 0 },
  tasks: []
})
const interventionLoading = ref(true)
const interventionError = ref('')

const riskTrend = ref<RiskTrend>({ days: 30, direction: 'stable', points: [] })
const trendLoading = ref(true)
const trendError = ref('')
const trendDays = ref(30)
const trendChartRef = ref<HTMLElement>()
let trendChart: echarts.ECharts | null = null
const handleTrendResize = () => trendChart?.resize()

const handleTrendDaysChange = async () => {
  await loadRiskTrend()
}

const disposeTrendChart = () => {
  window.removeEventListener('resize', handleTrendResize)
  trendChart?.dispose()
  trendChart = null
}

const unreadWarnings = ref<WarningItem[]>([])
const warningLoading = ref(true)
const warningError = ref('')

const latestAssessment = ref<DataHistoryItem | null>(null)
const assessmentLoading = ref(true)
const assessmentError = ref('')

const completedTasks = computed(() => activeIntervention.value.tasks.filter((t) => t.today_status === 'completed').length)

const riskColor = computed(() => getRiskScoreColor(riskReport.value.risk_score))

const severityLabel = computed(() => {
  const map: Record<string, string> = { none: '无风险', mild: '轻度', moderate: '中度', high: '较高', critical: '严重', unknown: '未知' }
  return map[riskReport.value.severity] || riskReport.value.severity
})

const severityTagType = computed(() => {
  const map: Record<string, string> = { none: 'info', mild: 'success', moderate: 'warning', high: 'danger', critical: 'danger' }
  return (map[riskReport.value.severity] || 'info') as 'info' | 'success' | 'warning' | 'danger'
})

const assessmentTypeLabel = (value: string | null | undefined) => {
  const map: Record<string, string> = {
    structured: '结构化',
    text: '文本',
    physiological: '生理',
    physio: '生理',
    record: '记录',
  }
  return map[value || ''] || '未知'
}

const getAssessmentType = (item: DataHistoryItem | null) => {
  return (item?.data as { assessment_type?: string } | undefined)?.assessment_type
}

const formatDate = (dateStr: string | null | undefined) => {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const escapeHtml = (value: unknown) => {
  if (value === null || value === undefined) return ''
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const loadRiskReport = async () => {
  riskLoading.value = true
  riskError.value = ''
  try {
    riskReport.value = await userApi.getRiskReport()
  } catch {
    riskError.value = '风险状态加载失败'
  } finally {
    riskLoading.value = false
  }
}

const loadActiveIntervention = async () => {
  interventionLoading.value = true
  interventionError.value = ''
  try {
    activeIntervention.value = await userApi.getActiveIntervention()
  } catch {
    interventionError.value = '干预计划加载失败'
  } finally {
    interventionLoading.value = false
  }
}

const loadRiskTrend = async () => {
  trendLoading.value = true
  trendError.value = ''
  try {
    riskTrend.value = await userApi.getRiskTrend(trendDays.value)
  } catch {
    trendError.value = '风险趋势加载失败'
  } finally {
    trendLoading.value = false
    await nextTick()
    if (riskTrend.value.points.length > 0 && !trendError.value) {
      renderTrendChart()
    } else {
      disposeTrendChart()
    }
  }
}

const loadWarnings = async () => {
  warningLoading.value = true
  warningError.value = ''
  try {
    const data = await userApi.getUserWarnings({ page: 1, page_size: 10, is_read: false })
    unreadWarnings.value = data.items
  } catch {
    warningError.value = '未读预警加载失败'
  } finally {
    warningLoading.value = false
  }
}

const loadLatestAssessment = async () => {
  assessmentLoading.value = true
  assessmentError.value = ''
  try {
    const data = await userApi.getDataHistory({ page: 1, page_size: 1 })
    latestAssessment.value = data.items[0] || null
  } catch {
    assessmentError.value = '最近测评加载失败'
  } finally {
    assessmentLoading.value = false
  }
}

const loadDashboard = async () => {
  await Promise.allSettled([
    loadRiskReport(),
    loadActiveIntervention(),
    loadRiskTrend(),
    loadWarnings(),
    loadLatestAssessment()
  ])
  const errors = [riskError.value, interventionError.value, trendError.value, warningError.value, assessmentError.value].filter(Boolean)
  if (errors.length > 0) {
    ElMessage.warning('仪表盘部分数据加载失败，请稍后重试')
  }
}

const renderTrendChart = () => {
  if (!trendChartRef.value) return
  if (!trendChart) {
    trendChart = echarts.init(trendChartRef.value)
    window.addEventListener('resize', handleTrendResize)
  }
  const points = riskTrend.value.points
  const riskLevelMap: Record<number, string> = { 0: '无风险', 1: '低风险', 2: '中风险', 3: '高风险', 4: '严重' }
  const trendMap: Record<string, string> = { up: '上升', down: '下降', stable: '稳定' }

  trendChart.setOption({
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#e4e7ed',
      borderWidth: 1,
      textStyle: { color: '#303133', fontSize: 13 },
      extraCssText: 'box-shadow: 0 2px 12px 0 rgba(0,0,0,0.1); border-radius: 4px;',
      formatter: (params: unknown) => {
        const p = (params as Array<{ dataIndex: number }>)[0]
        const point = points[p.dataIndex]
        if (!point) return ''
        const levelText = riskLevelMap[point.risk_level] || '未知'
        const trendText = trendMap[riskTrend.value.direction] || '稳定'
        const date = escapeHtml(point.date)
        const score = escapeHtml(point.risk_score)
        const level = escapeHtml(levelText)
        const trend = escapeHtml(trendText)
        return `<div style="padding: 4px 2px;">
          <div style="font-weight:600;margin-bottom:6px;color:#303133;">${date}</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#f56c6c;"></span>
            <span>风险分数：<strong>${score}分</strong></span>
          </div>
          <div style="margin-bottom:4px;padding-left:16px;">风险等级：<span style="color:#f56c6c;font-weight:500;">${level}</span></div>
          <div style="padding-left:16px;color:#909399;font-size:12px;">整体趋势：${trend}</div>
        </div>`
      }
    },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: points.map((p) => p.date), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { fontSize: 11 } },
    series: [{
      type: 'line',
      data: points.map((p) => p.risk_score),
      smooth: true,
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(245,108,108,0.3)' },
        { offset: 1, color: 'rgba(245,108,108,0.02)' }
      ]) },
      lineStyle: { color: '#f56c6c', width: 2 },
      itemStyle: { color: '#f56c6c' },
      emphasis: {
        itemStyle: { borderWidth: 2, borderColor: '#fff', shadowBlur: 8, shadowColor: 'rgba(245,108,108,0.5)' },
        scale: 1.5
      }
    }]
  })
}

const handleLogout = async () => {
  try {
    await ElMessageBox.confirm('确认退出当前账号吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await auth.logout()
  await router.push('/login')
}

onMounted(() => {
  loadDashboard()
})

onUnmounted(() => {
  disposeTrendChart()
})
</script>

<style scoped>
.layout {
  padding: 16px;
}

.layout__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.layout__actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.dash-card {
  min-height: 200px;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
}

.card-loading {
  padding: 16px 0;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.stat-label {
  font-size: 13px;
  color: #606266;
}

.stat-value {
  font-size: 13px;
  font-weight: 500;
}

.risk-score-display {
  font-size: 32px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  text-align: center;
  margin-bottom: 12px;
}

.risk-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
}

.trend-label {
  font-size: 12px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 4px;
}

.risk-advice {
  font-size: 12px;
  color: #606266;
  margin-top: 8px;
  line-height: 1.5;
}

.warning-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #f0f2f5;
}

.warning-title {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.warning-time {
  font-size: 12px;
  color: #909399;
}
</style>
