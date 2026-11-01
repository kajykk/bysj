<template>
  <el-dropdown
    trigger="click"
    @command="handleThemeChange"
  >
    <el-button circle>
      <el-icon>
        <AppIcon :name="theme === 'light' ? 'sun' : theme === 'dark' ? 'moon' : 'circle-half-2'" />
      </el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          command="light"
          :disabled="theme === 'light'"
        >
          <el-icon><AppIcon name="sun" /></el-icon>
          {{ $t('theme.light') }}
        </el-dropdown-item>
        <el-dropdown-item
          command="dark"
          :disabled="theme === 'dark'"
        >
          <el-icon><AppIcon name="moon" /></el-icon>
          {{ $t('theme.dark') }}
        </el-dropdown-item>
        <el-dropdown-item
          command="auto"
          :disabled="theme === 'auto'"
        >
          <el-icon><AppIcon name="circle-half-2" /></el-icon>
          {{ $t('theme.auto') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import AppIcon from '@/components/common/AppIcon.vue'

const { theme, setTheme } = useTheme()

const handleThemeChange = (command: string) => {
  setTheme(command as 'light' | 'dark' | 'auto')
}
</script>
