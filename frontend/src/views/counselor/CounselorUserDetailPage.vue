<template>
  <ListPageScaffold
    :title="t('counselorUserDetail.pageTitle', { name: userDisplayName })"
    :loading="loading"
    :empty="!loading && !user"
    :error-message="pageError"
    :empty-text="t('counselorUserDetail.emptyText')"
    @retry="fetchAll"
  >
    <template #header-extra>
      <el-button @click="goBack">
        {{ t('counselorUserDetail.btnBack') }}
      </el-button>
    </template>

    <el-descriptions
      v-if="user"
      :column="descColumn"
      border
      class="user-descriptions"
    >
      <el-descriptions-item :label="t('counselorUserDetail.descUserId')">
        {{ user.id }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('counselorUserDetail.descUsername')">
        {{ user.username }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('counselorUserDetail.descNickname')">
        {{ user.nickname || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('counselorUserDetail.descEmail')">
        {{ user.email || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('counselorUserDetail.descStatus')">
        {{ user.status || '-' }}
      </el-descriptions-item>
    </el-descriptions>

    <el-tabs v-model="tab">
      <el-tab-pane
        :label="t('counselorUserDetail.tabConsultations')"
        name="records"
      >
        <div class="toolbar">
          <el-button
            v-if="canConsult"
            type="primary"
            @click="openCreate"
          >
            {{ t('counselorUserDetail.btnNewConsultation') }}
          </el-button>
        </div>
        <el-table
          v-loading="consultationLoading"
          :data="consultationRows"
          border
        >
          <el-table-column
            prop="id"
            :label="t('counselorUserDetail.consultationColId')"
            width="100"
          />
          <el-table-column
            prop="main_topics"
            :label="t('counselorUserDetail.consultationColTopics')"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column
            prop="client_status"
            :label="t('counselorUserDetail.consultationColStatus')"
            min-width="160"
            show-overflow-tooltip
          />
          <el-table-column
            prop="interventions"
            :label="t('counselorUserDetail.consultationColInterventions')"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column
            prop="next_plan"
            :label="t('counselorUserDetail.consultationColNextPlan')"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column
            prop="created_at"
            :label="t('counselorUserDetail.consultationColTime')"
            min-width="180"
          />
          <el-table-column
            :label="t('counselorUserDetail.consultationColOperation')"
            width="140"
          >
            <template #default="{ row }">
              <ActionColumn
                v-if="canConsult"
                :label="t('counselorUserDetail.btnEdit')"
                show-audit
                @action="openEdit(row)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane
        :label="t('counselorUserDetail.tabGroups')"
        name="groups"
      >
        <div class="toolbar">
          <el-button
            v-if="canConsult"
            type="primary"
            @click="openCreateGroup"
          >
            {{ t('counselorUserDetail.btnNewGroup') }}
          </el-button>
        </div>
        <el-table
          v-loading="groupLoading"
          :data="groupRows"
          border
        >
          <el-table-column
            prop="id"
            :label="t('counselorUserDetail.groupColId')"
            width="100"
          />
          <el-table-column
            prop="group_name"
            :label="t('counselorUserDetail.groupColName')"
            min-width="180"
          />
          <el-table-column
            prop="description"
            :label="t('counselorUserDetail.groupColDescription')"
            min-width="220"
          />
          <el-table-column
            prop="user_count"
            :label="t('counselorUserDetail.groupColUserCount')"
            width="120"
          />
          <el-table-column
            :label="t('counselorUserDetail.groupColOperation')"
            width="200"
          >
            <template #default="{ row }">
              <ActionColumn
                v-if="canConsult"
                :label="t('counselorUserDetail.btnAddCurrentUser')"
                type="primary"
                show-audit
                @action="addCurrentUserToGroup(row)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- UX-P3-02 修复：风险轨迹改时间线视图，替代原纯表格，突出时间顺序 -->
      <el-tab-pane
        :label="t('counselorUserDetail.tabRiskHistory')"
        name="risk_history"
      >
        <el-timeline
          v-loading="loading"
          class="detail-timeline"
        >
          <el-timeline-item
            v-for="item in riskHistoryRows"
            :key="item.id"
            :type="getRiskTimelineType(item)"
            :timestamp="item.created_at"
            placement="top"
          >
            <div class="timeline-title">
              <el-tag
                size="small"
                :type="getWarningRiskLevelTagType(item.risk_level ?? 0)"
              >
                {{ getWarningRiskLevelLabel(item.risk_level ?? 0) }}
              </el-tag>
            </div>
            <div class="timeline-text">
              {{ t('counselorUserDetail.historyColRiskScore') }}: {{ item.risk_score }}
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty
          v-if="!loading && !riskHistoryRows.length"
          :description="t('common.noData')"
        />
      </el-tab-pane>

      <!-- ISS-057: 评估记录 -->
      <el-tab-pane
        :label="t('counselorUserDetail.tabAssessments')"
        name="assessments"
      >
        <el-table
          :data="assessmentRows"
          border
        >
          <el-table-column
            prop="id"
            :label="t('counselorUserDetail.assessmentColId')"
            width="100"
          />
          <el-table-column
            prop="type"
            :label="t('counselorUserDetail.assessmentColType')"
            min-width="120"
          />
          <el-table-column
            prop="score"
            :label="t('counselorUserDetail.assessmentColScore')"
            min-width="120"
          />
          <el-table-column
            prop="created_at"
            :label="t('counselorUserDetail.assessmentColTime')"
            min-width="180"
          />
        </el-table>
      </el-tab-pane>

      <!-- UX-P3-02 修复：干预记录改时间线视图 -->
      <el-tab-pane
        :label="t('counselorUserDetail.tabInterventions')"
        name="interventions"
      >
        <el-timeline class="detail-timeline">
          <el-timeline-item
            v-for="item in interventionRows"
            :key="item.id"
            :type="item.status === 'completed' ? 'success' : item.status === 'active' ? 'primary' : 'warning'"
            :timestamp="item.created_at"
            placement="top"
          >
            <div class="timeline-title">
              {{ item.type }}
            </div>
            <div class="timeline-text">
              {{ item.status }}
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty
          v-if="!interventionRows.length"
          :description="t('common.noData')"
        />
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="consultationDialogVisible"
      :title="editingConsultation ? t('counselorUserDetail.consultationDialogTitleEdit') : t('counselorUserDetail.consultationDialogTitleCreate')"
      width="640px"
    >
      <el-form
        :model="consultationForm"
        label-width="90px"
      >
        <el-form-item
          :label="t('counselorUserDetail.consultationFormTopics')"
          required
        >
          <el-input v-model="consultationForm.main_topics" />
        </el-form-item>
        <el-form-item :label="t('counselorUserDetail.consultationFormStatus')">
          <el-input v-model="consultationForm.client_status" />
        </el-form-item>
        <el-form-item :label="t('counselorUserDetail.consultationFormInterventions')">
          <el-input
            v-model="consultationForm.interventions"
            type="textarea"
          />
        </el-form-item>
        <el-form-item :label="t('counselorUserDetail.consultationFormNextPlan')">
          <el-input
            v-model="consultationForm.next_plan"
            type="textarea"
          />
        </el-form-item>
        <el-form-item :label="t('counselorUserDetail.consultationFormNotes')">
          <el-input
            v-model="consultationForm.notes"
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="consultationDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="savingConsultation"
          @click="saveConsultation"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="groupDialogVisible"
      :title="t('counselorUserDetail.groupDialogTitleCreate')"
      width="520px"
    >
      <el-form
        :model="groupForm"
        label-width="90px"
      >
        <el-form-item
          :label="t('counselorUserDetail.groupFormName')"
          required
        >
          <el-input v-model="groupForm.group_name" />
        </el-form-item>
        <el-form-item :label="t('counselorUserDetail.groupFormDescription')">
          <el-input
            v-model="groupForm.description"
            type="textarea"
          />
        </el-form-item>
        <el-form-item :label="t('counselorUserDetail.groupFormColorTag')">
          <el-input
            v-model="groupForm.color_tag"
            placeholder="#2e6fa8"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialogVisible = false">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="savingGroup"
          @click="saveGroup"
        >
          {{ t('common.save') }}
        </el-button>
      </template>
    </el-dialog>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { counselorApi, type ConsultationGroupItem, type ConsultationItem, type UserManageItem, type UserRiskHistoryItem, type UserAssessmentItem, type UserInterventionItem } from '@/api/counselorApi'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { getWarningRiskLevelLabel, getWarningRiskLevelTagType } from '@/utils/warning'
import { hasPermission } from '@/config/permissions'
import { useAuthStore } from '@/stores/auth'
// ISS-082 修复：引入 useBreakpoint 实现 el-descriptions 列数响应式
import { useBreakpoint } from '@/composables/useBreakpoint'

const { t } = useI18n()
// ISS-082 修复：移动端 el-descriptions 列数降为 1，避免字段挤压
const { isMobile } = useBreakpoint()
const descColumn = computed(() => (isMobile.value ? 1 : 2))

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const canConsult = computed(() => hasPermission(auth.role, 'counselor.user.consultation.view'))
const loading = ref(false); const pageError = ref(''); const user = ref<UserManageItem | null>(null); const tab = ref('records')
const consultationLoading = ref(false); const consultationRows = ref<ConsultationItem[]>([]); const consultationDialogVisible = ref(false); const editingConsultation = ref<ConsultationItem | null>(null); const savingConsultation = ref(false)
const consultationForm = reactive<Partial<ConsultationItem>>({ main_topics: '', client_status: '', interventions: '', next_plan: '', notes: '' })
const groupLoading = ref(false); const groupRows = ref<ConsultationGroupItem[]>([]); const groupDialogVisible = ref(false); const savingGroup = ref(false); const groupForm = reactive({ group_name: '', description: '', color_tag: '#2e6fa8' })
// ISS-057: 风险轨迹 / 评估记录 / 干预记录
const riskHistoryRows = ref<UserRiskHistoryItem[]>([])
const assessmentRows = ref<UserAssessmentItem[]>([])
const interventionRows = ref<UserInterventionItem[]>([])
const userId = computed(() => Number(route.params.id)); const userDisplayName = computed(() => user.value?.nickname || user.value?.username || userId.value)

const fetchAll = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const userData = await counselorApi.getCounselorUserDetail(userId.value)
    user.value = userData
    // ISS-057: 从 user 对象中提取 risk_history/assessments/interventions
    riskHistoryRows.value = userData.risk_history || []
    assessmentRows.value = userData.assessments || []
    interventionRows.value = userData.interventions || []
    await Promise.all([fetchConsultations(), fetchGroups()])
  } catch (error) {
    pageError.value = showHttpFeedback(error, t('counselorUserDetail.loadUserFailed')).detail
  } finally {
    loading.value = false
  }
}

const fetchConsultations = async () => {
  consultationLoading.value = true
  try {
    const data = await counselorApi.getCounselorUserConsultations(userId.value, { page: 1, page_size: 100 })
    consultationRows.value = data.items
  } catch (error) {
    showHttpFeedback(error, t('counselorUserDetail.loadConsultationsFailed'))
  } finally {
    consultationLoading.value = false
  }
}

const fetchGroups = async () => {
  groupLoading.value = true
  try {
    const data = await counselorApi.getCounselorGroups({ page: 1, page_size: 100 })
    groupRows.value = data.items
  } catch (error) {
    showHttpFeedback(error, t('counselorUserDetail.loadGroupsFailed'))
  } finally {
    groupLoading.value = false
  }
}

const openCreate = () => {
  editingConsultation.value = null
  consultationForm.main_topics = ''
  consultationForm.client_status = ''
  consultationForm.interventions = ''
  consultationForm.next_plan = ''
  consultationForm.notes = ''
  consultationDialogVisible.value = true
}

const openEdit = (row: ConsultationItem) => {
  editingConsultation.value = row
  consultationForm.main_topics = row.main_topics || ''
  consultationForm.client_status = row.client_status || ''
  consultationForm.interventions = row.interventions || ''
  consultationForm.next_plan = row.next_plan || ''
  consultationForm.notes = row.notes || ''
  consultationDialogVisible.value = true
}

const saveConsultation = async () => {
  if (!consultationForm.main_topics?.trim()) {
    return
  }
  savingConsultation.value = true
  try {
    if (editingConsultation.value) {
      await counselorApi.updateCounselorUserConsultation(userId.value, editingConsultation.value.id, consultationForm)
    } else {
      await counselorApi.createCounselorUserConsultation(userId.value, consultationForm)
    }
    consultationDialogVisible.value = false
    await fetchConsultations()
  } catch (error) {
    showHttpFeedback(error, t('counselorUserDetail.saveConsultationFailed'))
  } finally {
    savingConsultation.value = false
  }
}

const openCreateGroup = () => {
  groupForm.group_name = ''
  groupForm.description = ''
  groupForm.color_tag = '#2e6fa8'
  groupDialogVisible.value = true
}

const saveGroup = async () => {
  savingGroup.value = true
  try {
    await counselorApi.createCounselorGroup(groupForm)
    groupDialogVisible.value = false
    await fetchGroups()
  } catch (error) {
    showHttpFeedback(error, t('counselorUserDetail.saveGroupFailed'))
  } finally {
    savingGroup.value = false
  }
}

const addCurrentUserToGroup = async (row: ConsultationGroupItem) => {
  try {
    await counselorApi.addCounselorGroupMember(row.id, userId.value)
    await fetchGroups()
  } catch (error) {
    showHttpFeedback(error, t('counselorUserDetail.addMemberFailed'))
  }
}

const goBack = () => router.push({ path: '/counselor/users', query: route.query })

const getRiskTimelineType = (item: UserRiskHistoryItem) => {
  const tag = getWarningRiskLevelTagType(item.risk_level ?? 0)
  return tag === 'danger' ? 'danger' : tag === 'warning' ? 'warning' : 'primary'
}

onMounted(fetchAll)
</script>

<style scoped>
.user-descriptions {
  margin-bottom: var(--spacing-md);
}

/* UX-P3-01 修复：操作区滚动后保持可见 - sticky 定位 + 背景色 + z-index，
   避免长列表滚动时"新建咨询/新建分组"按钮脱离视口 */
.toolbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  background: var(--bg-page);
  padding: var(--spacing-sm) 0;
}

/* UX-P3-02 修复：时间线视图留白与节点排版 */
.detail-timeline {
  padding: var(--spacing-sm) 0 0 6px;
}

.detail-timeline .timeline-title {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.detail-timeline .timeline-text {
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
