<template>
  <div class="settings-page">
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span class="card-title">我的绑定码</span>
          </template>
          <div
            v-if="bindCodeLoading"
            style="padding: 20px"
          >
            <el-skeleton
              :rows="2"
              animated
            />
          </div>
          <template v-else>
            <div class="bind-code-display">
              <span class="bind-code-text">{{ counselorBindCode || '—' }}</span>
              <el-tag
                v-if="bindCodeStatusLabel"
                :type="bindCodeStatusType"
                effect="light"
              >
                {{ bindCodeStatusLabel }}
              </el-tag>
              <el-button
                type="primary"
                link
                @click="copyBindCode"
              >
                复制
              </el-button>
            </div>
            <div
              class="bind-tip"
              style="margin-top: 8px"
            >
              <el-icon><InfoFilled /></el-icon>
              <span>将此绑定码分享给需要绑定的用户，用户在"个人设置"页面输入绑定码即可建立绑定关系。</span>
            </div>
            <div style="margin-top: 12px">
              <el-button
                type="warning"
                plain
                size="small"
                :loading="refreshCodeLoading"
                @click="handleRefreshCode"
              >
                刷新绑定码
              </el-button>
            </div>
          </template>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
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
                value="咨询师"
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
import { counselorApi } from '@/api/counselorApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import { setStoredAuth } from '@/utils/authStorage'

const auth = useAuthStore()

const bindCodeLoading = ref(true)
const counselorBindCode = ref('')
const bindCodeStatus = ref<'placeholder' | 'active' | 'inactive'>('placeholder')
const refreshCodeLoading = ref(false)

const bindCodeStatusLabel = computed(() => {
  if (bindCodeStatus.value === 'active') return '可用'
  if (bindCodeStatus.value === 'placeholder') return '待分发'
  return '已失效'
})

const bindCodeStatusType = computed(() => {
  if (bindCodeStatus.value === 'active') return 'success'
  if (bindCodeStatus.value === 'placeholder') return 'warning'
  return 'info'
})

const loadCounselorBindCode = async () => {
  bindCodeLoading.value = true
  try {
    const data = await counselorApi.getCounselorBindCode()
    counselorBindCode.value = data.bind_code
    bindCodeStatus.value = 'active'
  } catch {
    counselorBindCode.value = ''
    bindCodeStatus.value = 'inactive'
  } finally {
    bindCodeLoading.value = false
  }
}

const copyBindCode = async () => {
  if (!counselorBindCode.value) return
  try {
    await navigator.clipboard.writeText(counselorBindCode.value)
    ElMessage.success('绑定码已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制')
  }
}

const handleRefreshCode = async () => {
  try {
    await ElMessageBox.confirm('刷新绑定码后，旧绑定码将失效，已绑定的用户不受影响。确认刷新？', '刷新确认', { type: 'warning' })
  } catch {
    return
  }
  refreshCodeLoading.value = true
  try {
    const data = await counselorApi.refreshCounselorBindCode()
    counselorBindCode.value = data.bind_code
    bindCodeStatus.value = 'active'
    ElMessage.success('绑定码已刷新')
  } catch (error) {
    ElMessage.error(normalizeHttpError(error, '刷新失败').detail)
  } finally {
    refreshCodeLoading.value = false
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
  loadCounselorBindCode()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}

.card-title {
  font-weight: 600;
}

.bind-code-display {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bind-code-text {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: 4px;
  color: #409eff;
  font-family: 'Courier New', Courier, monospace;
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
