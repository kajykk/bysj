<template>
  <div>
    <!-- ISS-083 TODO：小屏下表格列过多时可考虑横向滚动优化或列优先级隐藏策略 -->
    <!-- ISS-088 TODO：批量操作时建议补充进度条/Toast 反馈（如"已处理 X/Y 条"），增强长时间任务的可感知性 -->
    <!-- ISS-105 TODO：分页器在小屏可考虑精简 layout（如 total, prev, pager, next），避免 sizes 选择器挤压 -->
    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="data"
      border
      style="width: 100%"
      :row-class-name="combinedRowClassName"
      @selection-change="handleSelectionChange"
    >
      <slot />
    </el-table>

    <div class="pager-wrap">
      <!-- ISS-087 修复：批量操作时显示选中数量 -->
      <span
        v-if="selectedCount > 0"
        class="selection-count"
      >
        {{ t('common.selectedCount', { count: selectedCount }) }}
      </span>
      <el-pagination
        background
        layout="total, sizes, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        :page-sizes="[10, 20, 50, 100]"
        @current-change="(value) => $emit('update:page', value)"
        @size-change="(value) => $emit('update:pageSize', value)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  loading: boolean
  data: unknown[]
  total: number
  page: number
  pageSize: number
  rowClassName?: (params: { row: unknown; rowIndex: number }) => string
  tableKey?: string
}>()

const emit = defineEmits<{
  'update:page': [value: number]
  'update:pageSize': [value: number]
  'selection-change': [rows: unknown[]]
}>()

const { t } = useI18n()

// ISS-087 修复：跟踪选中行数量，供分页区显示
const selectedCount = ref(0)
const handleSelectionChange = (rows: unknown[]) => {
  selectedCount.value = Array.isArray(rows) ? rows.length : 0
  emit('selection-change', rows)
}

const tableRef = ref()
const highlightedRows = ref<Set<string | number>>(new Set())
// P1-D-9 修复：将 observer 和 timers 提升到组件作用域，便于卸载时清理
let mutationObserver: MutationObserver | null = null
const highlightTimers = new Set<ReturnType<typeof setTimeout>>()

const getRowKey = (row: unknown): string | number => {
  const r = row as Record<string, unknown>
  return (r.id ?? r.key ?? JSON.stringify(row)) as string | number
}

const combinedRowClassName = (params: { row: unknown; rowIndex: number }) => {
  const classes: string[] = []
  if (props.rowClassName) {
    const customClass = props.rowClassName(params)
    if (customClass) classes.push(customClass)
  }
  const key = getRowKey(params.row)
  if (highlightedRows.value.has(key)) {
    classes.push('row-highlight-animation')
  }
  return classes.join(' ')
}

watch(() => props.data, (newData, oldData) => {
  if (!oldData || oldData.length === 0) return
  const oldKeys = new Set(oldData.map((row: unknown) => getRowKey(row)))
  const newRows = newData.filter((row: unknown) => !oldKeys.has(getRowKey(row)))

  newRows.forEach((row: unknown) => {
    const key = getRowKey(row)
    highlightedRows.value.add(key)
    // P1-D-9 修复：保存 timer ID 以便卸载时清理
    const timer = setTimeout(() => {
      highlightedRows.value.delete(key)
      highlightTimers.delete(timer)
    }, 2000)
    highlightTimers.add(timer)
  })
}, { deep: true })

onMounted(() => {
  if (props.tableKey && tableRef.value) {
    const savedWidths = localStorage.getItem(`table_widths_${props.tableKey}`)
    if (savedWidths) {
      try {
        const widths = JSON.parse(savedWidths)
        const cols = tableRef.value.$el.querySelectorAll('.el-table__header th')
        cols.forEach((col: HTMLElement, index: number) => {
          if (widths[index]) {
            col.style.width = widths[index]
          }
        })
      } catch {
        // ignore parse error
      }
    }

    const observer = new MutationObserver(() => {
      const cols = tableRef.value?.$el.querySelectorAll('.el-table__header th')
      if (!cols) return
      const widths = Array.from(cols).map((col: unknown) => (col as HTMLElement).style.width || getComputedStyle(col as HTMLElement).width)
      localStorage.setItem(`table_widths_${props.tableKey}`, JSON.stringify(widths))
    })
    mutationObserver = observer

    const header = tableRef.value?.$el.querySelector('.el-table__header')
    if (header) {
      observer.observe(header, { attributes: true, subtree: true, attributeFilter: ['style'] })
    }
  }
})

// P1-D-9 修复：组件卸载时清理 MutationObserver 和所有 setTimeout
onBeforeUnmount(() => {
  if (mutationObserver) {
    mutationObserver.disconnect()
    mutationObserver = null
  }
  highlightTimers.forEach((timer) => clearTimeout(timer))
  highlightTimers.clear()
})
</script>

<style scoped>
.pager-wrap {
  margin-top: var(--spacing-md);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-md);
}

/* ISS-087 修复：选中数量提示样式 */
.selection-count {
  margin-right: auto;
  font-size: var(--font-size-small);
  color: var(--primary-color);
  font-weight: var(--font-weight-medium);
}
</style>

<style>
/* ISS-031 修复：行高亮颜色改用设计系统令牌，深色模式自动跟随 --row-highlight-bg */
.row-highlight-animation {
  animation: rowHighlight 2s ease-out;
}

@keyframes rowHighlight {
  0% {
    background-color: var(--row-highlight-bg, #ecf5ff);
  }
  100% {
    background-color: transparent;
  }
}
</style>
