<script setup lang="ts">
// Дашборд нагрузки (фаза 6c): справедливость и нагрузка по поддереву за период, сравнение
// дочерних подразделений, тренд, самые загруженные и недогруженные, незакрытые места
// текущего графика. Данные — read-model analytics; отчёт по нагрузке печатает documents.
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import VChart from 'vue-echarts'
import { useRoute } from 'vue-router'

import { analytics, ApiError, documents, saveFile, scheduling, unwrap, type Overview } from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { fromIso, toIso } from '@/utils/dates'

use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const units = useUnitsStore()
const toast = useToast()
const route = useRoute()

type Preset = 'month' | 'prev' | 'quarter' | 'half'
const PRESETS: { value: Preset; label: string }[] = [
  { value: 'month', label: 'Этот месяц' },
  { value: 'prev', label: 'Прошлый месяц' },
  { value: 'quarter', label: '3 месяца' },
  { value: 'half', label: '6 месяцев' },
]

const unitId = ref<string | null>(null)
const preset = ref<Preset | null>('month')
const range = ref<Date[]>(presetRange('month'))
const drafts = ref(false)
const data = ref<Overview | null>(null)
const loading = ref(false)
const unfilled = ref<{ count: number; month: string; scheduleId: string } | null>(null)

function presetRange(p: Preset): Date[] {
  const now = new Date()
  const first = (y: number, m: number) => new Date(y, m, 1)
  const last = (y: number, m: number) => new Date(y, m + 1, 0)
  const y = now.getFullYear()
  const m = now.getMonth()
  switch (p) {
    case 'prev':
      return [first(y, m - 1), last(y, m - 1)]
    case 'quarter':
      return [first(y, m - 2), last(y, m)]
    case 'half':
      return [first(y, m - 5), last(y, m)]
    default:
      return [first(y, m), last(y, m)]
  }
}

const period = computed(() => {
  const [from, to] = range.value
  return from && to ? { date_from: toIso(from), date_to: toIso(to) } : null
})

async function load() {
  if (!unitId.value || !period.value) return
  loading.value = true
  try {
    data.value = await unwrap(
      analytics.GET('/metrics/overview', {
        params: { query: { unit_id: unitId.value, ...period.value, drafts: drafts.value } },
      }),
    )
  } catch (e) {
    data.value = null
    const detail = e instanceof ApiError ? e.message : 'Аналитика недоступна'
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
  } finally {
    loading.value = false
  }
  void loadUnfilled()
}

/** Незакрытые места в графике подразделения на текущий месяц (закрывает само подразделение). */
async function loadUnfilled() {
  unfilled.value = null
  if (!unitId.value) return
  const now = new Date()
  const month = toIso(new Date(now.getFullYear(), now.getMonth(), 1))
  try {
    const list = await unwrap(
      scheduling.GET('/schedules', { params: { query: { month, unit_id: unitId.value } } }),
    )
    const schedule = list.find((s) => s.unit_id === unitId.value)
    if (!schedule) return
    const table = await unwrap(
      scheduling.GET('/schedules/{schedule_id}/table', { params: { path: { schedule_id: schedule.id } } }),
    )
    let count = 0
    for (const row of table.rows) {
      if (!row.is_active) continue
      for (const cell of row.cells) {
        if (cell && cell.executor_unit_id === schedule.unit_id) count += Math.max(0, row.headcount - cell.filled)
      }
    }
    unfilled.value = { count, month, scheduleId: schedule.id }
  } catch {
    unfilled.value = null
  }
}

async function report(format: 'pdf' | 'xlsx') {
  if (!unitId.value || !period.value) return
  try {
    await saveFile(
      documents.GET('/print/load-report', {
        params: { query: { unit_id: unitId.value, ...period.value, drafts: drafts.value, format } },
        parseAs: 'blob',
      }),
      `load.${format}`,
    )
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : 'Не удалось подготовить отчёт'
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
  }
}

watch(preset, (p) => {
  if (p) range.value = presetRange(p)
})
watch([unitId, range, drafts], () => {
  if (range.value.every(Boolean)) void load()
})
onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  // Ссылка на дашборд может задать подразделение, период и черновики: ?unit=&from=&to=&drafts=1
  const q = route.query
  if (typeof q.from === 'string' && typeof q.to === 'string') {
    preset.value = null
    range.value = [fromIso(q.from), fromIso(q.to)]
  }
  drafts.value = q.drafts === '1'
  unitId.value = (typeof q.unit === 'string' && q.unit) || (units.me?.unit.id ?? null)
})

const fmt = (x: number | undefined, digits = 2) =>
  x === undefined ? '—' : x.toLocaleString('ru-RU', { maximumFractionDigits: digits })

const histogramOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 16, top: 16, bottom: 40 },
  xAxis: {
    type: 'category',
    name: 'нарядов',
    nameLocation: 'middle',
    nameGap: 26,
    data: (data.value?.histogram ?? []).map((h) => h.duties),
  },
  yAxis: { type: 'value', minInterval: 1, name: 'людей' },
  series: [{ type: 'bar', data: (data.value?.histogram ?? []).map((h) => h.people), itemStyle: { color: '#4f81bd' } }],
}))

const unitsOption = computed(() => {
  const rows = (data.value?.units ?? []).filter((u) => u.people > 0)
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 8, right: 24, top: 16, bottom: 24, containLabel: true },
    xAxis: { type: 'value' },
    yAxis: {
      type: 'category',
      data: rows.map((u) => (u.own ? `${u.unit_name} (само)` : u.unit_name)),
      inverse: true,
      axisLabel: { width: 200, overflow: 'truncate' },
    },
    series: [{ type: 'bar', data: rows.map((u) => u.load_per_person), itemStyle: { color: '#9bbb59' } }],
  }
})

const trendOption = computed(() => {
  const t = data.value?.trend ?? []
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Нагрузка', 'Джини'] },
    grid: { left: 48, right: 48, top: 32, bottom: 24 },
    xAxis: { type: 'category', data: t.map((x) => x.month) },
    yAxis: [
      { type: 'value', name: 'нагрузка' },
      { type: 'value', name: 'Джини', min: 0, max: 1 },
    ],
    series: [
      { name: 'Нагрузка', type: 'bar', data: t.map((x) => x.load), itemStyle: { color: '#4f81bd' } },
      { name: 'Джини', type: 'line', yAxisIndex: 1, data: t.map((x) => x.gini), itemStyle: { color: '#c0504d' } },
    ],
  }
})
</script>

<template>
  <section class="page">
    <header>
      <h1>Нагрузка</h1>
      <p class="muted">
        Нагрузка нарядами и справедливость распределения по подразделению и всем нижестоящим за период. Нагрузка —
        нарядо-сутки × вес наряда; считаются люди, у которых был хотя бы один наряд.
      </p>
    </header>

    <div class="filters">
      <div class="unit">
        <UnitTreeSelect v-model="unitId" placeholder="Подразделение" input-id="dash-unit" />
      </div>
      <SelectButton v-model="preset" :options="PRESETS" option-label="label" option-value="value" size="small" />
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
      <span class="spacer" />
      <Button label="Отчёт PDF" icon="pi pi-file-pdf" severity="secondary" text @click="report('pdf')" />
      <Button label="Отчёт XLSX" icon="pi pi-file-excel" severity="secondary" text @click="report('xlsx')" />
    </div>

    <Message v-if="unfilled && unfilled.count > 0" severity="warn" :closable="false">
      В графике подразделения на текущий месяц не закрыто мест: {{ unfilled.count }}.
      <RouterLink :to="`/schedules?unit=${unitId}&month=${unfilled.month}`">Открыть график</RouterLink>
    </Message>

    <template v-if="data">
      <div class="cards">
        <div class="card kpi"><span>{{ data.totals.people }}</span><small>людей в нарядах</small></div>
        <div class="card kpi"><span>{{ data.totals.duties }}</span><small>нарядов</small></div>
        <div class="card kpi"><span>{{ data.totals.duty_days }}</span><small>нарядо-суток</small></div>
        <div class="card kpi"><span>{{ data.totals.holidays }}</span><small>в выходные и праздники</small></div>
        <div class="card kpi">
          <span>{{ fmt(data.fairness.load?.gini, 3) }}</span><small>Джини нагрузки (0 — поровну)</small>
        </div>
        <div class="card kpi">
          <span>{{ fmt(data.fairness.load?.jain, 3) }}</span><small>Джайн (1 — поровну)</small>
        </div>
        <div class="card kpi">
          <span>{{ fmt(data.fairness.count?.range, 0) }}</span><small>размах, нарядов</small>
        </div>
        <div class="card kpi">
          <span>{{ fmt(data.fairness.holiday?.range, 0) }}</span><small>размах выходных нарядов</small>
        </div>
      </div>

      <div v-if="data.totals.duties === 0" class="muted">За период нарядов нет.</div>
      <div v-else class="charts">
        <div class="card chart">
          <strong>Сколько нарядов у людей</strong>
          <VChart :option="histogramOption" autoresize class="echart" />
        </div>
        <div v-if="data.units.length > 1" class="card chart">
          <strong>Нагрузка на человека по подразделениям</strong>
          <VChart :option="unitsOption" autoresize class="echart" />
        </div>
        <div v-if="data.trend.length > 1" class="card chart wide">
          <strong>По месяцам</strong>
          <VChart :option="trendOption" autoresize class="echart" />
        </div>
        <div class="card">
          <strong>Больше всех</strong>
          <table class="list">
            <tr v-for="p in data.top" :key="p.person_id">
              <td>{{ p.person_name }}</td><td>{{ p.duties }} нар.</td><td>{{ fmt(p.load) }}</td>
            </tr>
          </table>
        </div>
        <div class="card">
          <strong>Меньше всех</strong>
          <table class="list">
            <tr v-for="p in data.bottom" :key="p.person_id">
              <td>{{ p.person_name }}</td><td>{{ p.duties }} нар.</td><td>{{ fmt(p.load) }}</td>
            </tr>
          </table>
        </div>
      </div>
    </template>
    <p v-else-if="loading" class="muted">Загрузка…</p>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.filters,
.check {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}
.unit {
  width: 22rem;
  max-width: 100%;
}
.range {
  width: 16rem;
}
.spacer {
  flex: 1;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.6rem;
}
.card {
  border: 1px solid var(--p-content-border-color);
  border-radius: 6px;
  padding: 0.75rem;
  background: var(--p-content-background);
}
.kpi {
  display: grid;
  gap: 0.2rem;
}
.kpi span {
  font-size: 1.5rem;
  font-weight: 700;
}
.kpi small {
  color: var(--p-text-muted-color);
}
.charts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(26rem, 1fr));
  gap: 0.75rem;
}
.chart {
  display: grid;
  gap: 0.4rem;
}
.wide {
  grid-column: 1 / -1;
}
.echart {
  height: 260px;
}
.list {
  width: 100%;
  font-size: 0.9rem;
  border-collapse: collapse;
  margin-top: 0.4rem;
}
.list td {
  padding: 0.15rem 0.25rem;
  border-top: 1px solid var(--p-content-border-color);
}
.list td:not(:first-child) {
  text-align: right;
  white-space: nowrap;
}
</style>
