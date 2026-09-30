<script setup lang="ts">
// Оперативная сводка (фаза 8): что требует действий, состояние графиков месяца, кто в наряде
// сегодня и как нагрузка распределяется по дням и подразделениям. Всё — в зоне ответственности
// оператора; черновики учитываются: сводка про текущую работу, а не про утверждённый факт.
import Button from 'primevue/button'
import SelectButton from 'primevue/selectbutton'
import Skeleton from 'primevue/skeleton'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { analytics, personnel, scheduling, unwrap, type Schedule } from '@/api/client'
import AppChart from '@/components/AppChart.vue'
import StatStrip, { type Stat } from '@/components/StatStrip.vue'
import { useUnitsStore } from '@/stores/units'
import { useTheme } from '@/theme'
import { toIso } from '@/utils/dates'
import { monthIso, monthTitle, shiftMonth } from '@/utils/schedule'

const units = useUnitsStore()
const router = useRouter()
const theme = useTheme()

const now = new Date()
const todayIso = toIso(now)
const thisMonth = monthIso(now)
const nextMonth = shiftMonth(thisMonth, 1)
const month = ref(thisMonth)
const capital = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)
const monthOptions = [
  { label: capital(monthTitle(thisMonth)), value: thisMonth },
  { label: capital(monthTitle(nextMonth)), value: nextMonth },
]

interface RosterItem {
  person_name: string
  unit_name: string
  duty_type_name?: string | null
  role_name?: string | null
  start_at: string
  end_at: string
  schedule_status: string
}
interface DayLoad {
  date: string
  duties: number
  people: number
}
interface UnitShare {
  label: string
  duties: number
  people: number
  load_per_person: number
}

const schedules = ref<Schedule[]>([])
const otherSchedules = ref<Schedule[]>([])
const mismatches = ref<number | null>(null)
const exemptToday = ref<number | null>(null)
const roster = ref<RosterItem[] | null>(null)
const days = ref<DayLoad[]>([])
const byUnit = ref<UnitShare[]>([])
const loading = ref(true)

const unitId = computed(() => units.me?.unit.id ?? null)
const monthRange = computed(() => {
  const [y = 1970, m = 1] = month.value.split('-').map(Number)
  return { date_from: month.value, date_to: toIso(new Date(y, m, 0)) }
})

// Каждый блок сводки независим: недоступность одного сервиса не гасит остальные
const safe = <T,>(p: Promise<T>): Promise<T | null> => p.catch(() => null)

async function load() {
  if (!unitId.value) return
  loading.value = true
  const unit = unitId.value
  const other = month.value === thisMonth ? nextMonth : thisMonth
  const range = monthRange.value
  const [cur, next, mm, ex, rs, cal, bu] = await Promise.all([
    safe(unwrap(scheduling.GET('/schedules', { params: { query: { month: month.value } } }))),
    safe(unwrap(scheduling.GET('/schedules', { params: { query: { month: other } } }))),
    safe(unwrap(personnel.GET('/reports/clearance-mismatches', { params: { query: { limit: 1 } } }))),
    safe(unwrap(personnel.GET('/people', { params: { query: { exempt_today: true, limit: 1 } } }))),
    safe(unwrap(analytics.GET('/metrics/roster', { params: { query: { unit_id: unit, day: todayIso } } }))),
    safe(unwrap(analytics.GET('/metrics/calendar', { params: { query: { unit_id: unit, ...range, drafts: true } } }))),
    safe(
      unwrap(
        analytics.GET('/metrics/breakdown', {
          params: { query: { unit_id: unit, ...range, drafts: true, dimension: 'unit' } },
        }),
      ),
    ),
  ])
  schedules.value = cur ?? []
  otherSchedules.value = next ?? []
  mismatches.value = mm?.total ?? null
  exemptToday.value = ex?.total ?? null
  roster.value = rs
  days.value = cal ?? []
  byUnit.value = bu?.items ?? []
  loading.value = false
}
watch(month, load)
onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  await load()
})

// --- показатели ----------------------------------------------------------------------------------
const pending = computed(() =>
  [...schedules.value, ...otherSchedules.value].filter((s) => s.can_edit && s.pending_incoming > 0),
)
const pendingTotal = computed(() => pending.value.reduce((n, s) => n + s.pending_incoming, 0))
const toFill = computed(() => schedules.value.reduce((n, s) => n + s.to_fill, 0))
const unfilled = computed(() => schedules.value.reduce((n, s) => n + s.unfilled, 0))
const drafts = computed(() => schedules.value.filter((s) => s.status === 'draft'))
const fillPct = (s: { to_fill: number; unfilled: number }) =>
  s.to_fill ? Math.round(((s.to_fill - s.unfilled) / s.to_fill) * 100) : 100

function openSchedule(s: Schedule) {
  void router.push({ path: '/schedules', query: { unit: s.unit_id, month: s.month } })
}
function openSchedules() {
  void router.push({ path: '/schedules', query: { month: month.value } })
}

const stats = computed<Stat[]>(() => [
  {
    key: 'fill',
    label: 'Укомплектовано',
    value: toFill.value ? `${fillPct({ to_fill: toFill.value, unfilled: unfilled.value })}%` : '—',
    state: unfilled.value ? 'serious' : 'good',
    stateText: unfilled.value ? `${unfilled.value} мест без людей` : 'все места закрыты',
    action: () => {
      const worst = [...schedules.value].sort((a, b) => b.unfilled - a.unfilled)[0]
      if (worst) openSchedule(worst)
      else openSchedules()
    },
  },
  {
    key: 'pending',
    label: 'Ждут принятия',
    value: String(pendingTotal.value),
    state: pendingTotal.value ? 'warn' : 'good',
    stateText: pendingTotal.value ? `входящие в ${pending.value.length} граф.` : 'входящих нет',
    action: () => (pending.value[0] ? openSchedule(pending.value[0]) : openSchedules()),
  },
  {
    key: 'drafts',
    label: 'Не опубликовано',
    value: String(drafts.value.length),
    sub: `из ${schedules.value.length} графиков месяца`,
    action: () => (drafts.value[0] ? openSchedule(drafts.value[0]) : openSchedules()),
  },
  {
    key: 'mismatch',
    label: 'Несоответствия допусков',
    value: mismatches.value === null ? '—' : String(mismatches.value),
    state: mismatches.value ? 'warn' : 'good',
    stateText: mismatches.value ? 'требуют проверки' : 'нет',
    action: () => router.push('/reports/clearance-mismatches'),
  },
  {
    key: 'exempt',
    label: 'Освобождены сегодня',
    value: exemptToday.value === null ? '—' : String(exemptToday.value),
    sub: 'болезнь, отпуск, командировка',
    action: () => router.push({ path: '/people', query: { exempt: '1' } }),
  },
])

// --- графики месяца --------------------------------------------------------------------------------
const STATUS: Record<string, { label: string; state: string }> = {
  draft: { label: 'Черновик', state: '' },
  published: { label: 'Опубликован', state: 'good' },
  archived: { label: 'В архиве', state: '' },
}
const rows = computed(() =>
  [...schedules.value].sort(
    (a, b) =>
      b.pending_incoming - a.pending_incoming ||
      b.unfilled - a.unfilled ||
      (a.unit_name ?? '').localeCompare(b.unit_name ?? '', 'ru'),
  ),
)

// --- наряд сегодня -----------------------------------------------------------------------------------
const time = (iso: string) => new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
const rosterGroups = computed(() => {
  const groups = new Map<string, RosterItem[]>()
  for (const r of roster.value ?? []) {
    const key = r.duty_type_name ?? 'Наряд'
    groups.set(key, [...(groups.get(key) ?? []), r])
  }
  return [...groups.entries()].map(([name, items]) => ({ name, items, start: items[0]?.start_at ?? '' }))
})

// --- графики ---------------------------------------------------------------------------------------
const dayOption = computed(() => {
  const [y = 1970, m = 1] = month.value.split('-').map(Number)
  const count = new Date(y, m, 0).getDate()
  const byDate = new Map(days.value.map((d) => [d.date, d]))
  const labels = Array.from({ length: count }, (_, i) => String(i + 1))
  const values = labels.map((_, i) => byDate.get(toIso(new Date(y, m - 1, i + 1)))?.duties ?? 0)
  const weekend = labels
    .map((_, i) => new Date(y, m - 1, i + 1).getDay())
    .map((d, i) => (d === 0 || d === 6 ? i : -1))
    .filter((i) => i >= 0)
  const todayIndex = month.value === thisMonth ? now.getDate() - 1 : -1
  return {
    grid: { left: 36, right: 12, top: 20, bottom: 28 },
    tooltip: {
      trigger: 'axis',
      formatter: (p: { name: string; value: number }[]) => `${p[0]?.name}-е число: ${p[0]?.value} нар.`,
    },
    xAxis: { type: 'category', data: labels, axisLabel: { interval: 1 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      {
        type: 'bar',
        name: 'Нарядов',
        data: values,
        barMaxWidth: 14,
        itemStyle: { borderRadius: [3, 3, 0, 0] },
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(137,135,129,0.09)' },
          data: weekend.map((i) => [{ xAxis: labels[i] }, { xAxis: labels[i] }]),
        },
        markLine:
          todayIndex >= 0
            ? {
                silent: true,
                symbol: 'none',
                label: { formatter: 'сегодня', position: 'end', fontSize: 11, color: theme.ink.value },
                lineStyle: { type: 'dashed', width: 1 },
                data: [{ xAxis: labels[todayIndex] }],
              }
            : undefined,
      },
    ],
  }
})

const unitOption = computed(() => {
  const items = [...byUnit.value].sort((a, b) => b.duties - a.duties).slice(0, 10)
  return {
    grid: { left: 8, right: 40, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (p: { dataIndex: number }[]) => {
        const u = items[p[0]?.dataIndex ?? 0]
        return u
          ? `${u.label}<br/>Нарядов: ${u.duties}<br/>Людей: ${u.people}<br/>Нагрузка на человека: ${u.load_per_person}`
          : ''
      },
    },
    xAxis: { type: 'value', minInterval: 1, splitNumber: 3 },
    yAxis: {
      type: 'category',
      inverse: true,
      data: items.map((u) => u.label),
      axisLabel: { width: 150, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        data: items.map((u) => u.duties),
        barMaxWidth: 16,
        itemStyle: { borderRadius: [0, 3, 3, 0] },
        label: { show: true, position: 'right', fontSize: 11, color: theme.ink.value, textBorderWidth: 0 },
      },
    ],
  }
})
</script>

<template>
  <section class="home">
    <header class="head">
      <div>
        <h1>Оперативная сводка</h1>
        <p class="sub">{{ units.me?.unit.name }} и нижестоящие подразделения</p>
      </div>
      <SelectButton
        v-model="month"
        :options="monthOptions"
        option-label="label"
        option-value="value"
        :allow-empty="false"
        size="small"
        aria-label="Месяц"
      />
    </header>

    <StatStrip :items="stats" :loading="loading" />

    <div class="grid">
      <section class="card panel">
        <header class="panel-head">
          <h2 class="panel-title">Графики · {{ monthTitle(month) }}</h2>
          <Button label="Все графики" text size="small" icon="pi pi-arrow-right" icon-pos="right" @click="openSchedules" />
        </header>
        <div v-if="loading" class="rows"><Skeleton v-for="i in 4" :key="i" height="2.25rem" /></div>
        <div v-else-if="!rows.length" class="empty-state">
          <strong>Графиков на месяц нет</strong>
          <span>Создайте график или дождитесь, когда вам передадут наряд.</span>
        </div>
        <table v-else class="table">
          <thead>
            <tr>
              <th>Подразделение</th>
              <th>Статус</th>
              <th class="fill-col">Укомплектовано</th>
              <th class="num-col">Входящие</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in rows" :key="s.id" tabindex="0" @click="openSchedule(s)" @keydown.enter="openSchedule(s)">
              <td class="unit">{{ s.unit_name }}</td>
              <td>
                <span class="status">
                  <span class="dot" :class="STATUS[s.status]?.state ? `dot--${STATUS[s.status]?.state}` : ''" />
                  {{ STATUS[s.status]?.label }}
                </span>
              </td>
              <td class="fill-col">
                <span v-if="s.to_fill" class="bar-cell">
                  <span class="bar"><span :style="{ width: `${fillPct(s)}%` }" :class="{ low: fillPct(s) < 100 }" /></span>
                  <span class="num">{{ s.to_fill - s.unfilled }}/{{ s.to_fill }}</span>
                </span>
                <span v-else class="muted">нет своих мест</span>
              </td>
              <td class="num-col num">
                <span v-if="s.pending_incoming" class="pending">{{ s.pending_incoming }}</span>
                <span v-else class="muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="card panel">
        <header class="panel-head">
          <h2 class="panel-title">В наряде сегодня</h2>
          <span class="muted small">{{ now.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) }}</span>
        </header>
        <div v-if="loading" class="rows"><Skeleton v-for="i in 5" :key="i" height="1.8rem" /></div>
        <p v-else-if="roster === null" class="muted small">Сведения о нарядах недоступны.</p>
        <p v-else-if="!roster.length" class="muted small">Сегодня нарядов нет или люди ещё не назначены.</p>
        <div v-else class="roster-list">
          <div v-for="g in rosterGroups" :key="g.name" class="roster-group">
            <div class="roster-head">
              <span>{{ g.name }}</span>
              <span class="muted num">{{ time(g.start) }}</span>
            </div>
            <div v-for="(r, i) in g.items" :key="i" class="roster-row">
              <span class="role">{{ r.role_name }}</span>
              <span class="person">
                {{ r.person_name }}
                <small>{{ r.unit_name }}</small>
              </span>
              <span v-if="r.schedule_status === 'draft'" v-tooltip.left="'График ещё не опубликован'" class="draft">
                черн.
              </span>
            </div>
          </div>
        </div>
      </section>

      <section class="card panel">
        <header class="panel-head">
          <h2 class="panel-title">Нарядов по дням</h2>
          <RouterLink to="/dashboard" class="link small">Вся аналитика</RouterLink>
        </header>
        <AppChart v-if="days.length" :option="dayOption" height="220px" label="Число нарядов по дням месяца" />
        <p v-else-if="!loading" class="muted small">В этом месяце людей в наряды ещё не назначали.</p>
      </section>

      <section class="card panel">
        <header class="panel-head">
          <h2 class="panel-title">По подразделениям</h2>
          <span class="muted small">нарядов за месяц</span>
        </header>
        <AppChart
          v-if="byUnit.length"
          :option="unitOption"
          :height="`${Math.max(160, Math.min(byUnit.length, 10) * 30 + 20)}px`"
          label="Нарядов по подразделениям"
        />
        <p v-else-if="!loading" class="muted small">Нет данных за месяц.</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.home {
  display: grid;
  gap: 1rem;
  max-width: 96rem;
}
.head {
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
  letter-spacing: -0.01em;
}
.sub {
  margin: 0.2rem 0 0;
  color: var(--app-ink-3);
}
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(20rem, 1fr);
  gap: var(--app-gap);
  align-items: start;
}
@media (max-width: 1150px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.panel {
  padding: 0.85rem 1rem 1rem;
  min-width: 0;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.6rem;
  min-height: 1.9rem;
}
.muted {
  color: var(--app-ink-3);
}
.small {
  font-size: 0.82rem;
}
.link {
  color: var(--app-accent);
  text-decoration: none;
}
.rows {
  display: grid;
  gap: 0.4rem;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.table th {
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-ink-3);
  padding: 0 0.5rem 0.45rem;
  border-bottom: 1px solid var(--app-border);
}
.table td {
  padding: 0.55rem 0.5rem;
  border-bottom: 1px solid var(--app-border);
}
.table tbody tr {
  cursor: pointer;
}
.table tbody tr:hover,
.table tbody tr:focus-visible {
  background: var(--app-subtle);
  outline: none;
}
.table tbody tr:last-child td {
  border-bottom: none;
}
.unit {
  font-weight: 600;
}
.status {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--app-ink-2);
}
.fill-col {
  width: 34%;
}
.num-col {
  width: 6rem;
  text-align: right !important;
}
.bar-cell {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 0.6rem;
}
.bar {
  height: 6px;
  border-radius: 3px;
  background: var(--app-hover);
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: var(--app-accent);
}
.bar span.low {
  background: var(--state-serious);
}
.bar-cell .num {
  min-width: 3.5rem;
  text-align: right;
  color: var(--app-ink-2);
}
.pending {
  display: inline-block;
  min-width: 1.6rem;
  padding: 0 0.35rem;
  border-radius: 4px;
  background: var(--chip-warn-bg);
  color: var(--chip-warn-fg);
  font-weight: 600;
  text-align: center;
}
.roster-list {
  display: grid;
  gap: 0.8rem;
  max-height: 22rem;
  overflow: auto;
}
.roster-head {
  display: flex;
  justify-content: space-between;
  font-weight: 600;
  font-size: 0.88rem;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid var(--app-border);
}
.roster-row {
  display: grid;
  grid-template-columns: minmax(7rem, 0.9fr) 1.2fr auto;
  gap: 0.5rem;
  align-items: baseline;
  padding: 0.35rem 0;
  font-size: 0.88rem;
}
.role {
  color: var(--app-ink-2);
}
.person {
  display: grid;
}
.person small {
  color: var(--app-ink-3);
  font-size: 0.76rem;
}
.draft {
  font-size: 0.72rem;
  color: var(--app-ink-3);
  border: 1px solid var(--app-border);
  border-radius: 4px;
  padding: 0 0.3rem;
}
</style>
