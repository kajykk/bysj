<template>
  <el-dropdown
    trigger="click"
    @command="handleThemeChange"
  >
    <el-button circle>
      <el-icon>
        <Sunny v-if="theme === 'light'" />
        <Moon v-else-if="theme === 'dark'" />
        <SemiSelect v-else />
      </el-icon>
    </el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item
          command="light"
          :disabled="theme === 'light'"
        >
          <el-icon><Sunny /></el-icon>
          {{ $t('theme.light') }}
        </el-dropdown-item>
        <el-dropdown-item
          command="dark"
          :disabled="theme === 'dark'"
        >
          <el-icon><Moon /></el-icon>
          {{ $t('theme.dark') }}
        </el-dropdown-item>
        <el-dropdown-item
          command="auto"
          :disabled="theme === 'auto'"
        >
          <el-icon><SemiSelect /></el-icon>
          {{ $t('theme.auto') }}
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { useTheme } from '@/composables/useTheme'
import { Sunny, Moon, SemiSelect } from '@element-plus/icons-vue'

const { theme, setTheme } = useTheme()

const handleThemeChange = (command: string) => {
  setTheme(command as 'light' | 'dark' | 'auto')
}
</script>
