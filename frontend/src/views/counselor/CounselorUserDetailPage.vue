<template>
  <ListPageScaffold
    :title="`用户详情 - ${userDisplayName}`"
    :loading="loading"
    :empty="!loading && !user"
    :error-message="pageError"
    empty-text="用户不存在"
    @retry="fetchAll"
  >
    <template #header-extra>
      <el-button @click="goBack">
        返回
      </el-button>
    </template>

    <el-descriptions
      v-if="user"
      :column="2"
      border
      style="margin-bottom: 12px"
    >
      <el-descriptions-item label="用户ID">
        {{ user.id }}
      </el-descriptions-item>
      <el-descriptions-item label="用户名">
        {{ user.username }}
      </el-descriptions-item>
      <el-descriptions-item label="昵称">
        {{ user.nickname || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="邮箱">
        {{ user.email || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="状态">
        {{ user.status || '-' }}
      </el-descriptions-item>
    </el-descriptions>

    <el-tabs v-model="tab">
      <el-tab-pane
        label="咨询记录"
        name="records"
      >
        <div class="toolbar">
          <el-button
            v-if="canConsult"
            type="primary"
            @click="openCreate"
          >
            新建记录
          </el-button>
        </div>
        <el-table
          v-loading="consultationLoading"
          :data="consultationRows"
          border
        >
          <el-table-column
            prop="id"
            label="记录ID"
            width="100"
          />
          <el-table-column
            prop="main_topics"
            label="会谈主题"
            min-width="180"
          />
          <el-table-column
            prop="client_status"
            label="来访状态"
            min-width="160"
          />
          <el-table-column
            prop="interventions"
            label="干预措施"
            min-width="180"
          />
          <el-table-column
            prop="next_plan"
            label="下次计划"
            min-width="180"
          />
          <el-table-column
            prop="created_at"
            label="时间"
            min-width="180"
          />
          <el-table-column
            label="操作"
            width="140"
          >
            <template #default="{ row }">
              <ActionColumn
                v-if="canConsult"
                label="编辑"
                show-audit
                @action="openEdit(row)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane
        label="分组管理"
        name="groups"
      >
        <div class="toolbar">
          <el-button
            v-if="canConsult"
            type="primary"
            @click="openCreateGroup"
          >
            新建分组
          </el-button>
        </div>
        <el-table
          v-loading="groupLoading"
          :data="groupRows"
          border
        >
          <el-table-column
            prop="id"
            label="分组ID"
            width="100"
          />
          <el-table-column
            prop="group_name"
            label="分组名称"
            min-width="180"
          />
          <el-table-column
            prop="description"
            label="说明"
            min-width="220"
          />
          <el-table-column
            prop="user_count"
            label="用户数"
            width="120"
          />
          <el-table-column
            label="操作"
            width="200"
          >
            <template #default="{ row }">
              <ActionColumn
                v-if="canConsult"
                label="加当前用户"
                type="primary"
                show-audit
                @action="addCurrentUserToGroup(row)"
              />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="consultationDialogVisible"
      :title="editingConsultation ? '编辑咨询记录' : '新建咨询记录'"
      width="640px"
    >
      <el-form
        :model="consultationForm"
        label-width="90px"
      >
        <el-form-item label="会谈主题">
          <el-input v-model="consultationForm.main_topics" />
        </el-form-item>
        <el-form-item label="来访状态">
          <el-input v-model="consultationForm.client_status" />
        </el-form-item>
        <el-form-item label="干预措施">
          <el-input
            v-model="consultationForm.interventions"
            type="textarea"
          />
        </el-form-item>
        <el-form-item label="下次计划">
          <el-input
            v-model="consultationForm.next_plan"
            type="textarea"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="consultationForm.notes"
            type="textarea"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="consultationDialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="savingConsultation"
          @click="saveConsultation"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="groupDialogVisible"
      title="新建分组"
      width="520px"
    >
      <el-form
        :model="groupForm"
        label-width="90px"
      >
        <el-form-item label="分组名称">
          <el-input v-model="groupForm.group_name" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            v-model="groupForm.description"
            type="textarea"
          />
        </el-form-item>
        <el-form-item label="颜色标记">
          <el-input
            v-model="groupForm.color_tag"
            placeholder="#409EFF"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="groupDialogVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="savingGroup"
          @click="saveGroup"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </ListPageScaffold>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { counselorApi, type ConsultationGroupItem, type ConsultationItem, type UserManageItem } from '@/api/counselorApi'
import ListPageScaffold from '@/components/common/ListPageScaffold.vue'
import ActionColumn from '@/components/common/ActionColumn.vue'
import { showHttpFeedback } from '@/utils/httpFeedback'
import { hasPermission } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const canConsult = computed(() => hasPermission(auth.role, 'counselor.user.consultation.view'))
const loading = ref(false); const pageError = ref(''); const user = ref<UserManageItem | null>(null); const tab = ref('records')
const consultationLoading = ref(false); const consultationRows = ref<ConsultationItem[]>([]); const consultationDialogVisible = ref(false); const editingConsultation = ref<ConsultationItem | null>(null); const savingConsultation = ref(false)
const consultationForm = reactive<Partial<ConsultationItem>>({ main_topics: '', client_status: '', interventions: '', next_plan: '', notes: '' })
const groupLoading = ref(false); const groupRows = ref<ConsultationGroupItem[]>([]); const groupDialogVisible = ref(false); const savingGroup = ref(false); const groupForm = reactive({ group_name: '', description: '', color_tag: '#409EFF' })
const userId = computed(() => Number(route.params.id)); const userDisplayName = computed(() => user.value?.nickname || user.value?.username || userId.value)

const fetchAll = async () => {
  loading.value = true
  pageError.value = ''
  try {
    const userData = await counselorApi.getCounselorUserDetail(userId.value)
    user.value = userData
    await Promise.all([fetchConsultations(), fetchGroups()])
  } catch (error) {
    pageError.value = showHttpFeedback(error, '用户详情加载失败').detail
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
    showHttpFeedback(error, '咨询记录加载失败')
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
    showHttpFeedback(error, '分组加载失败')
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
    showHttpFeedback(error, '保存咨询记录失败')
  } finally {
    savingConsultation.value = false
  }
}

const openCreateGroup = () => {
  groupForm.group_name = ''
  groupForm.description = ''
  groupForm.color_tag = '#409EFF'
  groupDialogVisible.value = true
}

const saveGroup = async () => {
  savingGroup.value = true
  try {
    await counselorApi.createCounselorGroup(groupForm)
    groupDialogVisible.value = false
    await fetchGroups()
  } catch (error) {
    showHttpFeedback(error, '保存分组失败')
  } finally {
    savingGroup.value = false
  }
}

const addCurrentUserToGroup = async (row: ConsultationGroupItem) => {
  try {
    await counselorApi.addCounselorGroupMember(row.id, userId.value)
    await fetchGroups()
  } catch (error) {
    showHttpFeedback(error, '添加分组成员失败')
  }
}

const goBack = () => router.push({ path: '/counselor/users', query: route.query })

onMounted(fetchAll)
</script>
