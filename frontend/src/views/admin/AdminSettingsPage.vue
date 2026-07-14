<template>
  <div class="settings-page">
    <el-tabs
      v-model="activeTab"
      type="border-card"
    >
      <el-tab-pane
        :label="t('adminSettings.tabs.thresholds')"
        name="thresholds"
      >
        <ThresholdsTab />
      </el-tab-pane>

      <el-tab-pane
        :label="t('adminSettings.tabs.configs')"
        name="configs"
      >
        <ConfigsTab
          :configs="configs"
          :loading="configLoading"
          :error="configError"
          @reload="loadConfigs"
        />
      </el-tab-pane>

      <el-tab-pane
        :label="t('adminSettings.tabs.feedbacks')"
        name="feedbacks"
      >
        <FeedbacksTab />
      </el-tab-pane>

      <!-- ISS-074: GDPR 合规管理 -->
      <el-tab-pane
        :label="t('adminSettings.tabs.gdpr')"
        name="gdpr"
      >
        <GdprTab />
      </el-tab-pane>

      <!-- ISS-077: 安全配置 -->
      <el-tab-pane
        :label="t('adminSettings.tabs.security')"
        name="security"
      >
        <SecurityTab
          :configs="configs"
          @reload="loadConfigs"
        />
      </el-tab-pane>

      <!-- ISS-077: 通知配置 -->
      <el-tab-pane
        :label="t('adminSettings.tabs.notification')"
        name="notification"
      >
        <NotificationTab
          :configs="configs"
          @reload="loadConfigs"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AdminSettingsPage' })
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi, type ConfigItem } from '@/api/adminApi'
import { normalizeHttpError } from '@/utils/errorPolicy'
import ThresholdsTab from './components/admin-settings-page/ThresholdsTab.vue'
import ConfigsTab from './components/admin-settings-page/ConfigsTab.vue'
import FeedbacksTab from './components/admin-settings-page/FeedbacksTab.vue'
import GdprTab from './components/admin-settings-page/GdprTab.vue'
import SecurityTab from './components/admin-settings-page/SecurityTab.vue'
import NotificationTab from './components/admin-settings-page/NotificationTab.vue'

const { t } = useI18n()

const activeTab = ref('thresholds')

// ===== 共享配置状态（ConfigsTab/SecurityTab/NotificationTab 共用） =====
// 安全/通知配置依赖 configs 列表中的 key-value，故此处由父组件持有
// configs 状态并在加载完成后由子组件通过 watch(props.configs) 同步表单。
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
    configError.value = normalizeHttpError(error, t('adminSettings.configs.loadFailed')).detail
  } finally {
    configLoading.value = false
  }
}

onMounted(() => {
  loadConfigs()
})
</script>

<style scoped>
.settings-page {
  padding: 0;
}
</style>
