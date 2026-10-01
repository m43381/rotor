<script setup lang="ts">
// Аналитика нагрузки (фазы 6c и 8): сводка и справедливость по поддереву за период, разрезы
// по подразделениям, нарядам, ролям, категориям и званиям, дням недели и месяцам, календарь,
// распределение нагрузки на человека и таблица людей. Данные — read-model analytics.
// Все графики — в общей теме; у каждого разреза есть табличный вид.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import TabPanel from 'primevue/tabpanel'
import TabPanels from 'primevue/tabpanels'
import Tabs from 'primevue/tabs'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { analytics, ApiError, documents, saveFile, unwrap, type Overview } from '@/api/client'
import AppChart from '@/components/AppChart.vue'
import StatStrip, { type Stat } from '@/components/StatStrip.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { useTheme } from '@/theme'
import { formatDate, fromIso, toIso } from '@/utils/dates'

const units = useUnitsStore()
const toast = useToast()
const route = useRoute()
const theme = useTheme()

// --- фильтры -----------------------------------------------------------------------------------
type Preset = 'month' | 'prev' | 'quarter' | 'half' | 'year'
const PRESETS: { value: Preset; label: string }[] = [
  { value: 'month', label: 'Месяц' },
  { value: 'prev', label: 'Прошлый' },
  { value: 'quarter', label: '3 мес.' },
  { value: 'half', label: '6 мес.' },
  { value: 'year', label: '12 мес.' },
]
const unitId = ref<string | null>(null)
const preset = ref<Preset | null>('month')
const range = ref<Date[]>(presetRange('month'))
const drafts = ref(false)
const tab = ref('overview')

function presetRange(p: Preset): Date[] {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth()
  const first = (dy: number, dm: number) => new Date(dy, dm, 1)
  const last = (dy: number, dm: number) => new Date(dy, dm + 1, 0)
  switch (p) {
    case 'prev':
      return [first(y, m - 1), last(y, m - 1)]
    case 'quarter':
      return [first(y, m - 2), last(y, m)]
    case 'half':
      return [first(y, m - 5), last(y, m)]
    case 'year':
      return [first(y, m - 11), last(y, m)]
    default:
      return [first(y, m), last(y, m)]
  }
}
const period = computed(() => {
  const [from, to] = range.value
  return from && to ? { date_from: toIso(from), date_to: toIso(to) } : null
})
const query = computed(() =>
  unitId.value && period.value ? { unit_id: unitId.value, ...period.value, drafts: drafts.value } : null,
)

// --- данные ------------------------------------------------------------------------------------
type Dim = 'unit' | 'duty_type' | 'role' | 'category' | 'rank' | 'weekday' | 'month' | 'source' | 'day_kind'
interface BreakdownItem {
  key: string | null
  label: string
  split_key: string | null
  split_label: string | null
  duties: number
  duty_days: number
  load: number
  people: number
  holidays: number
  load_per_person: number
}
interface DistItem {
  label: string
  people: number
  min: number
  q1: number
  median: number
  q3: number
  max: number
  mean: number
  gini: number
}
interface CalendarDay {
  date: string
  duties: number
  load: number
  people: number
}

const data = ref<Overview | null>(null)
const loading = ref(false)
const breakdowns = ref<Record<string, BreakdownItem[]>>({})
const distribution = ref<DistItem[]>([])
const calendar = ref<CalendarDay[]>([])

function showError(e: unknown, fallback = 'Аналитика недоступна') {
  const detail = e instanceof ApiError ? e.message : fallback
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

async function loadOverview() {
  const q = query.value
  if (!q) return
  loading.value = true
  try {
    data.value = await unwrap(analytics.GET('/metrics/overview', { params: { query: q } }))
  } catch (e) {
    data.value = null
    showError(e)
  } finally {
    loading.value = false
  }
}

async function breakdown(dimension: Dim, split: Dim | null = null): Promise<BreakdownItem[]> {
  const q = query.value
  if (!q) return []
  const key = `${dimension}|${split ?? ''}`
  const cached = breakdowns.value[key]
  if (cached) return cached
  try {
    const r = await unwrap(
      analytics.GET('/metrics/breakdown', {
        params: { query: { ...q, dimension, split: split ?? undefined } },
      }),
    )
    breakdowns.value = { ...breakdowns.value, [key]: r.items }
    return r.items
  } catch (e) {
    showError(e)
    return []
  }
}
const items = (dimension: Dim, split: Dim | null = null) => breakdowns.value[`${dimension}|${split ?? ''}`] ?? []

async function loadTab() {
  if (!query.value) return
  switch (tab.value) {
    case 'overview':
      await Promise.all([breakdown('weekday'), breakdown('duty_type'), breakdown('category'), breakdown('source')])
      break
    case 'pivot':
      await breakdown(pivotDim.value, pivotSplit.value)
      break
    case 'fairness':
      await loadDistribution()
      break
    case 'calendar':
      await Promise.all([loadCalendar(), breakdown('weekday', 'month')])
      break
    case 'people':
      await loadPeople()
      break
  }
}

async function loadDistribution() {
  const q = query.value
  if (!q) return
  try {
    const r = await unwrap(
      analytics.GET('/metrics/distribution', { params: { query: { ...q, dimension: distDim.value } } }),
    )
    distribution.value = r.items
  } catch (e) {
    showError(e)
  }
}
async function loadCalendar() {
  const q = query.value
  if (!q) return
  try {
    calendar.value = await unwrap(analytics.GET('/metrics/calendar', { params: { query: q } }))
  } catch (e) {
    showError(e)
  }
}

async function reloadAll() {
  breakdowns.value = {}
  peopleFirst.value = 0
  await Promise.all([loadOverview(), loadTab()])
}

watch(preset, (p) => {
  if (p) range.value = presetRange(p)
})
watch([unitId, range, drafts], () => {
  if (range.value.every(Boolean)) void reloadAll()
})
watch(tab, () => void loadTab())

onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  // Ссылка может задать подразделение, период и черновики: ?unit=&from=&to=&drafts=1
  const q = route.query
  if (typeof q.from === 'string' && typeof q.to === 'string') {
    preset.value = null
    range.value = [fromIso(q.from), fromIso(q.to)]
  }
  drafts.value = q.drafts === '1'
  unitId.value = (typeof q.unit === 'string' && q.unit) || (units.me?.unit.id ?? null)
})

async function report(format: 'pdf' | 'xlsx') {
  if (!query.value) return
  try {
    await saveFile(
      documents.GET('/print/load-report', { params: { query: { ...query.value, format } }, parseAs: 'blob' }),
      `load.${format}`,
    )
  } catch (e) {
    showError(e, 'Не удалось подготовить отчёт')
  }
}

// --- сводка --------------------------------------------------------------------------------------
const fmt = (x: number | undefined, digits = 2) =>
  x === undefined ? '—' : x.toLocaleString('ru-RU', { maximumFractionDigits: digits })

/** Коэффициент Джини словами: 0 — у всех поровну, чем больше — тем сильнее перекос. */
function evenness(gini: number | undefined): { label: string; state: Stat['state'] } {
  if (gini === undefined) return { label: '—', state: undefined }
  if (gini < 0.1) return { label: 'Высокая', state: 'good' }
  if (gini < 0.2) return { label: 'Хорошая', state: 'good' }
  if (gini < 0.3) return { label: 'Есть перекос', state: 'warn' }
  return { label: 'Сильный перекос', state: 'critical' }
}

const stats = computed<Stat[]>(() => {
  const d = data.value
  const e = evenness(d?.fairness.load?.gini)
  return [
    { key: 'people', label: 'Людей в нарядах', value: fmt(d?.totals.people, 0), sub: 'был хотя бы один наряд' },
    { key: 'duties', label: 'Нарядов', value: fmt(d?.totals.duties, 0), sub: `${fmt(d?.totals.duty_days, 0)} нарядо-суток` },
    {
      key: 'load',
      label: 'Нагрузка',
      value: fmt(d?.totals.load, 1),
      sub: `в среднем ${fmt(d?.fairness.load?.mean, 2)} на человека`,
    },
    {
      key: 'fair',
      label: 'Равномерность',
      value: e.label,
      state: e.state,
      stateText: `Джини ${fmt(d?.fairness.load?.gini, 3)} · Джайн ${fmt(d?.fairness.load?.jain, 3)}`,
    },
    {
      key: 'range',
      label: 'Разрыв в нарядах',
      value: fmt(d?.fairness.count?.range, 0),
      sub: `от ${fmt(d?.fairness.count?.min, 0)} до ${fmt(d?.fairness.count?.max, 0)} на человека`,
    },
    {
      key: 'holidays',
      label: 'Выходные и праздники',
      value: fmt(d?.totals.holidays, 0),
      sub: d?.totals.duties ? `${Math.round(((d.totals.holidays ?? 0) / d.totals.duties) * 100)}% нарядов` : '',
    },
  ]
})

// --- общие части графиков ------------------------------------------------------------------------
const tooltipAxis = { trigger: 'axis', axisPointer: { type: 'shadow' } }

function hbar(labels: string[], values: number[], name: string, digits = 2) {
  return {
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    tooltip: { ...tooltipAxis, valueFormatter: (v: number) => fmt(v, digits) },
    xAxis: { type: 'value', splitNumber: 4 },
    yAxis: { type: 'category', inverse: true, data: labels, axisLabel: { width: 170, overflow: 'truncate' } },
    series: [
      {
        name,
        type: 'bar',
        data: values,
        barMaxWidth: 18,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
        label: {
          show: true,
          position: 'right',
          fontSize: theme.fs(11),
          color: theme.ink.value,
          textBorderWidth: 0,
          formatter: (p: { value: number }) => fmt(p.value, digits),
        },
      },
    ],
  }
}
const barsHeight = (n: number) => `${Math.max(160, n * 30 + 24)}px`
const surface = computed(() => (theme.isDark.value ? '#1a1a19' : '#ffffff'))

// --- обзор ---------------------------------------------------------------------------------------
function monthLabel(ym: string): string {
  const [y, m] = ym.split('-').map(Number)
  return new Date(y ?? 1970, (m ?? 1) - 1, 1).toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' })
}
const trendLoadOption = computed(() => {
  const t = data.value?.trend ?? []
  return {
    grid: { left: 44, right: 16, top: 20, bottom: 28 },
    tooltip: { ...tooltipAxis, valueFormatter: (v: number) => fmt(v, 1) },
    xAxis: { type: 'category', data: t.map((x) => monthLabel(String(x.month))) },
    yAxis: { type: 'value', name: 'нагрузка' },
    series: [
      {
        name: 'Нагрузка',
        type: 'bar',
        data: t.map((x) => x.load),
        barMaxWidth: 36,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
})
const trendGiniOption = computed(() => {
  const t = data.value?.trend ?? []
  const color = theme.series.value[1]
  return {
    grid: { left: 44, right: 16, top: 20, bottom: 28 },
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmt(v, 3) },
    xAxis: { type: 'category', data: t.map((x) => monthLabel(String(x.month))), boundaryGap: false },
    yAxis: { type: 'value', min: 0, max: (v: { max: number }) => Math.max(0.4, Math.ceil(v.max * 10) / 10) },
    series: [
      {
        name: 'Коэффициент Джини',
        type: 'line',
        data: t.map((x) => x.gini),
        itemStyle: { color },
        lineStyle: { color, width: 2 },
        areaStyle: { opacity: 0.08, color },
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(12,163,12,0.07)' },
          label: { show: true, position: 'insideTopLeft', formatter: 'ровно', fontSize: theme.fs(11) },
          data: [[{ yAxis: 0 }, { yAxis: 0.2 }]],
        },
      },
    ],
  }
})

const unitRows = computed(() => (data.value?.units ?? []).filter((u) => u.people > 0))
const unitsOption = computed(() =>
  hbar(
    unitRows.value.map((u) => (u.own ? `${u.unit_name} (само)` : u.unit_name)),
    unitRows.value.map((u) => u.load_per_person),
    'Нагрузка на человека',
  ),
)
const weekdayOption = computed(() => {
  const w = items('weekday')
  const [c0, c1] = theme.series.value
  return {
    grid: { left: 40, right: 12, top: 20, bottom: 28 },
    tooltip: tooltipAxis,
    xAxis: { type: 'category', data: w.map((i) => i.label) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        name: 'Нарядов',
        type: 'bar',
        barMaxWidth: 34,
        data: w.map((i) => ({
          value: i.duties,
          // Суббота и воскресенье — вторым цветом, чтобы выходные читались сразу
          itemStyle: { color: ['Сб', 'Вс'].includes(i.label) ? c1 : c0, borderRadius: [4, 4, 0, 0] },
        })),
      },
    ],
  }
})
const dutyTypeOption = computed(() => {
  const d = [...items('duty_type')].sort((a, b) => b.load - a.load)
  return hbar(
    d.map((i) => i.label),
    d.map((i) => i.load),
    'Нагрузка',
    1,
  )
})
const categoryOption = computed(() => {
  const c = items('category')
  return hbar(
    c.map((i) => i.label),
    c.map((i) => i.load_per_person),
    'Нагрузка на человека',
  )
})
const sourceShare = computed(() => {
  const s = items('source')
  const total = s.reduce((n, i) => n + i.duties, 0)
  return s.map((i) => ({ label: i.label, duties: i.duties, pct: total ? Math.round((i.duties / total) * 100) : 0 }))
})

// --- конструктор -------------------------------------------------------------------------------
const DIMS: { value: Dim; label: string }[] = [
  { value: 'unit', label: 'Подразделение' },
  { value: 'duty_type', label: 'Наряд' },
  { value: 'role', label: 'Роль' },
  { value: 'category', label: 'Категория личного состава' },
  { value: 'rank', label: 'Звание' },
  { value: 'weekday', label: 'День недели' },
  { value: 'month', label: 'Месяц' },
  { value: 'source', label: 'Способ назначения' },
  { value: 'day_kind', label: 'Будни / выходные' },
]
type Metric = 'duties' | 'duty_days' | 'load' | 'people' | 'load_per_person'
const METRICS: { value: Metric; label: string; digits: number; additive: boolean }[] = [
  { value: 'duties', label: 'Нарядов', digits: 0, additive: true },
  { value: 'duty_days', label: 'Нарядо-суток', digits: 0, additive: true },
  { value: 'load', label: 'Нагрузка', digits: 1, additive: true },
  { value: 'people', label: 'Людей', digits: 0, additive: false },
  { value: 'load_per_person', label: 'Нагрузка на человека', digits: 2, additive: false },
]
type View = 'bar' | 'hbar' | 'stack' | 'share' | 'heatmap'
const pivotDim = ref<Dim>('unit')
const pivotSplit = ref<Dim | null>(null)
const pivotMetric = ref<Metric>('load')
const pivotView = ref<View>('hbar')
const metricInfo = computed(() => METRICS.find((m) => m.value === pivotMetric.value) ?? METRICS[0]!)
const VIEWS: { value: View; label: string; icon: string }[] = [
  { value: 'hbar', label: 'Полосы', icon: 'pi pi-align-left' },
  { value: 'bar', label: 'Столбцы', icon: 'pi pi-chart-bar' },
  { value: 'stack', label: 'Накопление', icon: 'pi pi-server' },
  { value: 'share', label: 'Доли, %', icon: 'pi pi-percentage' },
  { value: 'heatmap', label: 'Тепловая карта', icon: 'pi pi-th-large' },
]
// Накопление, доли и тепловая карта сравнивают группы по второму измерению: без разбивки
// им нечего показать, а складывать и делить на доли можно только суммируемые показатели.
// Вид не блокируется молча — недостающее подставляется, и об этом говорит подсказка.
const needsSplit = (v: View) => v === 'stack' || v === 'share' || v === 'heatmap'
const needsAdditive = (v: View) => v === 'stack' || v === 'share'
const SPLIT_DEFAULTS: Dim[] = ['duty_type', 'category', 'day_kind', 'unit']
const dimLabel = (d: Dim | null) => DIMS.find((x) => x.value === d)?.label.toLowerCase() ?? ''
// Что подставлено автоматически; подсказка гаснет, как только пользователь выберет своё
const autoSplit = ref<Dim | null>(null)
const autoMetric = ref(false)
watch(pivotView, (v) => {
  autoSplit.value = null
  autoMetric.value = false
  if (needsSplit(v) && !pivotSplit.value) {
    pivotSplit.value = SPLIT_DEFAULTS.find((d) => d !== pivotDim.value) ?? null
    autoSplit.value = pivotSplit.value
  }
  if (needsAdditive(v) && !metricInfo.value.additive) {
    pivotMetric.value = 'load'
    autoMetric.value = true
  }
})
watch([pivotSplit, pivotMetric], () => {
  const v = pivotView.value
  if (needsSplit(v) && !pivotSplit.value) pivotView.value = 'hbar'
  else if (needsAdditive(v) && !metricInfo.value.additive) pivotView.value = 'bar'
})
const pivotNote = computed(() => {
  const notes: string[] = []
  if (autoSplit.value && autoSplit.value === pivotSplit.value) notes.push(`разбивка «${dimLabel(autoSplit.value)}»`)
  if (autoMetric.value && pivotMetric.value === 'load') notes.push('показатель «нагрузка» — людей и нагрузку на человека складывать нельзя')
  return notes.length ? `Для этого вида автоматически выбраны ${notes.join('; ')}.` : ''
})
watch(pivotDim, (d) => {
  if (pivotSplit.value === d) pivotSplit.value = SPLIT_DEFAULTS.find((x) => x !== d) ?? null
})
watch([pivotDim, pivotSplit], () => void breakdown(pivotDim.value, pivotSplit.value))
const splitOptions = computed(() => [
  { value: null, label: 'Без разбивки' },
  ...DIMS.filter((d) => d.value !== pivotDim.value),
])

const pivotRows = computed(() => items(pivotDim.value, pivotSplit.value))
const ORDERED = new Set<Dim | null>(['weekday', 'month', 'rank', 'day_kind'])
const MAX_SERIES = 8 // категориальных цветов восемь; остальное сворачивается в «Прочие»

const pivotOption = computed(() => {
  const rows = pivotRows.value
  const metric = pivotMetric.value
  const info = metricInfo.value
  // Группы без собственного порядка — по убыванию показателя: так сравнивать легче всего
  const catTotals = new Map<string, number>()
  for (const r of rows) catTotals.set(r.label, (catTotals.get(r.label) ?? 0) + r[metric])
  const cats = ORDERED.has(pivotDim.value)
    ? [...catTotals.keys()]
    : [...catTotals.entries()].sort((a, b) => b[1] - a[1]).map(([c]) => c)
  const catIndex = new Map(cats.map((c, i) => [c, i]))
  const view = pivotView.value
  const horizontal = view === 'hbar' || view === 'share'
  const catAxis = {
    type: 'category',
    data: cats,
    inverse: horizontal,
    axisLabel: horizontal ? { width: 170, overflow: 'truncate' } : { interval: 0, rotate: cats.length > 8 ? 30 : 0 },
  }
  const valueAxis = {
    type: 'value',
    max: view === 'share' ? 100 : undefined,
    axisLabel: view === 'share' ? { formatter: '{value}%' } : {},
  }
  const grid = { left: 8, right: 24, top: 36, bottom: 8, containLabel: true }

  if (!pivotSplit.value) {
    const values = cats.map((c) => rows.find((r) => r.label === c)?.[metric] ?? 0)
    return {
      grid,
      tooltip: { ...tooltipAxis, valueFormatter: (v: number) => fmt(v, info.digits) },
      xAxis: horizontal ? valueAxis : catAxis,
      yAxis: horizontal ? catAxis : valueAxis,
      series: [
        {
          name: info.label,
          type: 'bar',
          data: values,
          barMaxWidth: 28,
          itemStyle: { borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
          label: {
            show: cats.length <= 24,
            position: horizontal ? 'right' : 'top',
            fontSize: theme.fs(11),
            color: theme.ink.value,
            textBorderWidth: 0,
            formatter: (p: { value: number }) => fmt(p.value, info.digits),
          },
        },
      ],
    }
  }

  // Второе измерение: не больше восьми серий, остальные — «Прочие» (для суммируемых показателей)
  const totals = new Map<string, number>()
  for (const r of rows) totals.set(r.split_label ?? '—', (totals.get(r.split_label ?? '—') ?? 0) + r[metric])
  // У упорядоченных измерений (дни недели, месяцы, звания) — их порядок, у остальных — по убыванию
  let series = ORDERED.has(pivotSplit.value)
    ? [...totals.keys()]
    : [...totals.entries()].sort((a, b) => b[1] - a[1]).map(([s]) => s)
  let other = false
  if (series.length > MAX_SERIES) {
    other = info.additive
    series = series.slice(0, info.additive ? MAX_SERIES - 1 : MAX_SERIES)
  }
  const seriesIndex = new Map(series.map((s, i) => [s, i]))
  const matrix = series.map(() => cats.map(() => 0))
  const otherRow = cats.map(() => 0)
  for (const r of rows) {
    const ci = catIndex.get(r.label)
    if (ci === undefined) continue
    const si = seriesIndex.get(r.split_label ?? '—')
    if (si !== undefined) matrix[si]![ci] = r[metric]
    else if (other) otherRow[ci] = (otherRow[ci] ?? 0) + r[metric]
  }
  const names = other ? [...series, 'Прочие'] : series
  const values = other ? [...matrix, otherRow] : matrix

  if (view === 'heatmap') {
    const cells: [number, number, number][] = []
    values.forEach((row, si) => row.forEach((v, ci) => cells.push([ci, si, v])))
    const max = Math.max(1, ...cells.map((c) => c[2]))
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 56, containLabel: true },
      tooltip: {
        formatter: (p: { value: [number, number, number] }) =>
          `${cats[p.value[0]]}<br/>${names[p.value[1]]}: <b>${fmt(p.value[2], info.digits)}</b>`,
      },
      xAxis: { type: 'category', data: cats, axisLabel: { interval: 0, rotate: cats.length > 6 ? 30 : 0 } },
      yAxis: { type: 'category', data: names, inverse: true, axisLabel: { width: 160, overflow: 'truncate' } },
      visualMap: {
        min: 0,
        max,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        itemHeight: 160,
        inRange: { color: theme.sequential.value },
      },
      series: [
        {
          name: info.label,
          type: 'heatmap',
          data: cells,
          label: {
            show: cats.length * names.length <= 120,
            fontSize: theme.fs(10),
            formatter: (p: { value: [number, number, number] }) => (p.value[2] ? fmt(p.value[2], info.digits) : ''),
          },
          itemStyle: { borderColor: surface.value, borderWidth: 2, borderRadius: 3 },
        },
      ],
    }
  }

  const stacked = view === 'stack' || view === 'share'
  const colSums = cats.map((_, ci) => values.reduce((n, row) => n + (row[ci] ?? 0), 0))
  return {
    grid,
    legend: { top: 0, type: 'scroll' },
    tooltip: {
      ...tooltipAxis,
      valueFormatter: (v: number) => (view === 'share' ? `${fmt(v, 1)}%` : fmt(v, info.digits)),
    },
    xAxis: horizontal ? valueAxis : catAxis,
    yAxis: horizontal ? catAxis : valueAxis,
    series: names.map((name, si) => ({
      name,
      type: 'bar',
      stack: stacked ? 'total' : undefined,
      barMaxWidth: stacked ? 30 : 16,
      // Промежуток между сегментами — цветом поверхности
      itemStyle: { borderColor: surface.value, borderWidth: stacked ? 1 : 0, borderRadius: stacked ? 0 : 3 },
      emphasis: { focus: 'series' },
      data:
        view === 'share'
          ? (values[si] ?? []).map((v, ci) => (colSums[ci] ? Math.round((v / colSums[ci]!) * 1000) / 10 : 0))
          : values[si],
    })),
  }
})
const pivotHeight = computed(() => {
  const n = new Set(pivotRows.value.map((r) => r.label)).size
  const splitN = pivotSplit.value ? new Set(pivotRows.value.map((r) => r.split_label)).size : 1
  if (pivotView.value === 'heatmap') return `${Math.max(240, Math.min(splitN, 9) * 34 + 120)}px`
  if (pivotView.value === 'hbar' || pivotView.value === 'share') {
    const per = pivotView.value === 'hbar' && pivotSplit.value ? Math.min(splitN, 8) * 12 + 14 : 32
    return `${Math.max(220, n * per + 60)}px`
  }
  return '360px'
})

// --- справедливость ----------------------------------------------------------------------------
const distDim = ref<Dim>('unit')
const DIST_DIMS = DIMS.filter((d) => d.value !== 'month' && d.value !== 'source')
watch(distDim, () => void loadDistribution())

const lorenzOption = computed(() => {
  const points = (data.value?.lorenz ?? []) as number[][]
  const [c0, c1] = theme.series.value
  const pct = (v: number) => `${Math.round(v * 100)}%`
  return {
    grid: { left: 48, right: 16, top: 36, bottom: 40 },
    legend: { top: 0 },
    tooltip: {
      trigger: 'axis',
      formatter: (p: { value: number[]; seriesName: string }[]) =>
        p
          .filter((x) => x.seriesName === 'Фактически')
          .map((x) => `${pct(x.value[0] ?? 0)} наименее загруженных несут ${pct(x.value[1] ?? 0)} нагрузки`)
          .join(''),
    },
    xAxis: { type: 'value', min: 0, max: 1, name: 'доля людей', nameLocation: 'middle', nameGap: 26, axisLabel: { formatter: pct } },
    yAxis: { type: 'value', min: 0, max: 1, name: 'доля нагрузки', axisLabel: { formatter: pct } },
    series: [
      {
        name: 'Поровну',
        type: 'line',
        data: [
          [0, 0],
          [1, 1],
        ],
        symbol: 'none',
        lineStyle: { type: 'dashed', width: 1.5, color: c1 },
        itemStyle: { color: c1 },
      },
      {
        name: 'Фактически',
        type: 'line',
        data: points,
        smooth: 0.2,
        symbolSize: 5,
        lineStyle: { width: 2, color: c0 },
        itemStyle: { color: c0 },
        areaStyle: { opacity: 0.1, color: c0 },
      },
    ],
  }
})
const histogramOption = computed(() => {
  const h = data.value?.histogram ?? []
  return {
    grid: { left: 40, right: 12, top: 20, bottom: 40 },
    tooltip: {
      ...tooltipAxis,
      formatter: (p: { name: string; value: number }[]) => `${p[0]?.name} нар.: ${p[0]?.value} чел.`,
    },
    xAxis: { type: 'category', name: 'нарядов у человека', nameLocation: 'middle', nameGap: 26, data: h.map((x) => x.duties) },
    yAxis: { type: 'value', minInterval: 1, name: 'людей' },
    series: [
      {
        type: 'bar',
        name: 'Людей',
        data: h.map((x) => x.people),
        barMaxWidth: 40,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
      },
    ],
  }
})
const boxOption = computed(() => {
  const d = distribution.value
  return {
    grid: { left: 8, right: 24, top: 16, bottom: 36, containLabel: true },
    tooltip: {
      trigger: 'item',
      formatter: (p: { dataIndex: number }) => {
        const i = d[p.dataIndex]
        return i
          ? `<b>${i.label}</b> · ${i.people} чел.<br/>минимум ${fmt(i.min)} · максимум ${fmt(i.max)}` +
              `<br/>половина людей — от ${fmt(i.q1)} до ${fmt(i.q3)}` +
              `<br/>медиана ${fmt(i.median)} · среднее ${fmt(i.mean)}<br/>Джини ${fmt(i.gini, 3)}`
          : ''
      },
    },
    xAxis: { type: 'value', name: 'нагрузка на человека', nameLocation: 'middle', nameGap: 26 },
    yAxis: { type: 'category', inverse: true, data: d.map((i) => i.label), axisLabel: { width: 170, overflow: 'truncate' } },
    series: [
      {
        name: 'Нагрузка',
        type: 'boxplot',
        data: d.map((i) => [i.min, i.q1, i.median, i.q3, i.max]),
        boxWidth: [8, 22],
        itemStyle: {
          color: theme.isDark.value ? 'rgba(57,135,229,0.25)' : 'rgba(42,120,214,0.15)',
          borderColor: theme.series.value[0],
          borderWidth: 1.5,
        },
      },
    ],
  }
})

// --- календарь -----------------------------------------------------------------------------------
type CalMetric = 'duties' | 'load' | 'people'
const calMetric = ref<CalMetric>('duties')
const CAL_METRICS: { value: CalMetric; label: string }[] = [
  { value: 'duties', label: 'Нарядов' },
  { value: 'load', label: 'Нагрузка' },
  { value: 'people', label: 'Людей' },
]
const calendarOption = computed(() => {
  const p = period.value
  const metric = calMetric.value
  const values = calendar.value.map((d) => [d.date, d[metric]])
  const max = Math.max(1, ...calendar.value.map((d) => d[metric]))
  const label = CAL_METRICS.find((m) => m.value === metric)?.label ?? ''
  return {
    tooltip: {
      formatter: (x: { value: [string, number] }) => `${formatDate(x.value[0])}<br/>${label}: <b>${fmt(x.value[1], 1)}</b>`,
    },
    visualMap: {
      min: 0,
      max,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 180,
      inRange: { color: theme.sequential.value },
    },
    calendar: {
      top: 36,
      left: 40,
      right: 16,
      bottom: 64,
      range: p ? [p.date_from, p.date_to] : undefined,
      cellSize: ['auto', 22],
      dayLabel: { firstDay: 1, nameMap: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'] },
      monthLabel: { nameMap: ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'] },
      itemStyle: { borderWidth: 2, borderColor: surface.value },
    },
    series: [{ type: 'heatmap', coordinateSystem: 'calendar', data: values }],
  }
})
const weekMonthOption = computed(() => {
  const rows = items('weekday', 'month')
  const days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
  const months = [...new Set(rows.map((r) => r.split_label ?? ''))].sort()
  const cells = rows.map((r) => [months.indexOf(r.split_label ?? ''), days.indexOf(r.label), r.duties])
  const max = Math.max(1, ...cells.map((c) => c[2] ?? 0))
  return {
    grid: { left: 8, right: 16, top: 8, bottom: 56, containLabel: true },
    tooltip: {
      formatter: (p: { value: number[] }) =>
        `${monthLabel(months[p.value[0] ?? 0] ?? '')}, ${days[p.value[1] ?? 0]}: <b>${p.value[2]}</b> нар.`,
    },
    xAxis: { type: 'category', data: months.map(monthLabel) },
    yAxis: { type: 'category', data: days, inverse: true },
    visualMap: {
      min: 0,
      max,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      itemHeight: 160,
      inRange: { color: theme.sequential.value },
    },
    series: [
      {
        type: 'heatmap',
        name: 'Нарядов',
        data: cells,
        label: { show: months.length <= 12, fontSize: theme.fs(10) },
        itemStyle: { borderColor: surface.value, borderWidth: 2, borderRadius: 3 },
      },
    ],
  }
})

// --- люди ----------------------------------------------------------------------------------------
interface PersonRow {
  person_id: string
  person_name: string
  duties: number
  duty_days: number
  load: number
  holidays: number
  last_date: string
}
const people = ref<PersonRow[]>([])
const peopleTotal = ref(0)
const peopleFirst = ref(0)
const peopleRows = ref(25)
const ascending = ref(false)
const peopleLoading = ref(false)
async function loadPeople() {
  const q = query.value
  if (!q) return
  peopleLoading.value = true
  try {
    const page = await unwrap(
      analytics.GET('/metrics/people', {
        params: { query: { ...q, limit: peopleRows.value, offset: peopleFirst.value, ascending: ascending.value } },
      }),
    )
    people.value = page.items
    peopleTotal.value = page.total
  } catch (e) {
    showError(e)
  } finally {
    peopleLoading.value = false
  }
}
function onPeoplePage(e: DataTablePageEvent) {
  peopleFirst.value = e.first
  peopleRows.value = e.rows
  void loadPeople()
}
watch(ascending, () => {
  peopleFirst.value = 0
  void loadPeople()
})
const mean = computed(() => data.value?.fairness.load?.mean ?? 0)
const maxLoad = computed(() => data.value?.fairness.load?.max || 1)
const topLoad = computed(() => data.value?.top[0]?.load || 1)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Аналитика</h1>
        <p class="muted">
          Нагрузка нарядами и справедливость распределения по подразделению и всем нижестоящим.
          Нагрузка — нарядо-сутки × вес роли.
        </p>
      </div>
      <div class="actions">
        <Button label="Отчёт PDF" icon="pi pi-file-pdf" severity="secondary" outlined size="small" @click="report('pdf')" />
        <Button label="Отчёт XLSX" icon="pi pi-file-excel" severity="secondary" outlined size="small" @click="report('xlsx')" />
      </div>
    </header>

    <div class="card filters">
      <div class="unit">
        <UnitTreeSelect v-model="unitId" placeholder="Подразделение" input-id="dash-unit" />
      </div>
      <SelectButton
        v-model="preset"
        :options="PRESETS"
        option-label="label"
        option-value="value"
        size="small"
        aria-label="Период"
      />
      <DatePicker
        v-model="range"
        selection-mode="range"
        date-format="dd.mm.yy"
        input-id="dash-range"
        show-icon
        class="range"
        @update:model-value="preset = null"
      />
      <label class="check">
        <Checkbox v-model="drafts" binary input-id="dash-drafts" />
        <span>Включая черновики</span>
      </label>
    </div>

    <StatStrip :items="stats" :loading="loading && !data" />

    <div v-if="data && data.totals.duties === 0" class="card empty-state">
      <i class="pi pi-chart-bar" />
      <strong>За период нарядов нет</strong>
      <span>Выберите другой период или включите черновики графиков.</span>
    </div>

    <Tabs v-else-if="data" v-model:value="tab" class="tabs">
      <TabList>
        <Tab value="overview"><i class="pi pi-th-large" /> Обзор</Tab>
        <Tab value="pivot"><i class="pi pi-sliders-h" /> Конструктор</Tab>
        <Tab value="fairness"><i class="pi pi-sort-amount-down" /> Справедливость</Tab>
        <Tab value="calendar"><i class="pi pi-calendar" /> Календарь</Tab>
        <Tab value="people"><i class="pi pi-users" /> Люди</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="overview">
          <div class="grid">
            <section class="card panel">
              <h2 class="panel-title">Нагрузка по месяцам</h2>
              <AppChart v-if="data.trend.length > 1" :option="trendLoadOption" height="240px" label="Нагрузка по месяцам" />
              <p v-else class="muted small">Выберите период длиннее месяца, чтобы увидеть динамику.</p>
            </section>
            <section class="card panel">
              <h2 class="panel-title">Неравномерность по месяцам</h2>
              <AppChart
                v-if="data.trend.length > 1"
                :option="trendGiniOption"
                height="240px"
                label="Коэффициент Джини по месяцам"
              />
              <p v-else class="muted small">
                Коэффициент Джини за период — {{ fmt(data.fairness.load?.gini, 3) }}: 0 — у всех поровну,
                1 — всё у одного.
              </p>
            </section>
            <section v-if="unitRows.length > 1" class="card panel">
              <h2 class="panel-title">Нагрузка на человека по подразделениям</h2>
              <AppChart
                :option="unitsOption"
                :height="barsHeight(unitRows.length)"
                label="Нагрузка на человека по подразделениям"
              />
            </section>
            <section class="card panel">
              <h2 class="panel-title">По дням недели</h2>
              <AppChart :option="weekdayOption" height="240px" label="Число нарядов по дням недели" />
            </section>
            <section class="card panel">
              <h2 class="panel-title">Нагрузка по нарядам</h2>
              <AppChart :option="dutyTypeOption" :height="barsHeight(items('duty_type').length)" label="Нагрузка по нарядам" />
            </section>
            <section class="card panel">
              <h2 class="panel-title">На человека по категориям</h2>
              <AppChart
                :option="categoryOption"
                :height="barsHeight(items('category').length)"
                label="Нагрузка на человека по категориям"
              />
              <div v-if="sourceShare.length" class="share">
                <span class="share-title">Как назначены</span>
                <div class="share-bar">
                  <span
                    v-for="(s, i) in sourceShare"
                    :key="s.label"
                    :style="{ width: `${s.pct}%`, background: theme.series.value[i] }"
                    :title="`${s.label}: ${s.duties}`"
                  />
                </div>
                <span class="share-legend">
                  <span v-for="(s, i) in sourceShare" :key="s.label">
                    <i :style="{ background: theme.series.value[i] }" /> {{ s.label }} — {{ s.pct }}%
                  </span>
                </span>
              </div>
            </section>
          </div>
        </TabPanel>

        <TabPanel value="pivot">
          <div class="card panel">
            <div class="pivot-controls">
              <label>
                <span>Показатель</span>
                <Select v-model="pivotMetric" :options="METRICS" option-label="label" option-value="value" />
              </label>
              <label>
                <span>Группировать по</span>
                <Select v-model="pivotDim" :options="DIMS" option-label="label" option-value="value" />
              </label>
              <label>
                <span>Разбить по</span>
                <Select
                  v-model="pivotSplit"
                  :options="splitOptions"
                  option-label="label"
                  option-value="value"
                  placeholder="Без разбивки"
                />
              </label>
              <label>
                <span>Вид</span>
                <SelectButton
                  v-model="pivotView"
                  :options="VIEWS"
                  option-label="label"
                  option-value="value"
                  :allow-empty="false"
                  size="small"
                >
                  <template #option="{ option }">
                    <i v-tooltip.top="option.label" :class="option.icon" :aria-label="option.label" />
                  </template>
                </SelectButton>
              </label>
            </div>
            <p v-if="pivotNote" class="pivot-note"><i class="pi pi-info-circle" /> {{ pivotNote }}</p>
            <AppChart
              v-if="pivotRows.length"
              :option="pivotOption"
              :height="pivotHeight"
              :label="`${metricInfo.label} по выбранному разрезу`"
            />
            <p v-else class="muted small">Нет данных для выбранного разреза.</p>
          </div>
          <DataTable
            v-if="pivotRows.length"
            :value="pivotRows"
            size="small"
            class="card table-card"
            scrollable
            scroll-height="24rem"
          >
            <Column field="label" :header="DIMS.find((d) => d.value === pivotDim)?.label" sortable />
            <Column
              v-if="pivotSplit"
              field="split_label"
              :header="DIMS.find((d) => d.value === pivotSplit)?.label"
              sortable
            />
            <Column field="duties" header="Нарядов" sortable body-class="num" header-class="num" />
            <Column field="duty_days" header="Нарядо-суток" sortable body-class="num" header-class="num" />
            <Column field="load" header="Нагрузка" sortable body-class="num" header-class="num" />
            <Column field="people" header="Людей" sortable body-class="num" header-class="num" />
            <Column field="load_per_person" header="На человека" sortable body-class="num" header-class="num" />
            <Column field="holidays" header="В выходные" sortable body-class="num" header-class="num" />
          </DataTable>
        </TabPanel>

        <TabPanel value="fairness">
          <div class="grid">
            <section class="card panel">
              <h2 class="panel-title">Кривая Лоренца</h2>
              <p class="muted small explain">
                Чем ближе линия к диагонали, тем ровнее. Площадь между ними — коэффициент Джини
                ({{ fmt(data.fairness.load?.gini, 3) }}).
              </p>
              <AppChart :option="lorenzOption" height="300px" label="Кривая Лоренца распределения нагрузки" />
            </section>
            <section class="card panel">
              <h2 class="panel-title">Сколько нарядов у людей</h2>
              <p class="muted small explain">Высокий столбец слева и длинный хвост справа — признак перекоса.</p>
              <AppChart :option="histogramOption" height="300px" label="Распределение людей по числу нарядов" />
            </section>
            <section class="card panel wide">
              <div class="panel-head">
                <h2 class="panel-title">Разброс нагрузки на человека</h2>
                <Select
                  v-model="distDim"
                  :options="DIST_DIMS"
                  option-label="label"
                  option-value="value"
                  size="small"
                  aria-label="Группировать по"
                />
              </div>
              <p class="muted small explain">
                Ящик — половина людей группы, черта — медиана, усы — минимум и максимум. Узкий ящик —
                нагрузка ровная.
              </p>
              <AppChart
                v-if="distribution.length"
                :option="boxOption"
                :height="barsHeight(distribution.length)"
                label="Разброс нагрузки на человека по группам"
              />
            </section>
            <section class="card panel">
              <h2 class="panel-title">Больше всех</h2>
              <table class="list">
                <tr v-for="p in data.top" :key="p.person_id">
                  <td>{{ p.person_name }}</td>
                  <td class="num">{{ p.duties }} нар.</td>
                  <td class="num">
                    <span class="meter"><span :style="{ width: `${Math.min(100, (p.load / topLoad) * 100)}%` }" /></span>
                    {{ fmt(p.load) }}
                  </td>
                </tr>
              </table>
            </section>
            <section class="card panel">
              <h2 class="panel-title">Меньше всех</h2>
              <table class="list">
                <tr v-for="p in data.bottom" :key="p.person_id">
                  <td>{{ p.person_name }}</td>
                  <td class="num">{{ p.duties }} нар.</td>
                  <td class="num">
                    <span class="meter low">
                      <span :style="{ width: `${Math.min(100, (p.load / topLoad) * 100)}%` }" />
                    </span>
                    {{ fmt(p.load) }}
                  </td>
                </tr>
              </table>
            </section>
          </div>
        </TabPanel>

        <TabPanel value="calendar">
          <section class="card panel">
            <div class="panel-head">
              <h2 class="panel-title">По дням</h2>
              <SelectButton
                v-model="calMetric"
                :options="CAL_METRICS"
                option-label="label"
                option-value="value"
                :allow-empty="false"
                size="small"
              />
            </div>
            <AppChart v-if="calendar.length" :option="calendarOption" height="260px" label="Нагрузка по дням периода" />
            <p v-else class="muted small">Нет данных.</p>
          </section>
          <section class="card panel spaced">
            <h2 class="panel-title">День недели × месяц</h2>
            <AppChart
              v-if="items('weekday', 'month').length"
              :option="weekMonthOption"
              height="320px"
              label="Нарядов по дням недели и месяцам"
            />
          </section>
        </TabPanel>

        <TabPanel value="people">
          <div class="people-head">
            <span class="muted">Среднее: <b>{{ fmt(mean) }}</b> на человека</span>
            <SelectButton
              v-model="ascending"
              :options="[
                { value: false, label: 'Больше всех' },
                { value: true, label: 'Меньше всех' },
              ]"
              option-label="label"
              option-value="value"
              :allow-empty="false"
              size="small"
            />
          </div>
          <DataTable
            :value="people"
            lazy
            paginator
            :first="peopleFirst"
            :rows="peopleRows"
            :rows-per-page-options="[25, 50, 100]"
            :total-records="peopleTotal"
            :loading="peopleLoading"
            size="small"
            class="card table-card"
            current-page-report-template="{first}–{last} из {totalRecords}"
            paginator-template="PrevPageLink PageLinks NextPageLink RowsPerPageDropdown CurrentPageReport"
            @page="onPeoplePage"
          >
            <Column field="person_name" header="Человек" />
            <Column field="duties" header="Нарядов" body-class="num" header-class="num" />
            <Column field="duty_days" header="Нарядо-суток" body-class="num" header-class="num" />
            <Column field="holidays" header="В выходные" body-class="num" header-class="num" />
            <Column header="Нагрузка" body-class="num" header-class="num">
              <template #body="{ data: p }">
                <span class="load-cell">
                  <span class="meter" :class="{ above: p.load > mean * 1.25, low: p.load < mean * 0.75 }">
                    <span :style="{ width: `${Math.min(100, (p.load / maxLoad) * 100)}%` }" />
                  </span>
                  {{ fmt(p.load) }}
                </span>
              </template>
            </Column>
            <Column header="Последний наряд">
              <template #body="{ data: p }">{{ formatDate(p.last_date) }}</template>
            </Column>
          </DataTable>
        </TabPanel>
      </TabPanels>
    </Tabs>
    <p v-else-if="loading" class="muted">Загрузка…</p>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  max-width: 100rem;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 650;
}
.muted {
  color: var(--app-ink-3);
  margin: 0.2rem 0 0;
}
.small {
  font-size: 0.84rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
.filters {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
  padding: 0.6rem 0.75rem;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}
.unit {
  width: 22rem;
  max-width: 100%;
}
.range {
  width: 15rem;
}
.tabs :deep(.p-tablist-tab-list) {
  background: transparent;
}
.tabs :deep(.p-tab) .pi {
  margin-right: 0.35rem;
  font-size: 0.85rem;
}
.tabs :deep(.p-tabpanels) {
  background: transparent;
  padding: 0.9rem 0 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(30rem, 1fr));
  gap: var(--app-gap);
  align-items: start;
}
.panel {
  padding: 0.85rem 1rem 0.9rem;
  min-width: 0;
}
.panel > .panel-title {
  margin-bottom: 0.5rem;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.3rem;
}
.wide {
  grid-column: 1 / -1;
}
.spaced {
  margin-top: var(--app-gap);
}
.explain {
  margin: -0.2rem 0 0.4rem;
}
.pivot-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.9rem;
  align-items: flex-end;
  padding-bottom: 0.75rem;
  margin-bottom: 0.5rem;
  border-bottom: 1px solid var(--app-border);
}
.pivot-note {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
  color: var(--app-ink-2);
}
.pivot-controls label {
  display: grid;
  gap: 0.3rem;
}
.pivot-controls label > span {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-ink-3);
}
.pivot-controls :deep(.p-select) {
  min-width: 13rem;
}
.table-card {
  margin-top: var(--app-gap);
  padding: 0.25rem 0.5rem;
}
.table-card :deep(.num),
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.list {
  width: 100%;
  font-size: 0.88rem;
  border-collapse: collapse;
}
.list td {
  padding: 0.3rem 0.25rem;
  border-top: 1px solid var(--app-border);
}
.list tr:first-child td {
  border-top: none;
}
.list td:not(:first-child) {
  white-space: nowrap;
}
.meter {
  display: inline-block;
  width: 4rem;
  height: 5px;
  border-radius: 3px;
  background: var(--app-hover);
  vertical-align: middle;
  margin-right: 0.4rem;
  overflow: hidden;
}
.meter span {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--app-accent);
}
.meter.above span {
  background: var(--state-serious);
}
.meter.low span {
  background: var(--app-ink-3);
}
.load-cell {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
}
.people-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.share {
  display: grid;
  gap: 0.4rem;
  margin-top: 0.6rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--app-border);
}
.share-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-ink-3);
}
.share-bar {
  display: flex;
  height: 10px;
  border-radius: 5px;
  overflow: hidden;
  gap: 2px;
}
.share-legend {
  display: flex;
  gap: 1rem;
  font-size: 0.84rem;
  color: var(--app-ink-2);
}
.share-legend i {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 0.3rem;
  vertical-align: -1px;
}
</style>
