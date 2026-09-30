<script setup lang="ts">
// Личный состав в зоне ответственности: постраничная навигация (open-questions №33),
// фильтры по дереву, категории, званию и освобождению, поиск; массовое освобождение
// и массовая выдача допусков для выбранных.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, personnel, unwrap, type PersonCreate, type PersonListItem } from '@/api/client'
import BulkClearanceDialog from '@/components/BulkClearanceDialog.vue'
import ExemptionDialog from '@/components/ExemptionDialog.vue'
import PersonFormDialog from '@/components/PersonFormDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'
import { formatDate } from '@/utils/dates'

const units = useUnitsStore()
const refs = useRefsStore()
const toast = useToast()
const router = useRouter()
const route = useRoute()

// Фильтры можно открыть ссылкой: /people?exempt=1 (с рабочего стола), ?unit=…
const unitId = ref<string | null>((route.query.unit as string | undefined) ?? null)
const query = ref('')
const categoryId = ref<string | null>(null)
const rankId = ref<string | null>(null)
const exemptToday = ref(route.query.exempt === '1')
const includeExcluded = ref(false)
const rows = ref<PersonListItem[]>([])
const total = ref(0)
const first = ref(0)
const pageSize = ref(50)
const loading = ref(false)
const selection = ref<PersonListItem[]>([])
const busy = ref(false)

const canEdit = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))

let requestId = 0
async function load() {
  const current = ++requestId
  loading.value = true
  try {
    const page = await unwrap(
      personnel.GET('/people', {
        params: {
          query: {
            offset: first.value,
            limit: pageSize.value,
            unit_id: unitId.value ?? undefined,
            q: query.value.trim() || undefined,
            category_id: categoryId.value ?? undefined,
            rank_id: rankId.value ?? undefined,
            exempt_today: exemptToday.value || undefined,
            include_archived: includeExcluded.value,
          },
        },
      }),
    )
    if (current !== requestId) return // ответ на устаревший запрос (фильтр уже сменили)
    rows.value = page.items
    total.value = page.total
  } catch (e) {
    showError(e)
  } finally {
    if (current === requestId) loading.value = false
  }
}

/** Новый фильтр — с первой страницы, выбор сбрасывается. */
function reload() {
  first.value = 0
  selection.value = []
  return load()
}

function onPage(event: DataTablePageEvent) {
  first.value = event.first
  pageSize.value = event.rows
  selection.value = []
  void load()
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(reload, 300)
})
watch([unitId, includeExcluded, categoryId, rankId, exemptToday], reload)

const filtered = computed(
  () => !!(unitId.value || query.value.trim() || categoryId.value || rankId.value || exemptToday.value),
)
function resetFilters() {
  unitId.value = categoryId.value = rankId.value = null
  query.value = ''
  exemptToday.value = false
}

onMounted(async () => {
  await Promise.all([units.me ? Promise.resolve() : units.load(), refs.ensure()]).catch(showError)
  await load()
})

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось загрузить данные'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

function openRow(e: { data: PersonListItem; originalEvent: Event }) {
  // Клик по чекбоксу выбора не должен открывать карточку.
  const target = e.originalEvent.target as HTMLElement | null
  if (target?.closest('.p-checkbox, [data-pc-section="checkbox"]')) return
  void router.push(`/people/${e.data.id}`)
}

function fio(p: PersonListItem) {
  return [p.last_name, p.first_name, p.middle_name].filter(Boolean).join(' ')
}

// --- добавление -------------------------------------------------------------------------------
const createVisible = ref(false)
async function onCreate(value: PersonCreate) {
  busy.value = true
  try {
    const person = await unwrap(personnel.POST('/people', { body: value }))
    createVisible.value = false
    toast.add({ severity: 'success', summary: 'Человек добавлен', life: 3000 })
    await router.push(`/people/${person.id}`)
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

// --- массовое освобождение (болезнь, отпуск, командировка группы людей) ----------------------
const exemptionVisible = ref(false)
const clearanceVisible = ref(false)
async function onBulkExemption(value: {
  reason_id: string
  date_from: string
  date_to: string
  comment: string | null
}) {
  busy.value = true
  try {
    const r = await unwrap(
      personnel.POST('/exemptions/bulk', {
        body: { ...value, person_ids: selection.value.map((p) => p.id) },
      }),
    )
    exemptionVisible.value = false
    const skipped = r.skipped ?? []
    toast.add({
      severity: skipped.length ? 'warn' : 'success',
      summary: `Освобождение оформлено: ${r.done}`,
      detail: skipped.length
        ? `Пропущено ${skipped.length}: ` +
          skipped.map((s) => `${String(s.name ?? '')} — ${String(s.reason)}`).join('; ')
        : undefined,
      life: skipped.length ? 10000 : 3000,
    })
    selection.value = []
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Личный состав</h1>
        <p class="muted">
          Люди, которые заступают в наряды: категория, звание, должность, освобождения и допуски.
          <span class="found">Найдено: {{ total }}</span>
        </p>
      </div>
      <div class="actions">
        <Button
          label="Несоответствия допусков"
          icon="pi pi-exclamation-triangle"
          severity="secondary"
          text
          @click="router.push('/reports/clearance-mismatches')"
        />
        <Button
          v-if="canEdit"
          label="Импорт"
          icon="pi pi-upload"
          severity="secondary"
          text
          @click="router.push('/import')"
        />
        <Button v-if="canEdit" label="Добавить человека" icon="pi pi-user-plus" @click="createVisible = true" />
      </div>
    </header>

    <div class="filters">
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Все подразделения" show-clear />
      </div>
      <IconField class="search">
        <InputIcon class="pi pi-search" />
        <InputText v-model="query" placeholder="ФИО или личный номер" aria-label="Поиск" />
      </IconField>
      <Select
        v-model="categoryId"
        :options="refs.categories"
        option-label="name"
        option-value="id"
        placeholder="Все категории"
        show-clear
        class="small-filter"
        aria-label="Категория"
      />
      <Select
        v-model="rankId"
        :options="refs.activeRanks"
        option-label="name"
        option-value="id"
        placeholder="Любое звание"
        show-clear
        filter
        class="small-filter"
        aria-label="Звание"
      />
      <label class="check">
        <Checkbox v-model="exemptToday" binary input-id="exempt" />
        <span>Освобождены сегодня</span>
      </label>
      <label class="check">
        <Checkbox v-model="includeExcluded" binary input-id="excluded" />
        <span>Показывать исключённых из списков</span>
      </label>
      <Button v-if="filtered" label="Сбросить" icon="pi pi-filter-slash" text size="small" @click="resetFilters" />
    </div>

    <div v-if="selection.length && canEdit" class="selection-bar">
      <span><i class="pi pi-check-square" /> Выбрано: <strong>{{ selection.length }}</strong></span>
      <Button label="Выдать допуск" icon="pi pi-verified" size="small" @click="clearanceVisible = true" />
      <Button
        label="Оформить освобождение"
        icon="pi pi-calendar-minus"
        size="small"
        severity="secondary"
        @click="exemptionVisible = true"
      />
      <Button label="Снять выбор" text size="small" @click="selection = []" />
    </div>

    <DataTable
      v-model:selection="selection"
      :value="rows"
      data-key="id"
      lazy
      paginator
      :first="first"
      :rows="pageSize"
      :rows-per-page-options="[25, 50, 100]"
      :total-records="total"
      :loading="loading"
      paginator-template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink RowsPerPageDropdown CurrentPageReport"
      current-page-report-template="{first}–{last} из {totalRecords}"
      scrollable
      scroll-height="flex"
      class="table"
      :row-class="(row: PersonListItem) => (row.is_active ? '' : 'excluded-row')"
      @page="onPage"
      @row-click="openRow"
    >
      <template #empty>
        <div class="empty-state">
          <i class="pi pi-users" />
          <strong>Никого не найдено</strong>
          <span v-if="filtered">Измените условия поиска или сбросьте фильтры.</span>
        </div>
      </template>
      <Column v-if="canEdit" selection-mode="multiple" style="width: 3rem" />
      <Column header="ФИО">
        <template #body="{ data }">
          <span class="fio">{{ fio(data) }}</span>
          <Tag v-if="!data.is_active" value="Исключён из списков" severity="secondary" class="tag" />
          <span
            v-else-if="data.exempt_until"
            v-tooltip.top="'Сегодня освобождён от нарядов'"
            class="chip chip--warn tag"
          >
            <i class="pi pi-calendar-times" /> {{ data.exempt_reason }} до {{ formatDate(data.exempt_until) }}
          </span>
        </template>
      </Column>
      <Column header="Категория" style="width: 11rem">
        <template #body="{ data }">
          <span v-if="data.category_name" class="chip chip--category">{{ data.category_name }}</span>
          <span v-else v-tooltip.top="'Укажите категорию в карточке'" class="chip chip--danger">не указана</span>
        </template>
      </Column>
      <Column field="rank_name" header="Звание" style="width: 11rem" />
      <Column field="position_name" header="Должность" style="width: 16rem" />
      <Column field="unit_name" header="Подразделение" style="width: 16rem" />
      <Column field="personal_no" header="Личный №" style="width: 9rem" />
    </DataTable>

    <PersonFormDialog
      v-model:visible="createVisible"
      :busy="busy"
      :default-unit-id="unitId ?? units.me?.unit.id ?? null"
      @submit="onCreate"
    />
    <BulkClearanceDialog v-model:visible="clearanceVisible" :person-ids="selection.map((p) => p.id)" />
    <ExemptionDialog
      v-model:visible="exemptionVisible"
      :title="`Освобождение для ${selection.length} чел.`"
      :busy="busy"
      @submit="onBulkExemption"
    />
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
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.actions,
.filters {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}
.unit-filter {
  width: 22rem;
  max-width: 100%;
}
.search :deep(input) {
  width: 16rem;
}
.found {
  font-weight: 600;
  color: var(--p-text-color);
  margin-left: 0.25rem;
}
.small-filter {
  width: 12rem;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  margin-left: 0.25rem;
}
.selection-bar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  padding: 0.5rem 0.8rem;
  border-radius: var(--app-radius);
  background: var(--app-accent-soft);
  border: 1px solid var(--app-border-strong);
}
.selection-bar .pi {
  color: var(--app-accent);
  margin-right: 0.2rem;
}
.table {
  flex: 1;
  min-height: 0;
}
.table :deep(tbody tr) {
  cursor: pointer;
}
.table :deep(.excluded-row) {
  color: var(--p-text-muted-color);
}
.fio {
  font-weight: 600;
}
.tag {
  margin-left: 0.5rem;
}
</style>
