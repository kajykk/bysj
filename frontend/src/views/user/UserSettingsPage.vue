<template>
  <div class="settings-page">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span class="card-title">预警设置</span>
          </template>
          <div
            v-if="settingsLoading"
            style="padding: 20px"
          >
            <el-skeleton
              :rows="4"
              animated
            />
          </div>
          <el-form
            v-else
            :model="settingsForm"
            label-width="120px"
          >
            <el-form-item label="通知渠道">
              <el-checkbox-group v-model="settingsForm.notify_channels">
                <el-checkbox
                  label="站内通知"
                  value="in_app"
                />
                <el-checkbox
                  label="邮件"
                  value="email"
                />
                <el-checkbox
                  label="短信"
                  value="sms"
                />
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="预警阈值等级">
              <el-select
                v-model="settingsForm.threshold_level"
                style="width: 200px"
              >
                <el-option
                  label="等级1（轻度及以上）"
                  :value="1"
                />
                <el-option
                  label="等级2（中度及以上）"
                  :value="2"
                />
                <el-option
                  label="等级3（较高及以上）"
                  :value="3"
                />
                <el-option
                  label="等级4（严重）"
                  :value="4"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="免打扰时段">
              <div style="display: flex; gap: 8px; align-items: center">
                <el-time-select
                  v-model="settingsForm.quiet_hours_start"
                  :max-time="settingsForm.quiet_hours_end"
                  placeholder="开始"
                  start="00:00"
                  step="00:30"
                  end="23:30"
                />
                <span>至</span>
                <el-time-select
                  v-model="settingsForm.quiet_hours_end"
                  :min-time="settingsForm.quiet_hours_start"
                  placeholder="结束"
                  start="00:00"
                  step="00:30"
                  end="23:30"
                />
              </div>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="settingsSaving"
                @click="saveSettings"
              >
                保存设置
              </el-button>
              <el-button
                style="margin-left: 8px"
                @click="resetSettingsForm"
              >
                重置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card v-if="auth.role === 'user'">
          <template #header>
            <span class="card-title">咨询师绑定</span>
          </template>
          <div
            v-if="bindingLoading"
            style="padding: 20px"
          >
            <el-skeleton
              :rows="3"
              animated
            />
          </div>
          <template v-else-if="currentBinding">
            <el-descriptions
              :column="1"
              border
            >
              <el-descriptions-item label="绑定咨询师">
                {{ currentBinding.counselor_name }}
              </el-descriptions-item>
              <el-descriptions-item label="绑定时间">
                {{ formatDate(currentBinding.bound_at) }}
              </el-descriptions-item>
            </el-descriptions>
            <div style="margin-top: 16px">
              <el-button
                type="danger"
                plain
                :loading="unbindLoading"
                @click="handleUnbind"
              >
                解绑咨询师
              </el-button>
            </div>
          </template>
          <template v-else>
            <el-form
              :model="bindForm"
              label-width="100px"
              @submit.prevent="handleBind"
            >
              <el-form-item label="绑定码">
                <el-input
                  v-model="bindForm.bind_code"
                  placeholder="请输入咨询师提供的绑定码"
                  :maxlength="10"
                  clearable
                />
              </el-form-item>
              <el-form-item>
                <el-button
                  type="primary"
                  :loading="bindLoading"
                  @click="handleBind"
                >
                  绑定咨询师
                </el-button>
              </el-form-item>
            </el-form>
            <div class="bind-tip">
              <el-icon><InfoFilled /></el-icon>
              <span>请向您的咨询师获取绑定码，输入后即可建立绑定关系。绑定后，咨询师可查看您的风险评估结果并提供干预建议。</span>
            </div>
          </template>
        </el-card>

        <el-card style="margin-top: 16px">
          <template #header>
            <span class="card-title">个人信息</span>
          </template>
          <el-form
            :model="profileForm"
            label-width="100px"
          >
            <el-form-item label="用户名">
              <el-input
                :model-value="auth.user?.username"
                disabled
              />
            </el-form-item>
            <el-form-item label="角色">
              <el-input
                :model-value="roleLabel"
                disabled
              />
            </el-form-item>
            <el-form-item label="昵称">
              <el-input
                v-model="profileForm.nickname"
                placeholder="设置你的昵称"
              />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input
                v-model="profileForm.email"
                placeholder="你的邮箱地址"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="profileSaving"
                @click="saveProfile"
              >
                保存信息
              </el-button>
              <el-button
                style="margin-left: 8px"
                @click="resetProfileForm"
              >
                恢复原值
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card style="margin-top: 16px">
          <template #header>
            <span class="card-title">修改密码</span>
          </template>
          <el-form
            :model="passwordForm"
            label-width="100px"
          >
            <el-form-item label="当前密码">
              <el-input
                v-model="passwordForm.old_password"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item label="新密码">
              <el-input
                v-model="passwordForm.new_password"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input
                v-model="passwordForm.confirm_password"
                type="password"
                show-password
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="passwordSaving"
                @click="changePassword"
              >
                修改密码
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'
import { userApi, type UserBindingInfo } from '@/api/userApi'
import type { BindCounselorResult } from '@/api/userBindingApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { setStoredAuth } from '@/utils/authStorage'
import { checkPasswordBytes, MAX_PASSWORD_BYTES } from '@/utils/passwordValidation'

const auth = useAuthStore()

const roleLabel = computed(() => {
  if (auth.role === 'admin') return '管理员'
  if (auth.role === 'counselor') return '咨询师'
  return '普通用户'
})

const formatDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const settingsLoading = ref(true)
const settingsSaving = ref(false)
const settingsForm = reactive({
  notify_channels: ['in_app'] as string[],
  threshold_level: 2,
  quiet_hours_start: '' as string | null,
  quiet_hours_end: '' as string | null
})

const channelKeys = ['in_app', 'email', 'sms', 'websocket'] as const

const channelsToRecord = (channels: string[]): Record<string, boolean> => {
  const result: Record<string, boolean> = { in_app: false, email: false, sms: false, websocket: false }
  for (const key of channelKeys) {
    result[key] = channels.includes(key)
  }
  return result
}

const recordToChannels = (record: Record<string, boolean> | null | undefined): string[] => {
  if (!record) return ['in_app']
  return channelKeys.filter((key) => Boolean(record[key]))
}

const loadSettings = async () => {
  settingsLoading.value = true
  try {
    const data = await userApi.getWarningSettings()
    settingsForm.notify_channels = recordToChannels(data.notify_channels)
    settingsForm.threshold_level = data.threshold_level || 2
    settingsForm.quiet_hours_start = data.quiet_hours_start || ''
    settingsForm.quiet_hours_end = data.quiet_hours_end || ''
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '预警设置加载失败').detail)
  } finally {
    settingsLoading.value = false
  }
}

const saveSettings = async () => {
  settingsSaving.value = true
  try {
    await userApi.updateWarningSettings({
      notify_channels: channelsToRecord(settingsForm.notify_channels),
      threshold_level: settingsForm.threshold_level,
      quiet_hours_start: settingsForm.quiet_hours_start || undefined,
      quiet_hours_end: settingsForm.quiet_hours_end || undefined
    })
    ElMessage.success('预警设置已保存')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '保存失败').detail)
  } finally {
    settingsSaving.value = false
  }
}

const resetSettingsForm = () => {
  settingsForm.notify_channels = ['in_app']
  settingsForm.threshold_level = 2
  settingsForm.quiet_hours_start = ''
  settingsForm.quiet_hours_end = ''
}

const bindingLoading = ref(true)
const currentBinding = ref<UserBindingInfo | null>(null)

const loadBinding = async () => {
  if (auth.role !== 'user') {
    bindingLoading.value = false
    return
  }
  bindingLoading.value = true
  try {
    currentBinding.value = await userApi.getUserBinding()
  } catch (error) {
    currentBinding.value = null
    ElMessage.warning(normalizeHttpError(error, '咨询师绑定信息加载失败').detail)
  } finally {
    bindingLoading.value = false
  }
}

const bindForm = reactive({ bind_code: '' })
const bindLoading = ref(false)

const handleBind = async () => {
  if (!bindForm.bind_code.trim()) {
    ElMessage.warning('请输入绑定码')
    return
  }
  bindLoading.value = true
  try {
    const result: BindCounselorResult = await userApi.bindCounselor(bindForm.bind_code.trim())
    currentBinding.value = {
      binding_id: result.binding_id,
      counselor_id: result.counselor_id,
      counselor_name: result.counselor_name,
      counselor_email: result.counselor_email,
      bound_at: result.bound_at,
      status: result.status,
      bind_code_status: result.bind_code_status
    }
    bindForm.bind_code = ''
    ElMessage.success(`已成功绑定咨询师：${result.counselor_name}`)
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '绑定失败').detail)
  } finally {
    bindLoading.value = false
  }
}

const unbindLoading = ref(false)

const handleUnbind = async () => {
  try {
    await ElMessageBox.confirm('确认解绑当前咨询师？解绑后咨询师将无法查看您的风险评估数据。', '解绑确认', { type: 'warning' })
  } catch {
    return
  }
  unbindLoading.value = true
  try {
    await userApi.unbindCounselor()
    currentBinding.value = null
    ElMessage.success('已解绑咨询师')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '解绑失败').detail)
  } finally {
    unbindLoading.value = false
  }
}

const profileForm = reactive({
  nickname: auth.user?.nickname || '',
  email: auth.user?.email || ''
})
const profileSaving = ref(false)

const saveProfile = async () => {
  profileSaving.value = true
  try {
    const data = await authApi.updateProfile({
      nickname: profileForm.nickname || undefined,
      email: profileForm.email || undefined
    })
    if (auth.user) {
      auth.user.nickname = data.nickname
      auth.user.email = data.email
      setStoredAuth({ user: auth.user })
    }
    ElMessage.success('个人信息已保存')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '保存失败').detail)
  } finally {
    profileSaving.value = false
  }
}

const resetProfileForm = () => {
  profileForm.nickname = auth.user?.nickname || ''
  profileForm.email = auth.user?.email || ''
}

const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const passwordSaving = ref(false)

const changePassword = async () => {
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  if (passwordForm.new_password.length < 8) {
    ElMessage.warning('密码长度不能少于8位')
    return
  }
  const byteError = checkPasswordBytes(passwordForm.new_password)
  if (byteError) {
    ElMessage.warning(byteError)
    return
  }
  passwordSaving.value = true
  try {
    await authApi.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    ElMessage.success('密码修改成功')
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '修改失败').detail)
  } finally {
    passwordSaving.value = false
  }
}

onMounted(() => {
  loadSettings()
  loadBinding()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}

.card-title {
  font-weight: 600;
}

.bind-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.bind-tip .el-icon {
  margin-top: 3px;
  flex-shrink: 0;
}
</style>
