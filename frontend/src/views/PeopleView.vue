<script setup lang="ts">
// Личный состав в зоне ответственности: постраничная навигация (open-questions №33),
// фильтр по дереву, поиск, массовое освобождение.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, personnel, unwrap, type PersonCreate, type PersonListItem } from '@/api/client'
import ExemptionDialog from '@/components/ExemptionDialog.vue'
import PersonFormDialog from '@/components/PersonFormDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'

const units = useUnitsStore()
const refs = useRefsStore()
const toast = useToast()
const router = useRouter()

const unitId = ref<string | null>(null)
const query = ref('')
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
watch([unitId, includeExcluded], reload)

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
          Найдено: {{ total }}<span v-if="selection.length"> · выбрано: {{ selection.length }}</span>
        </p>
      </div>
      <div class="actions">
        <Button
          v-if="canEdit"
          label="Освобождение"
          icon="pi pi-calendar-minus"
          severity="secondary"
          :disabled="!selection.length"
          @click="exemptionVisible = true"
        />
        <Button v-if="canEdit" label="Добавить" icon="pi pi-plus" @click="createVisible = true" />
      </div>
    </header>

    <div class="filters">
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Все подразделения" show-clear />
      </div>
      <span class="search">
        <i class="pi pi-search" />
        <InputText v-model="query" placeholder="ФИО или личный номер" aria-label="Поиск" />
      </span>
      <label class="excluded">
        <Checkbox v-model="includeExcluded" binary input-id="excluded" />
        <span>Показывать исключённых из списков</span>
      </label>
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
      <template #empty>Никого не найдено</template>
      <Column selection-mode="multiple" style="width: 3rem" />
      <Column header="ФИО">
        <template #body="{ data }">
          <span class="fio">{{ fio(data) }}</span>
          <Tag v-if="!data.is_active" value="Исключён из списков" severity="secondary" class="tag" />
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
.search {
  position: relative;
  display: inline-flex;
  align-items: center;
}
.search .pi {
  position: absolute;
  left: 0.75rem;
  color: var(--p-text-muted-color);
}
.search :deep(input) {
  padding-left: 2.25rem;
  width: 18rem;
}
.excluded {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  margin-left: 0.5rem;
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
