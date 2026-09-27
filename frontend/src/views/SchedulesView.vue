<script setup lang="ts">
// График подразделения на месяц (фаза 3a): таблица «роль наряда × день», делегирование ролей
// прямым дочерним подразделениям, принятие входящих, закрепление, публикация (ADR-0009).
// Выделение: клик — ячейка, Shift+клик — прямоугольник, клик по роли или дню — строка/столбец.
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  ApiError,
  scheduling,
  unwrap,
  type Cell,
  type PendingWarning,
  type Schedule,
  type ScheduleTable,
  type TableRow,
} from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { formatDateTime } from '@/utils/dates'
import { formatInterval } from '@/utils/duty'
import { abbr, monthIso, monthTitle, rect, shiftMonth, weekday, type CellPos } from '@/utils/schedule'

const units = useUnitsStore()
const toast = useToast()
const confirm = useConfirm()
const route = useRoute()
const router = useRouter()

const unitId = ref<string | null>((route.query.unit as string | undefined) ?? null)
const month = ref<string>((route.query.month as string | undefined) ?? monthIso(new Date()))
const schedules = ref<Schedule[]>([])
const table = ref<ScheduleTable | null>(null)
const loading = ref(false)
const busy = ref(false)
const selected = ref(new Set<string>())
const anchor = ref<CellPos | null>(null)
const executorId = ref<string | null>(null)

const current = computed(() => schedules.value.find((s) => s.unit_id === unitId.value) ?? null)
const canCreate = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))
const editable = computed(() => table.value?.schedule.can_edit === true)
const others = computed(() =>
  schedules.value.filter((s) => s.unit_id !== unitId.value && s.pending_incoming > 0),
)
const monthDate = computed({
  get: () => {
    const [y = 1970, m = 1] = month.value.split('-').map(Number)
    return new Date(y, m - 1, 1)
  },
  set: (d: Date | null) => {
    if (d) month.value = monthIso(d)
  },
})

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

async function load() {
  if (!unitId.value) return
  loading.value = true
  try {
    schedules.value = await unwrap(scheduling.GET('/schedules', { params: { query: { month: month.value } } }))
    const s = current.value
    table.value = s
      ? await unwrap(scheduling.GET('/schedules/{schedule_id}/table', { params: { path: { schedule_id: s.id } } }))
      : null
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

watch([unitId, month], () => {
  selected.value = new Set()
  anchor.value = null
  void router.replace({ query: { unit: unitId.value ?? undefined, month: month.value } })
  void load()
})
onMounted(async () => {
  if (!units.me) await units.load().catch(showError)
  unitId.value ??= units.me?.unit.id ?? null
  await load()
})

// --- строки: группировка ролей по нарядам ----------------------------------------------------
interface Group {
  key: string
  row: TableRow
  roles: { row: TableRow; index: number }[]
}
const groups = computed<Group[]>(() => {
  const result: Group[] = []
  table.value?.rows.forEach((row, index) => {
    const last = result[result.length - 1]
    if (last && last.key === row.duty_type_id) last.roles.push({ row, index })
    else result.push({ key: row.duty_type_id, row, roles: [{ row, index }] })
  })
  return result
})

// --- выделение ----------------------------------------------------------------------------
function cellAt(pos: CellPos): Cell | null {
  return table.value?.rows[pos.row]?.cells[pos.col] ?? null
}

function toggle(ids: string[], on?: boolean) {
  const next = new Set(selected.value)
  const add = on ?? ids.some((id) => !next.has(id))
  for (const id of ids) {
    if (add) next.add(id)
    else next.delete(id)
  }
  selected.value = next
}

function clickCell(pos: CellPos, event: MouseEvent) {
  const cell = cellAt(pos)
  if (!cell || !editable.value) return
  if (event.shiftKey && anchor.value) {
    const ids = rect(anchor.value, pos)
      .map(cellAt)
      .filter((c): c is Cell => !!c)
      .map((c) => c.id)
    toggle(ids, true)
  } else {
    toggle([cell.id])
    anchor.value = pos
  }
}

function selectRow(index: number) {
  if (!editable.value) return
  const ids = (table.value?.rows[index]?.cells ?? []).filter((c): c is Cell => !!c).map((c) => c.id)
  toggle(ids)
}

function selectColumn(col: number) {
  if (!editable.value) return
  const ids = (table.value?.rows ?? []).map((r) => r.cells[col]).filter((c): c is Cell => !!c).map((c) => c.id)
  toggle(ids)
}

const selectedCells = computed(() => {
  const result: Cell[] = []
  for (const row of table.value?.rows ?? []) {
    for (const c of row.cells) if (c && selected.value.has(c.id)) result.push(c)
  }
  return result
})
const acceptable = computed(() => selectedCells.value.filter((c) => c.state === 'incoming_pending'))
const delegable = computed(() => selectedCells.value.filter((c) => c.state !== 'inactive'))

// --- отображение ячейки -------------------------------------------------------------------
const STATE_LABELS: Record<string, string> = {
  own: 'Своя роль, закрывает подразделение',
  delegated_pending: 'Передана — ещё не принята',
  delegated_accepted: 'Передана и принята',
  incoming_pending: 'Входящая — ждёт принятия',
  incoming_active: 'Входящая — принята',
  incoming_delegated_pending: 'Входящая, передана дальше — ещё не принята',
  incoming_delegated_accepted: 'Входящая, передана дальше и принята',
  inactive: 'Роль не действует',
}

function executorName(c: Cell) {
  return table.value?.units[c.executor_unit_id]?.name ?? ''
}

function cellText(c: Cell): string {
  switch (c.state) {
    case 'own':
      return ''
    case 'incoming_pending':
      return '?'
    case 'incoming_active':
      return '●'
    case 'inactive':
      return '—'
    default: {
      const u = table.value?.units[c.executor_unit_id]
      return u ? abbr(u.name, u.short_name) : '…'
    }
  }
}

function cellTitle(c: Cell, date: string): string {
  const who = c.state.includes('delegated') ? ` → ${executorName(c)}` : ''
  return `${date.split('-').reverse().join('.')}: ${STATE_LABELS[c.state] ?? c.state}${who}${c.is_pinned ? ' (закреплено)' : ''}`
}

const STATUS: Record<string, { label: string; severity: string }> = {
  draft: { label: 'Черновик', severity: 'secondary' },
  published: { label: 'Опубликован', severity: 'success' },
  archived: { label: 'В архиве', severity: 'contrast' },
}

// --- действия -----------------------------------------------------------------------------
async function run(action: () => Promise<{ changed: number }>, success: string) {
  busy.value = true
  try {
    const r = await action()
    toast.add({ severity: 'success', summary: success, detail: `Ячеек: ${r.changed}`, life: 3000 })
    selected.value = new Set()
    await load()
  } catch (e) {
    showError(e)
    if (e instanceof ApiError && e.status === 409) await load()
  } finally {
    busy.value = false
  }
}

function scheduleId(): string {
  const s = table.value?.schedule
  if (!s) throw new Error('Нет графика')
  return s.id
}

function delegate(executor: string, success: string) {
  const ids = delegable.value.map((c) => c.id)
  // Смена решения удаляет цепочку ниже — предупреждаем, если там уже приняли
  const accepted = delegable.value.filter((c) => c.state.endsWith('delegated_accepted')).length
  const go = () =>
    run(
      () =>
        unwrap(
          scheduling.POST('/schedules/{schedule_id}/delegate', {
            params: { path: { schedule_id: scheduleId() } },
            body: { cell_ids: ids, executor_unit_id: executor },
          }),
        ),
      success,
    )
  if (!accepted) return go()
  confirm.require({
    header: 'Изменить решение?',
    message: `${accepted} из выбранных ячеек уже приняты ниже по цепочке. Решения нижестоящих подразделений по ним будут отменены.`,
    icon: 'pi pi-exclamation-triangle',
    acceptProps: { label: 'Изменить', severity: 'warn' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: go,
  })
}

function accept(all: boolean) {
  return run(
    () =>
      unwrap(
        scheduling.POST('/schedules/{schedule_id}/accept', {
          params: { path: { schedule_id: scheduleId() } },
          body: { cell_ids: all ? null : acceptable.value.map((c) => c.id) },
        }),
      ),
    'Входящие приняты',
  )
}

function pin(pinned: boolean) {
  return run(
    () =>
      unwrap(
        scheduling.POST('/schedules/{schedule_id}/pin', {
          params: { path: { schedule_id: scheduleId() } },
          body: { cell_ids: selectedCells.value.map((c) => c.id), pinned },
        }),
      ),
    pinned ? 'Закреплено' : 'Закрепление снято',
  )
}

async function create() {
  if (!unitId.value) return
  busy.value = true
  try {
    await unwrap(scheduling.POST('/schedules', { body: { unit_id: unitId.value, month: month.value } }))
    toast.add({ severity: 'success', summary: 'График создан', life: 3000 })
    await load()
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

const warnings = ref<PendingWarning[]>([])
const warningsVisible = ref(false)

function publish() {
  const s = table.value?.schedule
  if (!s) return
  confirm.require({
    header: 'Опубликовать график?',
    message: `График на ${monthTitle(s.month)} станет утверждённым. Изменения после публикации возможны и попадают в журнал.`,
    icon: 'pi pi-send',
    acceptProps: { label: 'Опубликовать' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: async () => {
      busy.value = true
      try {
        const r = await unwrap(
          scheduling.POST('/schedules/{schedule_id}/publish', {
            params: { path: { schedule_id: s.id } },
            body: { version: s.version },
          }),
        )
        warnings.value = r.warnings
        if (r.warnings.length) warningsVisible.value = true
        else toast.add({ severity: 'success', summary: 'График опубликован', life: 3000 })
        await load()
      } catch (e) {
        showError(e)
      } finally {
        busy.value = false
      }
    },
  })
}

function archive() {
  const s = table.value?.schedule
  if (!s) return
  confirm.require({
    header: 'Перенести график в архив?',
    message: 'Архивный график доступен только для просмотра.',
    icon: 'pi pi-inbox',
    acceptProps: { label: 'В архив', severity: 'secondary' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: async () => {
      busy.value = true
      try {
        await unwrap(
          scheduling.POST('/schedules/{schedule_id}/archive', {
            params: { path: { schedule_id: s.id } },
            body: { version: s.version },
          }),
        )
        await load()
      } catch (e) {
        showError(e)
      } finally {
        busy.value = false
      }
    },
  })
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div class="title">
        <h1>Графики</h1>
        <template v-if="table">
          <Tag :value="STATUS[table.schedule.status]?.label" :severity="STATUS[table.schedule.status]?.severity" />
          <small v-if="table.schedule.published_at" class="muted">
            опубликован {{ formatDateTime(table.schedule.published_at) }}, {{ table.schedule.published_by }}
          </small>
        </template>
      </div>
      <div class="actions">
        <Button
          v-if="editable && table && table.schedule.pending_incoming"
          :label="`Принять все входящие (${table.schedule.pending_incoming})`"
          icon="pi pi-check-circle"
          severity="secondary"
          :loading="busy"
          @click="accept(true)"
        />
        <Button
          v-if="editable && table?.schedule.status === 'draft'"
          label="Опубликовать"
          icon="pi pi-send"
          :loading="busy"
          @click="publish"
        />
        <Button
          v-if="editable && table?.schedule.status === 'published'"
          label="В архив"
          icon="pi pi-inbox"
          severity="secondary"
          text
          @click="archive"
        />
      </div>
    </header>

    <div class="filters">
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Подразделение" />
      </div>
      <div class="month">
        <Button icon="pi pi-chevron-left" text rounded aria-label="Предыдущий месяц" @click="month = shiftMonth(month, -1)" />
        <DatePicker v-model="monthDate" view="month" date-format="MM yy" input-id="month" class="month-picker" />
        <Button icon="pi pi-chevron-right" text rounded aria-label="Следующий месяц" @click="month = shiftMonth(month, 1)" />
      </div>
      <span v-for="s in others" :key="s.id" class="pending-chip">
        <Button
          :label="`${s.unit_name}: входящих ${s.pending_incoming}`"
          icon="pi pi-inbox"
          size="small"
          severity="warn"
          text
          @click="unitId = s.unit_id"
        />
      </span>
    </div>

    <Message v-if="!loading && unitId && !table" severity="secondary" :closable="false">
      Графика на {{ monthTitle(month) }} нет.
      <Button
        v-if="canCreate"
        label="Создать график"
        icon="pi pi-plus"
        size="small"
        class="inline-btn"
        :loading="busy"
        @click="create"
      />
    </Message>

    <template v-if="table">
      <div v-if="editable" class="selection-bar">
        <span class="muted">
          <template v-if="selected.size">Выбрано ячеек: {{ selected.size }}</template>
          <template v-else>Выберите ячейки: клик, Shift+клик — прямоугольник, клик по роли или дню — вся строка/столбец</template>
        </span>
        <template v-if="selected.size">
          <Select
            v-model="executorId"
            :options="table.children"
            option-label="name"
            option-value="id"
            placeholder="Кому передать"
            class="executor"
            input-id="executor"
            :disabled="!table.children.length"
          />
          <Button
            label="Делегировать"
            icon="pi pi-share-alt"
            size="small"
            :disabled="!executorId || !delegable.length"
            :loading="busy"
            @click="executorId && delegate(executorId, 'Роль передана')"
          />
          <Button
            label="Вернуть себе"
            icon="pi pi-undo"
            size="small"
            severity="secondary"
            :disabled="!delegable.length"
            @click="delegate(table.schedule.unit_id, 'Роль возвращена')"
          />
          <Button
            v-if="acceptable.length"
            :label="`Принять (${acceptable.length})`"
            icon="pi pi-check"
            size="small"
            severity="success"
            @click="accept(false)"
          />
          <Button label="Закрепить" icon="pi pi-lock" size="small" severity="secondary" text @click="pin(true)" />
          <Button label="Открепить" icon="pi pi-lock-open" size="small" severity="secondary" text @click="pin(false)" />
          <Button label="Снять выделение" size="small" severity="secondary" text @click="selected = new Set()" />
        </template>
      </div>

      <div class="grid-wrap">
        <table class="grid">
          <thead>
            <tr>
              <th class="sticky role-col">Наряд / роль</th>
              <th
                v-for="(d, col) in table.days"
                :key="d.date"
                :class="['day', d.kind]"
                :title="d.name ?? undefined"
                @click="selectColumn(col)"
              >
                <div>{{ Number(d.date.slice(8)) }}</div>
                <small>{{ weekday(d.date) }}</small>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in groups" :key="g.key">
              <tr class="type-row">
                <td class="sticky role-col">
                  <strong>{{ g.row.duty_type_name }}</strong>
                  <small class="muted">
                    · {{ g.row.owner_unit_name }} · {{ formatInterval(g.row.start_time, g.row.duration_minutes) }}
                  </small>
                </td>
                <td :colspan="table.days.length" />
              </tr>
              <tr v-for="r in g.roles" :key="r.row.duty_role_id">
                <td class="sticky role-col role" :class="{ inactive: !r.row.is_active }" @click="selectRow(r.index)">
                  {{ r.row.role_name }} <small class="muted">×{{ r.row.headcount }}</small>
                </td>
                <td
                  v-for="(c, col) in r.row.cells"
                  :key="col"
                  :class="[
                    'cell',
                    table.days[col]?.kind,
                    c?.state,
                    { selected: c && selected.has(c.id), empty: !c, clickable: c && editable },
                  ]"
                  :title="c ? cellTitle(c, table.days[col]?.date ?? '') : undefined"
                  :data-cell="c?.id"
                  @click="clickCell({ row: r.index, col }, $event)"
                >
                  <template v-if="c">
                    {{ cellText(c) }}<i v-if="c.is_pinned" class="pi pi-lock pin" />
                  </template>
                </td>
              </tr>
            </template>
            <tr v-if="!table.rows.length">
              <td class="sticky role-col muted" :colspan="table.days.length + 1">
                В графике нет ролей: у подразделения нет своих нарядов и входящих ролей.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="legend">
        <span v-for="(label, state) in STATE_LABELS" :key="state" class="legend-item">
          <span :class="['swatch', 'cell', state]" />{{ label }}
        </span>
      </div>
    </template>

    <Dialog v-model:visible="warningsVisible" header="График опубликован" modal :style="{ width: '32rem' }">
      <p>В поддереве остались непринятые ячейки. Публикацию это не блокирует, но их стоит проверить:</p>
      <ul>
        <li v-for="w in warnings" :key="w.unit_id">{{ w.unit_name }} — {{ w.count }}</li>
      </ul>
      <div class="dialog-actions">
        <Button label="Понятно" @click="warningsVisible = false" />
      </div>
    </Dialog>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0.75rem;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
}
.actions,
.filters,
.selection-bar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}
.unit-filter {
  width: 22rem;
  max-width: 100%;
}
.month {
  display: flex;
  align-items: center;
}
.month-picker :deep(input) {
  width: 10rem;
  text-align: center;
}
.inline-btn {
  margin-left: 0.75rem;
}
.selection-bar {
  min-height: 2.5rem;
}
.executor {
  width: 16rem;
}
.grid-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--p-content-border-color);
  border-radius: 6px;
}
.grid {
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.85rem;
  user-select: none;
}
.grid th,
.grid td {
  border-bottom: 1px solid var(--p-content-border-color);
  border-right: 1px solid var(--p-content-border-color);
  padding: 0;
}
.grid thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--p-content-background);
}
.sticky {
  position: sticky;
  left: 0;
  z-index: 1;
  background: var(--p-content-background);
}
thead .sticky {
  z-index: 3;
}
.role-col {
  min-width: 17rem;
  max-width: 22rem;
  padding: 0.3rem 0.6rem !important;
  text-align: left;
}
.role {
  cursor: pointer;
}
.role.inactive {
  color: var(--p-text-muted-color);
  text-decoration: line-through;
}
.type-row td {
  background: var(--p-content-hover-background);
}
.type-row .sticky {
  background: var(--p-content-hover-background);
  white-space: nowrap;
}
.day {
  width: 2.4rem;
  min-width: 2.4rem;
  text-align: center;
  cursor: pointer;
  line-height: 1.1;
  padding: 0.2rem 0 !important;
}
.day small {
  color: var(--p-text-muted-color);
}
.day.weekend,
.day.holiday {
  color: var(--p-red-500);
}
.cell {
  height: 2rem;
  text-align: center;
  font-size: 0.72rem;
  font-weight: 600;
  white-space: nowrap;
  position: relative;
}
.cell.clickable {
  cursor: pointer;
}
.cell.weekend,
.cell.holiday {
  background-image: linear-gradient(rgb(239 68 68 / 0.06), rgb(239 68 68 / 0.06));
}
.cell.own {
  background-color: var(--p-emerald-50);
}
.cell.incoming_active {
  background-color: var(--p-emerald-100);
  color: var(--p-emerald-700);
}
.cell.delegated_pending,
.cell.incoming_delegated_pending {
  background-color: var(--p-amber-100);
  color: var(--p-amber-800);
}
.cell.delegated_accepted,
.cell.incoming_delegated_accepted {
  background-color: var(--p-sky-100);
  color: var(--p-sky-800);
}
.cell.incoming_pending {
  background-color: var(--p-orange-200);
  color: var(--p-orange-800);
}
.cell.inactive {
  background-color: var(--p-surface-200);
  color: var(--p-text-muted-color);
}
.cell.selected {
  outline: 2px solid var(--p-primary-color);
  outline-offset: -2px;
}
.pin {
  position: absolute;
  top: 1px;
  right: 1px;
  font-size: 0.5rem;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem 1rem;
  font-size: 0.8rem;
  color: var(--p-text-muted-color);
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}
.swatch {
  display: inline-block;
  width: 1rem;
  height: 1rem;
  border: 1px solid var(--p-content-border-color);
  border-radius: 3px;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
