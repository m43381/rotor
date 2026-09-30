<script setup lang="ts">
// График ECharts в общей теме приложения: светлая и тёмная темы переключаются вместе
// с интерфейсом, модули регистрируются один раз здесь, а не в каждом экране.
import { BarChart, BoxplotChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  CalendarComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import { useTheme } from '@/theme'

use([
  BarChart,
  BoxplotChart,
  HeatmapChart,
  LineChart,
  ScatterChart,
  CalendarComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

withDefaults(defineProps<{ option: Record<string, unknown>; height?: string; label?: string }>(), {
  height: '280px',
  label: undefined,
})
const { chartTheme } = useTheme()
</script>

<template>
  <div class="chart" :style="{ height }" role="img" :aria-label="label">
    <VChart :key="chartTheme" :option="option" :theme="chartTheme" autoresize />
  </div>
</template>

<style scoped>
.chart {
  width: 100%;
  min-width: 0;
}
</style>
