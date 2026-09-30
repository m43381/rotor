// Оформление (фаза 8): пресет PrimeVue, светлая и тёмная тема, темы графиков ECharts.
// Цвета — из одной палитры: основной цвет интерфейса — синий первой серии графиков,
// поверхности — тёплые нейтральные, категориальные цвета графиков проверены на различимость
// (в том числе при нарушениях цветового зрения) отдельно для светлой и тёмной темы.
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'
import { registerTheme } from 'echarts/core'
import { computed, ref } from 'vue'

const BLUE = {
  50: '#eef5fd',
  100: '#cde2fb',
  200: '#9ec5f4',
  300: '#6da7ec',
  400: '#3987e5',
  500: '#2a78d6',
  600: '#256abf',
  700: '#1c5cab',
  800: '#184f95',
  900: '#104281',
  950: '#0d366b',
}
const NEUTRAL = {
  0: '#ffffff',
  50: '#f9f9f7',
  100: '#f0efec',
  200: '#e1e0d9',
  300: '#c3c2b7',
  400: '#a3a29a',
  500: '#898781',
  600: '#6b6a65',
  700: '#52514e',
  800: '#383835',
  900: '#252523',
  950: '#1a1a19',
}

export const DutyFlowPreset = definePreset(Aura, {
  semantic: {
    primary: BLUE,
    colorScheme: {
      light: { surface: NEUTRAL },
      dark: { surface: NEUTRAL },
    },
  },
})

// --- палитра графиков ---------------------------------------------------------------------------
// Порядок слотов — часть проверки различимости: цвета берутся строго по порядку, не по кругу.
export const SERIES = {
  light: ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'],
  dark: ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'],
}
/** Последовательная шкала (одна синяя гамма) — для тепловых карт и календаря. */
export const SEQUENTIAL = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
export const SEQUENTIAL_DARK = ['#1f2f45', '#184f95', '#1c5cab', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4']

const CHROME = {
  light: { ink: '#0b0b0b', secondary: '#52514e', muted: '#898781', grid: '#e1e0d9', axis: '#c3c2b7', tip: '#ffffff' },
  dark: { ink: '#f4f3ef', secondary: '#c3c2b7', muted: '#898781', grid: '#2c2c2a', axis: '#383835', tip: '#252523' },
}

function chartTheme(mode: 'light' | 'dark') {
  const c = CHROME[mode]
  const axis = {
    axisLine: { lineStyle: { color: c.axis } },
    axisTick: { show: false },
    axisLabel: { color: c.muted },
    splitLine: { lineStyle: { color: c.grid } },
    nameTextStyle: { color: c.muted },
  }
  return {
    color: SERIES[mode],
    backgroundColor: 'transparent',
    textStyle: { color: c.secondary, fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' },
    title: { textStyle: { color: c.ink } },
    legend: { textStyle: { color: c.secondary }, icon: 'roundRect', itemWidth: 12, itemHeight: 8 },
    tooltip: {
      backgroundColor: c.tip,
      borderColor: c.grid,
      textStyle: { color: c.ink },
      extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,0.12); border-radius: 8px;',
    },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: { ...axis, axisLine: { show: false } },
    line: { symbolSize: 8, lineStyle: { width: 2 } },
    bar: { itemStyle: { borderRadius: 4 } },
    visualMap: { textStyle: { color: c.secondary } },
    calendar: {
      itemStyle: { color: 'transparent', borderColor: c.grid },
      splitLine: { lineStyle: { color: c.axis } },
      dayLabel: { color: c.muted },
      monthLabel: { color: c.secondary },
      yearLabel: { show: false },
    },
  }
}
registerTheme('dutyflow-light', chartTheme('light'))
registerTheme('dutyflow-dark', chartTheme('dark'))

// --- переключение темы -------------------------------------------------------------------------
type Mode = 'light' | 'dark'
const KEY = 'dutyflow.theme'

function initial(): Mode {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* хранилище недоступно — берём системную настройку */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

const mode = ref<Mode>(initial())

function apply(value: Mode) {
  const root = document.documentElement
  root.classList.toggle('app-dark', value === 'dark')
  root.dataset.theme = value
  root.style.colorScheme = value
}
apply(mode.value)

export function useTheme() {
  const isDark = computed(() => mode.value === 'dark')
  function toggle() {
    mode.value = isDark.value ? 'light' : 'dark'
    apply(mode.value)
    try {
      localStorage.setItem(KEY, mode.value)
    } catch {
      /* не запомнили — тема продержится до перезагрузки */
    }
  }
  return {
    mode,
    isDark,
    toggle,
    chartTheme: computed(() => (isDark.value ? 'dutyflow-dark' : 'dutyflow-light')),
    series: computed(() => SERIES[mode.value]),
    sequential: computed(() => (isDark.value ? SEQUENTIAL_DARK : SEQUENTIAL)),
    /** Цвет подписей значений на графиках — текстовый, а не цвет серии */
    ink: computed(() => CHROME[mode.value].secondary),
  }
}
