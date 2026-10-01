<script setup lang="ts">
// График подразделения на месяц (фаза 3a): таблица «роль наряда × день», делегирование ролей
// прямым дочерним подразделениям, принятие входящих, закрепление, публикация (ADR-0009).
// Выделение: клик — ячейка, Shift+клик — прямоугольник, клик по роли или дню — строка/столбец.
// Двойной клик по ячейке — панель назначения людей (фаза 3b).
// «Распределить…» — автораспределение с предпросмотром и применением (фаза 4b).
// Фаза 8: шаги процесса со сводкой над таблицей, режимы отображения (исполнители, люди,
// заполнение), подсветка ячеек, требующих действий, подсказка при наведении, отметка
// сегодняшнего дня и незаполненных мест.
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import Popover from 'primevue/popover'
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  ApiError,
  scheduling,
  unwrap,
  type Cell,
  type Decision,
  type PendingWarning,
  type Run,
  type Schedule,
  type ScheduleTable,
  type TableRow,
} from '@/api/client'
import AllocateDialog from '@/components/AllocateDialog.vue'
import AllocationPanel from '@/components/AllocationPanel.vue'
import CellPanel from '@/components/CellPanel.vue'
import PrintDialog from '@/components/PrintDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { formatDateTime, toIso } from '@/utils/dates'
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
const isSuperadmin = computed(() => units.me?.roles.includes('superadmin') === true)
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
  preview.value = null
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
  if (cell && preview.value) {
    focusCell.value = cell.id  // в предпросмотре щелчок показывает объяснение
    return
  }
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

function cellText(c: Cell, headcount: number): string {
  switch (c.state) {
    case 'own':
    case 'incoming_active':
      return c.filled ? `${c.filled}/${headcount}` : ''
    case 'incoming_pending':
      return c.filled ? `${c.filled}/${headcount}` : '?'
    case 'inactive':
      return '—'
    default: {
      const u = table.value?.units[c.executor_unit_id]
      return u ? abbr(u.name, u.short_name) : '…'
    }
  }
}

function fillClass(c: Cell, headcount: number): string | undefined {
  if (!c.filled) return undefined
  return c.filled >= headcount ? 'full' : 'partial'
}

// --- сводка и шаги процесса (фаза 8) ------------------------------------------------------------
/** Ячейку закрывает само подразделение графика своими людьми. */
const isOwnFill = (c: Cell) => c.state === 'own' || c.state === 'incoming_active'
const isUnfilled = (c: Cell, headcount: number) => isOwnFill(c) && c.filled < headcount
const isWaiting = (c: Cell) => c.state === 'incoming_pending'
const isDelegatedPending = (c: Cell) => c.state === 'delegated_pending' || c.state === 'incoming_delegated_pending'

const summary = computed(() => {
  const result = { toFill: 0, unfilled: 0, places: 0, placesFilled: 0, waiting: 0, delegated: 0, delegatedPending: 0, conflicts: 0 }
  for (const row of table.value?.rows ?? []) {
    if (!row.is_active) continue
    for (const c of row.cells) {
      if (!c) continue
      if (isOwnFill(c)) {
        result.toFill += 1
        result.places += row.headcount
        result.placesFilled += Math.min(c.filled, row.headcount)
        if (c.filled < row.headcount) result.unfilled += 1
      }
      if (isWaiting(c)) result.waiting += 1
      if (c.state.includes('delegated')) result.delegated += 1
      if (isDelegatedPending(c)) result.delegatedPending += 1
      if (c.has_conflict) result.conflicts += 1
    }
  }
  return result
})

type StepState = 'done' | 'todo' | 'skip'
const steps = computed(() => {
  const s = summary.value
  const status = table.value?.schedule.status
  const list: { key: Highlight; title: string; text: string; state: StepState }[] = [
    {
      key: 'waiting',
      title: 'Приём входящих',
      text: s.waiting ? `ждут принятия: ${s.waiting}` : 'все входящие приняты',
      state: s.waiting ? 'todo' : 'done',
    },
    {
      key: 'delegated',
      title: 'Передача ролей',
      text: !s.delegated
        ? 'роли не передавались'
        : s.delegatedPending
          ? `не приняты ниже: ${s.delegatedPending} из ${s.delegated}`
          : `передано и принято: ${s.delegated}`,
      state: !s.delegated ? 'skip' : s.delegatedPending ? 'todo' : 'done',
    },
    {
      key: 'unfilled',
      title: 'Назначение людей',
      text: s.toFill ? `${s.placesFilled} из ${s.places} мест` + (s.unfilled ? ` · без людей ${s.unfilled} яч.` : '') : 'своих мест нет',
      state: !s.toFill ? 'skip' : s.unfilled ? 'todo' : 'done',
    },
    {
      key: 'conflicts',
      title: 'Проверка',
      text: s.conflicts ? `нарушений: ${s.conflicts}` : 'нарушений нет',
      state: s.conflicts ? 'todo' : 'done',
    },
    {
      key: 'all',
      title: 'Публикация',
      text: status === 'published' ? 'опубликован' : status === 'archived' ? 'в архиве' : 'черновик',
      state: status === 'draft' ? 'todo' : 'done',
    },
  ]
  return list
})
const fillPercent = computed(() =>
  summary.value.places ? Math.round((summary.value.placesFilled / summary.value.places) * 100) : 100,
)

// --- режимы отображения и подсветка ----------------------------------------------------------
type Mode = 'executors' | 'people' | 'fill'
type Highlight = 'all' | 'unfilled' | 'waiting' | 'delegated' | 'conflicts'
const MODES: { value: Mode; label: string }[] = [
  { value: 'executors', label: 'Исполнители' },
  { value: 'people', label: 'Люди' },
  { value: 'fill', label: 'Заполнение' },
]
const MODE_KEY = 'dutyflow.schedule.mode'
function savedMode(): Mode {
  try {
    const v = localStorage.getItem(MODE_KEY)
    if (v === 'people' || v === 'fill') return v
  } catch {
    /* по умолчанию — исполнители */
  }
  return 'executors'
}
const mode = ref<Mode>(savedMode())
watch(mode, (v) => {
  try {
    localStorage.setItem(MODE_KEY, v)
  } catch {
    /* не запомнили — не страшно */
  }
})
const highlight = ref<Highlight>('all')
function toggleHighlight(key: Highlight) {
  highlight.value = highlight.value === key || key === 'all' ? 'all' : key
}
function matches(c: Cell, headcount: number): boolean {
  switch (highlight.value) {
    case 'unfilled':
      return isUnfilled(c, headcount)
    case 'waiting':
      return isWaiting(c)
    case 'delegated':
      return isDelegatedPending(c)
    case 'conflicts':
      return c.has_conflict
    default:
      return true
  }
}

const shortName = (full: string) => full.split(' ')[0] ?? full
function displayText(c: Cell, headcount: number): string {
  if (mode.value === 'fill') return c.state === 'inactive' ? '—' : `${c.filled}/${headcount}`
  if (mode.value === 'people' && isOwnFill(c)) {
    const people = c.assigned ?? []
    if (!people.length) return ''
    const first = people[0]
    return first ? shortName(first.person_name) + (people.length > 1 ? ` +${people.length - 1}` : '') : ''
  }
  return cellText(c, headcount)
}

const todayIso = toIso(new Date())
const todayCol = computed(() => table.value?.days.findIndex((d) => d.date === todayIso) ?? -1)

// --- подсказка при наведении -------------------------------------------------------------------
const hover = ref<{ cell: Cell; row: TableRow; date: string; x: number; y: number } | null>(null)
function hoverCell(cell: Cell | null, row: TableRow, date: string, e: MouseEvent) {
  if (!cell) {
    hover.value = null
    return
  }
  hover.value = { cell, row, date, x: e.clientX, y: e.clientY }
}
const tipStyle = computed(() => {
  const h = hover.value
  if (!h) return {}
  const right = h.x > window.innerWidth - 320
  const below = h.y < window.innerHeight - 220
  return {
    left: right ? `${h.x - 16}px` : `${h.x + 16}px`,
    top: below ? `${h.y + 16}px` : `${h.y - 16}px`,
    transform: `translate(${right ? '-100%' : '0'}, ${below ? '0' : '-100%'})`,
  }
})
function longDate(iso: string): string {
  const [y = 1970, m = 1, d = 1] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
}

const legend = ref<InstanceType<typeof Popover> | null>(null)

// --- автораспределение: предпросмотр → применение (фаза 4b) -----------------------------------
const allocateVisible = ref(false)
const printVisible = ref(false)
const preview = ref<Run | null>(null)
const stale = ref(false)
const focusCell = ref<string | null>(null)

const proposals = computed(() => {
  const byCell = new Map<string, Decision[]>()
  for (const d of preview.value?.decisions ?? []) {
    byCell.set(d.day_plan_id, [...(byCell.get(d.day_plan_id) ?? []), d])
  }
  return byCell
})
// Фоновый расчёт (фаза 5b): опрос прогона, пока не готов
const elapsed = ref(0)
let poller: ReturnType<typeof setInterval> | undefined
let startedAt = 0

function stopPolling() {
  clearInterval(poller)
  poller = undefined
}

function startPolling() {
  stopPolling()
  startedAt = Date.now()
  elapsed.value = 0
  poller = setInterval(async () => {
    const run = preview.value
    if (!run || (run.status !== 'queued' && run.status !== 'running')) return stopPolling()
    elapsed.value = Math.round((Date.now() - startedAt) / 1000)
    try {
      const fresh = await unwrap(
        scheduling.GET('/allocation-runs/{run_id}', { params: { path: { run_id: run.id } } }),
      )
      if (preview.value?.id !== fresh.id) return
      if (fresh.status === 'queued' || fresh.status === 'running') {
        preview.value = { ...run, status: fresh.status }
      } else {
        stopPolling()
        showPreview(fresh)
      }
    } catch (e) {
      stopPolling()
      showError(e)
    }
  }, 2000)
}
onBeforeUnmount(stopPolling)

const focused = computed(() => (focusCell.value ? (proposals.value.get(focusCell.value) ?? []) : []))

function proposalText(c: Cell): string | null {
  const items = proposals.value.get(c.id)
  if (!items?.length || !preview.value) return null
  if (preview.value.kind === 'units') {
    const name = items[0]?.chosen_name ?? ''
    return abbr(name)
  }
  return `+${items.length}`
}

function showPreview(run: Run) {
  preview.value = run
  if (run.status === 'queued' || run.status === 'running') startPolling()
  stale.value = run.status === 'stale'
  focusCell.value = run.decisions[0]?.day_plan_id ?? null
  selected.value = new Set()
}

async function applyPreview() {
  const run = preview.value
  if (!run) return
  busy.value = true
  try {
    const result = await unwrap(
      scheduling.POST('/allocation-runs/{run_id}/apply', { params: { path: { run_id: run.id } } }),
    )
    toast.add({
      severity: 'success',
      summary: 'Распределение применено',
      detail: `${result.filled} ${result.kind === 'people' ? 'назначений' : 'ячеек передано'}`,
      life: 4000,
    })
    preview.value = null
    await load()
  } catch (e) {
    if (e instanceof ApiError && e.code === 'run_stale') stale.value = true
    else showError(e)
  } finally {
    busy.value = false
  }
}

async function discardPreview() {
  const run = preview.value
  if (!run) return
  try {
    await unwrap(scheduling.POST('/allocation-runs/{run_id}/discard', { params: { path: { run_id: run.id } } }))
  } catch (e) {
    showError(e)
  }
  preview.value = null
}

async function recalc() {
  const run = preview.value
  const s = table.value?.schedule
  if (!run || !s) return
  busy.value = true
  try {
    const cfg = run.config as { cell_ids?: string[] | null }
    showPreview(
      await unwrap(
        scheduling.POST('/schedules/{schedule_id}/allocate', {
          params: { path: { schedule_id: s.id } },
          body: {
            kind: run.kind as 'people' | 'units',
            mode: run.mode as 'fill' | 'rebuild',
            method: ((run.config as { method?: string }).method ?? 'auto') as
              | 'auto'
              | 'greedy'
              | 'hungarian'
              | 'local_search'
              | 'cpsat',
            cell_ids: cfg.cell_ids ?? null,
            seed: run.seed,
            config: {},
          },
        }),
      ),
    )
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

// --- панель назначения людей ------------------------------------------------------------------
const panelVisible = ref(false)
const panelCell = ref<string | null>(null)

function openPanel(id: string) {
  panelCell.value = id
  panelVisible.value = true
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
  const send = (drop: boolean) =>
    unwrap(
      scheduling.POST('/schedules/{schedule_id}/delegate', {
        params: { path: { schedule_id: scheduleId() } },
        body: { cell_ids: ids, executor_unit_id: executor, drop_assignments: drop },
      }),
    )
  const go = () =>
    run(async () => {
      try {
        return await send(false)
      } catch (e) {
        if (!(e instanceof ApiError && e.code === 'assignments_exist')) throw e
        // В ячейках уже есть люди — снимать их только с явного согласия
        const agreed = await new Promise<boolean>((resolve) =>
          confirm.require({
            header: 'Снять назначенных людей?',
            message: `${e.message} Продолжить?`,
            icon: 'pi pi-exclamation-triangle',
            acceptProps: { label: 'Снять и продолжить', severity: 'danger' },
            rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
            accept: () => resolve(true),
            reject: () => resolve(false),
            onHide: () => resolve(false),
          }),
        )
        if (!agreed) return { changed: 0 }
        return send(true)
      }
    }, success)
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

/** Снимок задачи для движка (ADR-0013) — файлом, для отладки и бенчмарков. */
async function downloadSnapshot() {
  const s = table.value?.schedule
  if (!s) return
  busy.value = true
  try {
    const { data, response } = await scheduling.GET('/schedules/{schedule_id}/snapshot', {
      params: { path: { schedule_id: s.id } },
      parseAs: 'blob',
    })
    if (!response.ok || !data) throw new ApiError(response.status, 'error', 'Не удалось собрать снимок')
    const name = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1]
    const link = document.createElement('a')
    link.href = URL.createObjectURL(data)
    link.download = name ?? 'snapshot.json'
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
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
/** Удалить черновик: пустой или созданный по ошибке. Назначенных людей — только с согласия. */
function removeSchedule() {
  const s = table.value?.schedule
  if (!s) return
  const send = (drop: boolean) =>
    unwrap(
      scheduling.DELETE('/schedules/{schedule_id}', {
        params: { path: { schedule_id: s.id }, query: { version: s.version, drop_assignments: drop } },
      }),
    )
  const ask = (header: string, message: string, label: string) =>
    new Promise<boolean>((resolve) =>
      confirm.require({
        header,
        message,
        icon: 'pi pi-exclamation-triangle',
        acceptProps: { label, severity: 'danger' },
        rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
        accept: () => resolve(true),
        reject: () => resolve(false),
        onHide: () => resolve(false),
      }),
    )
  void (async () => {
    const title = `${s.unit_name ?? 'Подразделение'}, ${monthTitle(month.value)}`
    if (
      !(await ask(
        'Удалить график?',
        `График «${title}» будет удалён вместе с ячейками. Наряды, переданные нижестоящим, у них тоже исчезнут.`,
        'Удалить',
      ))
    )
      return
    busy.value = true
    try {
      try {
        await send(false)
      } catch (e) {
        if (!(e instanceof ApiError && e.code === 'assignments_exist')) throw e
        if (!(await ask('Снять назначенных людей?', `${e.message} Продолжить?`, 'Снять и удалить'))) return
        await send(true)
      }
      toast.add({ severity: 'success', summary: 'График удалён', life: 3000 })
      preview.value = null
      selected.value = new Set()
      await load()
    } catch (e) {
      showError(e)
    } finally {
      busy.value = false
    }
  })()
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
          v-if="editable && table && !preview"
          label="Распределить…"
          icon="pi pi-bolt"
          :loading="busy"
          @click="allocateVisible = true"
        />
        <Button
          v-if="table"
          label="Печать…"
          icon="pi pi-print"
          severity="secondary"
          @click="printVisible = true"
        />
        <Button
          v-if="isSuperadmin && table"
          label="Снимок задачи"
          icon="pi pi-download"
          severity="secondary"
          text
          :loading="busy"
          @click="downloadSnapshot"
        />
        <Button
          v-if="editable && table?.schedule.status === 'draft'"
          v-tooltip.bottom="'Удалить черновик графика'"
          icon="pi pi-trash"
          severity="danger"
          text
          aria-label="Удалить график"
          :loading="busy"
          @click="removeSchedule"
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

    <div v-if="!loading && unitId && !table" class="card empty-state">
      <i class="pi pi-calendar-plus" />
      <strong>Графика на {{ monthTitle(month) }} нет</strong>
      <span>
        График создаётся со всеми ролями своих нарядов. Входящие роли вышестоящих появятся в нём
        сами, когда их передадут.
      </span>
      <Button v-if="canCreate" label="Создать график" icon="pi pi-plus" :loading="busy" @click="create" />
    </div>

    <template v-if="table">
      <div class="steps" role="list" aria-label="Порядок работы с графиком">
        <button
          v-for="(st, i) in steps"
          :key="st.title"
          type="button"
          role="listitem"
          class="step"
          :class="[st.state, { active: highlight === st.key && st.key !== 'all' }]"
          :disabled="st.key === 'all' || st.state === 'skip'"
          :title="st.key !== 'all' && st.state === 'todo' ? `${st.text} — подсветить эти ячейки` : st.text"
          @click="toggleHighlight(st.key)"
        >
          <span class="step-mark">
            <i v-if="st.state === 'done'" class="pi pi-check" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span class="step-body">
            <span class="step-title">{{ st.title }}</span>
            <span class="step-text">{{ st.text }}</span>
          </span>
        </button>
        <div class="fill-meter" :title="`Укомплектовано ${fillPercent}% своих мест`">
          <span class="fill-value">{{ fillPercent }}%</span>
          <span class="fill-bar"><span :style="{ width: `${fillPercent}%` }" /></span>
          <span class="fill-label">укомплектовано</span>
        </div>
      </div>

      <div class="toolbar">
        <SelectButton
          v-model="mode"
          :options="MODES"
          option-label="label"
          option-value="value"
          :allow-empty="false"
          size="small"
          aria-label="Что показывать в ячейках"
        />
        <span v-if="highlight !== 'all'" class="chip chip--warn highlight-chip">
          <i class="pi pi-filter" />
          {{ steps.find((st) => st.key === highlight)?.title }}
          <button type="button" aria-label="Снять подсветку" @click="highlight = 'all'"><i class="pi pi-times" /></button>
        </span>
        <span class="spacer" />
        <Button
          v-tooltip.left="
            'Клик — ячейка, Shift+клик — прямоугольник, клик по роли или дню — строка или столбец; двойной клик — назначить людей'
          "
          icon="pi pi-question-circle"
          text
          rounded
          severity="secondary"
          size="small"
          aria-label="Как выбирать ячейки"
        />
        <Button
          label="Обозначения"
          icon="pi pi-palette"
          text
          severity="secondary"
          size="small"
          @click="legend?.toggle($event)"
        />
        <Popover ref="legend">
          <div class="legend">
            <span v-for="(label, state) in STATE_LABELS" :key="state" class="legend-item">
              <span :class="['swatch', 'cell', state]" />{{ label }}
            </span>
            <span class="legend-item"><span class="swatch cell own unfilled" />Своя ячейка без людей</span>
            <span class="legend-item"><span class="swatch cell own full" />Укомплектована</span>
            <span class="legend-item"><span class="swatch cell own conflict" />Нарушение (отдых, лимит)</span>
            <span class="legend-item"><i class="pi pi-lock legend-icon" />Исполнитель закреплён</span>
          </div>
        </Popover>
      </div>

      <!-- Место под панелью действий постоянное: иначе после первого клика таблица сдвигается
           и двойной клик промахивается -->
      <div v-if="editable && !preview" class="selection-bar" :class="{ idle: !selected.size }">
        <span v-if="selected.size" class="sel-count">
          <i class="pi pi-check-square" /> Выбрано ячеек: {{ selected.size }}
        </span>
        <span v-else class="muted sel-hint">
          <i class="pi pi-hand-pointer" /> Выберите ячейки — здесь появятся действия: передать, вернуть,
          принять, закрепить. Двойной клик — назначить людей.
        </span>
        <template v-if="selected.size">
          <Select
            v-model="executorId"
            :options="table.children"
            option-label="name"
            option-value="id"
            placeholder="Кому передать"
            size="small"
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
          <Button
            v-if="selectedCells.length === 1 && selectedCells[0]"
            label="Люди…"
            icon="pi pi-users"
            size="small"
            severity="secondary"
            @click="selectedCells[0] && openPanel(selectedCells[0].id)"
          />
          <Button label="Закрепить" icon="pi pi-lock" size="small" severity="secondary" text @click="pin(true)" />
          <Button label="Открепить" icon="pi pi-lock-open" size="small" severity="secondary" text @click="pin(false)" />
          <Button label="Снять выделение" size="small" severity="secondary" text @click="selected = new Set()" />
        </template>
      </div>

      <div class="work">
        <div class="grid-wrap">
          <table class="grid">
            <thead>
              <tr>
                <th class="sticky role-col">Наряд / роль</th>
                <th
                  v-for="(d, col) in table.days"
                  :key="d.date"
                  :class="['day', d.kind, { today: col === todayCol }]"
                  :title="d.name ?? (col === todayCol ? 'Сегодня' : undefined)"
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
                    <span
                      v-if="r.row.assigned_unit_name"
                      v-tooltip.right="
                        r.row.locked
                          ? `Роль закреплена за «${r.row.assigned_unit_name}»: ячейки передаются ему автоматически, изменить исполнителя здесь нельзя`
                          : `Роль закреплена за «${r.row.assigned_unit_name}»`
                      "
                      class="chip chip--unit role-pin"
                    >
                      <i :class="r.row.locked ? 'pi pi-lock' : 'pi pi-map-marker'" /> {{ r.row.assigned_unit_name }}
                    </span>
                  </td>
                  <td
                    v-for="(c, col) in r.row.cells"
                    :key="col"
                    :class="[
                      'cell',
                      table.days[col]?.kind,
                      c?.state,
                      c && (mode === 'fill' || isOwnFill(c)) && fillClass(c, r.row.headcount),
                      {
                        today: col === todayCol,
                        unfilled: c && r.row.is_active && isUnfilled(c, r.row.headcount),
                        dim: c && highlight !== 'all' && !matches(c, r.row.headcount),
                        wide: mode === 'people',
                        selected: c && selected.has(c.id),
                        empty: !c,
                        clickable: !!c,
                        conflict: c?.has_conflict,
                        proposed: c && proposals.has(c.id),
                        focused: c && preview && focusCell === c.id,
                      },
                    ]"
                    :data-cell="c?.id"
                    @mouseenter="hoverCell(c, r.row, table.days[col]?.date ?? '', $event)"
                    @mousemove="hover && (hover.x = $event.clientX, hover.y = $event.clientY)"
                    @mouseleave="hover = null"
                    @click="clickCell({ row: r.index, col }, $event)"
                    @dblclick="c && openPanel(c.id)"
                  >
                    <template v-if="c">
                      {{ proposalText(c) ?? displayText(c, r.row.headcount)
                      }}<i v-if="c.is_pinned" class="pi pi-lock pin" />
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

        <AllocationPanel
          v-if="preview"
          :run="preview"
          :decisions="focused"
          :busy="busy"
          :stale="stale"
          :elapsed="elapsed"
          @apply="applyPreview"
          @discard="discardPreview"
          @close="preview = null"
          @recalc="recalc"
        />
      </div>

      <div
        v-if="hover"
        class="cell-tip"
        :style="tipStyle"
        role="tooltip"
      >
        <div class="tip-date">{{ longDate(hover.date) }}</div>
        <div class="tip-role">{{ hover.row.duty_type_name }} · {{ hover.row.role_name }}</div>
        <div class="tip-state">
          <span :class="['swatch', 'cell', hover.cell.state]" />
          {{ STATE_LABELS[hover.cell.state] }}
        </div>
        <div v-if="hover.cell.state.includes('delegated')" class="tip-line">
          Исполнитель: <b>{{ executorName(hover.cell) }}</b>
        </div>
        <div class="tip-line">
          Назначено {{ hover.cell.filled }} из {{ hover.row.headcount }}
          <span v-if="isUnfilled(hover.cell, hover.row.headcount)" class="tip-warn">— нужны люди</span>
        </div>
        <ul v-if="hover.cell.assigned?.length" class="tip-people">
          <li v-for="a in hover.cell.assigned" :key="a.person_name" :class="{ conflict: a.conflict }">
            {{ a.person_name }}<span v-if="a.conflict"> — {{ a.conflict }}</span>
          </li>
        </ul>
        <div v-if="hover.cell.is_pinned" class="tip-line muted"><i class="pi pi-lock" /> закреплено</div>
        <div v-if="editable && !preview" class="tip-hint">Двойной клик — назначить людей</div>
      </div>
    </template>

    <AllocateDialog
      v-if="table"
      v-model:visible="allocateVisible"
      :schedule-id="table.schedule.id"
      :selected-cell-ids="[...selected]"
      :has-children="table.children.length > 0"
      :can-choose-method="isSuperadmin"
      @preview="showPreview"
    />
    <PrintDialog
      v-if="table"
      v-model:visible="printVisible"
      :schedule-id="table.schedule.id"
      :unit-id="table.schedule.unit_id"
      :month="table.schedule.month"
      :status="table.schedule.status"
    />
    <CellPanel v-model:visible="panelVisible" :cell-id="panelCell" @changed="load" />
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
  height: 2.9rem;
  box-sizing: border-box;
  flex-wrap: nowrap !important;
  overflow-x: auto;
  padding: 0.35rem 0.6rem;
  border-radius: var(--app-radius);
  background: var(--app-accent-soft);
  border: 1px solid var(--app-border-strong);
}
.selection-bar.idle {
  background: transparent;
  border-style: dashed;
  border-color: var(--app-border);
}
.sel-hint {
  font-size: 0.85rem;
}
.sel-count {
  font-weight: 600;
  margin-right: 0.25rem;
}
.sel-count .pi {
  color: var(--app-accent);
}
/* Шаги процесса */
.steps {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr)) auto;
  background: var(--app-card-bg);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  overflow: hidden;
}
.step {
  display: flex;
  gap: 0.6rem;
  align-items: flex-start;
  padding: 0.6rem 0.75rem;
  border: none;
  border-right: 1px solid var(--app-border);
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}
.step:disabled {
  cursor: default;
}
.step:not(:disabled):hover,
.step.active {
  background: var(--app-subtle);
}
.step.active {
  box-shadow: inset 0 -2px 0 var(--app-accent);
}
.step-mark {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  font-size: 0.75rem;
  font-weight: 700;
  border: 1.5px solid var(--app-border-strong);
  color: var(--app-ink-3);
}
.step.done .step-mark {
  border-color: var(--state-good);
  background: var(--state-good);
  color: #fff;
}
.step.done .step-mark .pi {
  font-size: 0.7rem;
}
.step.todo .step-mark {
  border-color: var(--state-serious);
  color: var(--state-serious);
}
.step.skip {
  opacity: 0.6;
}
.step-body {
  display: grid;
  min-width: 0;
}
.step-title {
  font-weight: 600;
  font-size: 0.86rem;
}
.step-text {
  font-size: 0.78rem;
  color: var(--app-ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.step.todo .step-text {
  color: var(--app-ink-2);
}
.fill-meter {
  display: grid;
  grid-template-columns: auto;
  align-content: center;
  gap: 0.2rem;
  padding: 0.5rem 1rem;
  min-width: 9rem;
}
.fill-value {
  font-size: 1.3rem;
  font-weight: 650;
  line-height: 1;
}
.fill-bar {
  height: 5px;
  border-radius: 3px;
  background: var(--app-hover);
  overflow: hidden;
}
.fill-bar span {
  display: block;
  height: 100%;
  background: var(--app-accent);
}
.fill-label {
  font-size: 0.72rem;
  color: var(--app-ink-3);
}
@media (max-width: 1200px) {
  .steps {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .fill-meter {
    display: none;
  }
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.toolbar .spacer {
  flex: 1;
}
.highlight-chip button {
  border: none;
  background: none;
  color: inherit;
  cursor: pointer;
  padding: 0 0 0 0.2rem;
}
.legend-icon {
  width: 1rem;
  text-align: center;
  font-size: 0.75rem;
}
.executor {
  width: 16rem;
}
.work {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 0.75rem;
}
.grid-wrap {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  background: var(--app-card-bg);
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
  color: var(--state-critical);
}
.day.today {
  background: var(--app-accent) !important;
  color: #fff;
}
.day.today small {
  color: rgb(255 255 255 / 0.8);
}
.cell.today {
  box-shadow: inset 1px 0 0 var(--app-accent), inset -1px 0 0 var(--app-accent);
}
.cell.wide {
  min-width: 5.6rem;
  max-width: 5.6rem;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  padding: 0 0.2rem !important;
}
/* Своя ячейка без людей: заметна сразу, даже без цвета — полосой и точкой в углу */
.cell.unfilled {
  box-shadow: inset 0 -3px 0 var(--state-critical);
}
.cell.unfilled::before {
  content: '';
  position: absolute;
  bottom: 5px;
  right: 4px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--state-critical);
}
.cell.delegated_pending,
.cell.incoming_delegated_pending,
.cell.incoming_pending {
  outline: 1px dashed rgb(201 133 0 / 0.7);
  outline-offset: -3px;
}
.cell.dim {
  opacity: 0.22;
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
.cell.partial {
  box-shadow: inset 0 -3px 0 var(--p-amber-400);
}
.cell.full {
  box-shadow: inset 0 -3px 0 var(--p-emerald-500);
}
.cell.conflict::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  border-top: 7px solid var(--p-red-500);
  border-right: 7px solid transparent;
}
.cell.proposed {
  background-color: var(--p-violet-100);
  color: var(--p-violet-800);
}
.cell.focused {
  outline: 2px solid var(--p-violet-500);
  outline-offset: -2px;
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
  display: grid;
  gap: 0.45rem;
  font-size: 0.84rem;
  color: var(--app-ink-2);
}
.cell-tip {
  position: fixed;
  z-index: 1100;
  width: 18rem;
  padding: 0.6rem 0.75rem;
  border-radius: 8px;
  background: var(--app-card-bg);
  border: 1px solid var(--app-border-strong);
  box-shadow: 0 8px 24px rgb(0 0 0 / 0.14);
  pointer-events: none;
  font-size: 0.84rem;
  display: grid;
  gap: 0.25rem;
}
.tip-date {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-ink-3);
}
.tip-role {
  font-weight: 600;
}
.tip-state {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--app-ink-2);
}
.tip-line {
  color: var(--app-ink-2);
}
.tip-warn {
  color: var(--state-critical);
  font-weight: 600;
}
.tip-people {
  margin: 0.15rem 0 0;
  padding-left: 1.1rem;
}
.tip-people .conflict {
  color: var(--state-critical);
}
.tip-hint {
  margin-top: 0.2rem;
  font-size: 0.75rem;
  color: var(--app-ink-3);
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
.role-pin {
  margin-left: 0.35rem;
  font-size: 0.72rem;
  padding: 0 0.4rem;
}
</style>

<style>
/* Не scoped: селектор темы стоит на <html>. Scoped-вариант с :global() свёл бы правило
   к одному `.app-dark` и перекрасил всю страницу. */
.app-dark :is(td, .swatch).cell.own {
  background-color: rgb(27 175 122 / 0.1);
}
.app-dark :is(td, .swatch).cell.incoming_active {
  background-color: rgb(27 175 122 / 0.22);
  color: #6fd9ae;
}
.app-dark :is(td, .swatch).cell.delegated_pending,
.app-dark :is(td, .swatch).cell.incoming_delegated_pending {
  background-color: rgb(201 133 0 / 0.22);
  color: #f0c060;
}
.app-dark :is(td, .swatch).cell.delegated_accepted,
.app-dark :is(td, .swatch).cell.incoming_delegated_accepted {
  background-color: rgb(57 135 229 / 0.22);
  color: #9ec5f4;
}
.app-dark :is(td, .swatch).cell.incoming_pending {
  background-color: rgb(217 89 38 / 0.3);
  color: #f5a27a;
}
.app-dark :is(td, .swatch).cell.inactive {
  background-color: var(--app-hover);
}
.app-dark :is(td, .swatch).cell.proposed {
  background-color: rgb(144 133 233 / 0.25);
  color: #c9c2f5;
}
</style>
