/**
 * ECharts 按需引入统一入口
 *
 * 性能优化：从 `import * as echarts from 'echarts'`（全量引入 ~800KB）
 * 改为按需引入（~300KB），仅注册项目实际使用的图表与组件。
 *
 * R-007 优化：移除未实际使用的 RadarChart / RadarComponent（全代码库搜索无 `type: 'radar'` 配置），
 * 减小 echarts chunk 体积。HeatmapChart + VisualMapComponent 仅在 ConfusionChart.vue 使用，
 * 通过 vite.config.ts manualChunks 拆分到独立 chunk，仅实验页面加载。
 *
 * 使用方式：
 *   import { echarts, type ECharts, type EChartsCoreOption } from '@/utils/echarts'
 */
import * as echarts from 'echarts/core'
import { LineChart, BarChart, PieChart, HeatmapChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  ToolboxComponent,
  DataZoomComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// 注册项目实际使用的图表与组件
echarts.use([
  LineChart,
  BarChart,
  PieChart,
  HeatmapChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  ToolboxComponent,
  DataZoomComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export { echarts }
export type { ECharts, EChartsCoreOption } from 'echarts/core'
export { graphic } from 'echarts/core'
