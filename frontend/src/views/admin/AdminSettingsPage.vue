<template>
  <div class="settings-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <el-tab-pane
        label="预警阈值"
        name="thresholds"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">预警阈值配置</span>
              <el-button
                type="primary"
                size="small"
                @click="openThresholdCreate"
              >
                新增阈值
              </el-button>
            </div>
          </template>

          <StatefulContainer
            :loading="thresholdLoading"
            :empty="!thresholdLoading && thresholds.length === 0"
            :error-message="thresholdError"
            empty-text="暂无阈值配置"
            @retry="loadThresholds"
          >
            <el-table
              :data="thresholds"
              border
              stripe
            >
              <el-table-column
                prop="level"
                label="等级"
                width="80"
              />
              <el-table-column
                prop="level_name"
                label="等级名称"
                width="120"
              />
              <el-table-column
                prop="min_score"
                label="最低分数"
                width="100"
              />
              <el-table-column
                prop="max_score"
                label="最高分数"
                width="100"
              />
              <el-table-column
                prop="color"
                label="颜色"
                width="100"
              >
                <template #default="{ row }">
                  <span :style="{ color: row.color, fontWeight: 'bold' }">{{ row.color }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="action_required"
                label="要求动作"
                min-width="200"
              />
              <el-table-column
                label="操作"
                width="100"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button
                    link
                    type="primary"
                    size="small"
                    @click="openThresholdEdit(row)"
                  >
                    编辑
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </StatefulContainer>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        label="系统配置"
        name="configs"
      >
        <el-card>
          <template #header>
            <div class="header-row">
              <span class="card-title">系统配置</span>
              <el-button
                type="primary"
                size="small"
                @click="openConfigCreate"
              >
                新增配置
              </el-button>
            </div>
          </template>

          <StatefulContainer
            :loading="configLoading"
            :empty="!configLoading && configs.length === 0"
            :error-message="configError"
            empty-text="暂无系统配置"
            @retry="loadConfigs"
          >
            <el-table
              :data="configs"
              border
              stripe
            >
              <el-table-column
                prop="config_key"
                label="配置键"
                min-width="180"
              />
              <el-table-column
                prop="config_value"
                label="配置值"
                min-width="240"
              >
                <template #default="{ row }">
                  <span class="config-value">{{ JSON.stringify(row.config_value) }}</span>
                </template>
              </el-table-column>
              <el-table-column
                prop="description"
                label="描述"
                min-width="180"
              >
                <template #default="{ row }">
                  {{ row.description || '-' }}
                </template>
              </el-table-column>
              <el-table-column
                label="操作"
                width="100"
                fixed="right"
              >
                <template #default="{ row }">
                  <el-button
                    link
                    type="primary"
                    size="small"
                    @click="openConfigEdit(row)"
                  >
                    编辑
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </StatefulContainer>
        </el-card>
      </el-tab-pane>

      <el-tab-pane
        label="模型反馈"
        name="feedbacks"
      >
        <el-card>
          <template #header>
            <span class="card-title">模型反馈记录</span>
          </template>
          <StatefulContainer
            :loading="feedbackLoading"
            :empty="!feedbackLoading && feedbacks.length === 0"
            :error-message="feedbackError"
            empty-text="暂无反馈记录"
            @retry="loadFeedbacks"
          >
            <el-table
              :data="feedbacks"
              border
              stripe
            >
              <el-table-column
                prop="id"
                label="ID"
                width="80"
              />
              <el-table-column
                prop="counselor_id"
                label="咨询师ID"
                width="100"
              />
              <el-table-column
                prop="user_id"
                label="用户ID"
                width="100"
              />
              <el-table-column
                prop="assessment_id"
                label="评估ID"
                width="100"
              />
              <el-table-column
                prop="agreed"
                label="是否同意"
                width="100"
              >
                <template #default="{ row }">
                  <el-tag
                    :type="row.agreed ? 'success' : 'danger'"
                    size="small"
                  >
                    {{ row.agreed ? '同意' : '不同意' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                prop="reason"
                label="原因"
                min-width="200"
              />
              <el-table-column
                prop="created_at"
                label="时间"
                width="180"
              />
            </el-table>
          </StatefulContainer>
          <div class="pager-wrap">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="feedbackTotal"
              :page-size="feedbackPageSize"
              :current-page="feedbackPage"
              @current-change="(v: number) => { feedbackPage = v; loadFeedbacks() }"
              @size-change="(v: number) => { feedbackPageSize = v; feedbackPage = 1; loadFeedbacks() }"
            />
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="thresholdFormVisible"
      :title="thresholdEditing ? '编辑阈值' : '新增阈值'"
      width="480px"
      destroy-on-close
    >
      <el-form
        :model="thresholdForm"
        label-width="100px"
      >
        <el-form-item
          label="等级"
          required
        >
          <el-input-number
            v-model="thresholdForm.level"
            :min="0"
            :max="10"
            :disabled="!!thresholdEditing"
          />
        </el-form-item>
        <el-form-item
          label="等级名称"
          required
        >
          <el-input v-model="thresholdForm.level_name" />
        </el-form-item>
        <el-form-item
          label="最低分数"
          required
        >
          <el-input-number
            v-model="thresholdForm.min_score"
            :min="0"
            :max="100"
            :precision="1"
          />
        </el-form-item>
        <el-form-item
          label="最高分数"
          required
        >
          <el-input-number
            v-model="thresholdForm.max_score"
            :min="0"
            :max="100"
            :precision="1"
          />
        </el-form-item>
        <el-form-item
          label="颜色"
          required
        >
          <el-input
            v-model="thresholdForm.color"
            placeholder="#e6a23c"
          />
        </el-form-item>
        <el-form-item
          label="要求动作"
          required
        >
          <el-input
            v-model="thresholdForm.action_required"
            type="textarea"
            :rows="2"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="thresholdFormVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="thresholdSaving"
          @click="submitThreshold"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="configFormVisible"
      :title="configEditing ? '编辑配置' : '新增配置'"
      width="480px"
      destroy-on-close
    >
      <el-form
        :model="configForm"
        label-width="100px"
      >
        <el-form-item
          label="配置键"
          required
        >
          <el-input
            v-model="configForm.config_key"
            :disabled="!!configEditing"
          />
        </el-form-item>
        <el-form-item
          label="配置值"
          required
        >
          <el-input
            v-model="configValueJson"
            type="textarea"
            :rows="4"
            placeholder="{&quot;value&quot;: &quot;example&quot;}"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="configForm.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configFormVisible = false">
          取消
        </el-button>
        <el-button
          type="primary"
          :loading="configSaving"
          @click="submitConfig"
        >
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import StatefulContainer from '@/components/common/StatefulContainer.vue'
import { adminApi, type ThresholdItem, type ConfigItem, type ModelFeedbackItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'

const activeTab = ref('thresholds')

const thresholds = ref<ThresholdItem[]>([])
const thresholdLoading = ref(false)
const thresholdError = ref('')

const loadThresholds = async () => {
  thresholdLoading.value = true
  thresholdError.value = ''
  try {
    const data = await adminApi.listAdminThresholds()
    thresholds.value = data.items
  } catch (error) {
    thresholdError.value = normalizeHttpError(error, '阈值加载失败').detail
  } finally {
    thresholdLoading.value = false
  }
}

const thresholdFormVisible = ref(false)
const thresholdSaving = ref(false)
const thresholdEditing = ref(false)
const thresholdForm = reactive({ level: 0, level_name: '', min_score: 0, max_score: 100, color: '#e6a23c', action_required: '' })

const openThresholdCreate = () => {
  thresholdEditing.value = false
  thresholdForm.level = 0
  thresholdForm.level_name = ''
  thresholdForm.min_score = 0
  thresholdForm.max_score = 100
  thresholdForm.color = '#e6a23c'
  thresholdForm.action_required = ''
  thresholdFormVisible.value = true
}

const openThresholdEdit = (row: ThresholdItem) => {
  thresholdEditing.value = true
  thresholdForm.level = row.level
  thresholdForm.level_name = row.level_name
  thresholdForm.min_score = row.min_score
  thresholdForm.max_score = row.max_score
  thresholdForm.color = row.color
  thresholdForm.action_required = row.action_required
  thresholdFormVisible.value = true
}

const submitThreshold = async () => {
  if (!thresholdForm.level_name.trim()) { ElMessage.warning('请输入等级名称'); return }
  if (thresholdForm.min_score > thresholdForm.max_score) { ElMessage.warning('最低分数不能大于最高分数'); return }
  thresholdSaving.value = true
  try {
    await adminApi.upsertAdminThreshold({ ...thresholdForm })
    ElMessage.success('阈值已保存')
    thresholdFormVisible.value = false
    loadThresholds()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '保存失败').detail)
  } finally {
    thresholdSaving.value = false
  }
}

const configs = ref<ConfigItem[]>([])
const configLoading = ref(false)
const configError = ref('')

const loadConfigs = async () => {
  configLoading.value = true
  configError.value = ''
  try {
    const data = await adminApi.listAdminConfigs()
    configs.value = data.items
  } catch (error) {
    configError.value = normalizeHttpError(error, '配置加载失败').detail
  } finally {
    configLoading.value = false
  }
}

const configFormVisible = ref(false)
const configSaving = ref(false)
const configEditing = ref(false)
const configForm = reactive({ config_key: '', description: '' })
const configValueJson = ref('{}')

const openConfigCreate = () => {
  configEditing.value = false
  configForm.config_key = ''
  configForm.description = ''
  configValueJson.value = '{}'
  configFormVisible.value = true
}

const openConfigEdit = (row: ConfigItem) => {
  configEditing.value = true
  configForm.config_key = row.config_key
  configForm.description = row.description || ''
  configValueJson.value = JSON.stringify(row.config_value, null, 2)
  configFormVisible.value = true
}

const submitConfig = async () => {
  if (!configForm.config_key.trim()) { ElMessage.warning('请输入配置键'); return }
  let configValue: Record<string, unknown>
  try { configValue = JSON.parse(configValueJson.value) } catch { ElMessage.warning('配置值 JSON 格式错误'); return }
  configSaving.value = true
  try {
    await adminApi.upsertAdminConfig({ config_key: configForm.config_key, config_value: configValue, description: configForm.description || undefined })
    ElMessage.success('配置已保存')
    configFormVisible.value = false
    loadConfigs()
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '保存失败').detail)
  } finally {
    configSaving.value = false
  }
}

const feedbacks = ref<ModelFeedbackItem[]>([])
const feedbackTotal = ref(0)
const feedbackPage = ref(1)
const feedbackPageSize = ref(10)
const feedbackLoading = ref(false)
const feedbackError = ref('')

const loadFeedbacks = async () => {
  feedbackLoading.value = true
  feedbackError.value = ''
  try {
    const data = await adminApi.listAdminFeedbacks({ page: feedbackPage.value, page_size: feedbackPageSize.value })
    feedbacks.value = data.items
    feedbackTotal.value = data.total
  } catch (error) {
    feedbackError.value = normalizeHttpError(error, '反馈加载失败').detail
  } finally {
    feedbackLoading.value = false
  }
}

onMounted(() => {
  loadThresholds()
  loadConfigs()
  loadFeedbacks()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}

.card-title {
  font-weight: 600;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-value {
  font-family: monospace;
  font-size: 12px;
  color: #606266;
  word-break: break-all;
}

.pager-wrap {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
