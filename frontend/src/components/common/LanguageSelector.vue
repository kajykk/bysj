<template>
  <el-dropdown
    trigger="click"
    @command="handleLanguageChange"
  >
    <el-button circle>
      <el-icon><Position /></el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          command="zh-CN"
          :disabled="currentLocale === 'zh-CN'"
        >
          {{ $t('language.zh') }}
        </el-dropdown-item>
        <el-dropdown-item
          command="en-US"
          :disabled="currentLocale === 'en-US'"
        >
          {{ $t('language.en') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Position } from '@element-plus/icons-vue'
import { loadLocaleMessages } from '@/i18n'

const { locale } = useI18n()

const currentLocale = computed(() => locale.value)

const handleLanguageChange = async (command: string) => {
  await loadLocaleMessages(command)
}
</script>
