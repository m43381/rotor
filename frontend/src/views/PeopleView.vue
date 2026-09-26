<script setup lang="ts">
// Личный состав в зоне ответственности: виртуальный скролл с ленивой подгрузкой
// (десятки тысяч строк), фильтр по дереву, поиск, массовые операции.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import type { VirtualScrollerLazyEvent } from 'primevue/virtualscroller'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, personnel, unwrap, type PersonCreate, type PersonListItem } from '@/api/client'
import ExemptionDialog from '@/components/ExemptionDialog.vue'
import PersonFormDialog from '@/components/PersonFormDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'
import { LazyRows } from '@/utils/lazyRows'

const units = useUnitsStore()
const refs = useRefsStore()
const toast = useToast()
const router = useRouter()

const unitId = ref<string | null>(null)
const query = ref('')
const includeArchived = ref(false)
const selection = ref<PersonListItem[]>([])
const busy = ref(false)

const canEdit = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))

const lazy = reactive(
  new LazyRows<PersonListItem>(async (offset, limit) =>
    unwrap(
      personnel.GET('/people', {
        params: {
          query: {
            offset,
            limit,
            unit_id: unitId.value ?? undefined,
            q: query.value.trim() || undefined,
            include_archived: includeArchived.value,
          },
        },
      }),
    ),
  ),
)

async function reload() {
  selection.value = []
  try {
    await lazy.reset()
  } catch (e) {
    showError(e)
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(reload, 300)
})
watch([unitId, includeArchived], reload)

onMounted(async () => {
  await Promise.all([units.me ? Promise.resolve() : units.load(), refs.ensure()]).catch(showError)
  await reload()
})

function onLazyLoad(event: VirtualScrollerLazyEvent) {
  lazy.ensure(event.first, event.last).catch(showError)
}

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось загрузить данные'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

function openRow(e: { data: PersonListItem | undefined; originalEvent: Event }) {
  // Клик по чекбоксу выбора не должен открывать карточку.
  const target = e.originalEvent.target as HTMLElement | null
  if (!e.data || target?.closest('.p-checkbox, [data-pc-section="checkbox"]')) return
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

// --- перевод ----------------------------------------------------------------------------------
const transferVisible = ref(false)
const transferTarget = ref<string | null>(null)
async function onTransfer() {
  if (!transferTarget.value) return
  busy.value = true
  try {
    const r = await unwrap(
      personnel.POST('/people/transfer', {
        body: { person_ids: selection.value.map((p) => p.id), unit_id: transferTarget.value },
      }),
    )
    transferVisible.value = false
    toast.add({ severity: 'success', summary: `Переведено: ${r.done}`, life: 3000 })
    await reload()
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

// --- массовое освобождение --------------------------------------------------------------------
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
    const skippedList = r.skipped ?? []
    const skipped = skippedList.length
    toast.add({
      severity: skipped ? 'warn' : 'success',
      summary: `Освобождение оформлено: ${r.done}`,
      detail: skipped
        ? `Пропущено ${skipped}: ` +
          skippedList.map((s) => `${String(s.name ?? '')} — ${String(s.reason)}`).join('; ')
        : undefined,
      life: skipped ? 10000 : 3000,
    })
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
        <p class="muted">Найдено: {{ lazy.total }}<span v-if="selection.length"> · выбрано: {{ selection.length }}</span></p>
      </div>
      <div class="actions">
        <Button
          v-if="canEdit"
          label="Перевести"
          icon="pi pi-arrow-right-arrow-left"
          severity="secondary"
          :disabled="!selection.length"
          @click="((transferTarget = null), (transferVisible = true))"
        />
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
      <label class="archived">
        <Checkbox v-model="includeArchived" binary input-id="archived" />
        <span>Показывать архив</span>
      </label>
    </div>

    <DataTable
      v-model:selection="selection"
      :value="lazy.rows"
      data-key="id"
      scrollable
      scroll-height="flex"
      class="table"
      :virtual-scroller-options="{ lazy: true, onLazyLoad, itemSize: 44, delay: 100, showLoader: true }"
      :row-class="(row: PersonListItem | undefined) => (row && !row.is_active ? 'archived-row' : '')"
      @row-click="openRow"
    >
      <template #empty>Никого не найдено</template>
      <Column selection-mode="multiple" style="width: 3rem" />
      <Column header="ФИО">
        <template #body="{ data }">
          <span v-if="data" class="fio">{{ fio(data) }}</span>
          <span v-else class="skeleton" />
        </template>
      </Column>
      <Column header="Звание" style="width: 11rem">
        <template #body="{ data }">{{ data?.rank_name ?? '' }}</template>
      </Column>
      <Column header="Должность" style="width: 16rem">
        <template #body="{ data }">{{ data?.position_name ?? '' }}</template>
      </Column>
      <Column header="Подразделение" style="width: 16rem">
        <template #body="{ data }">{{ data?.unit_name ?? '' }}</template>
      </Column>
      <Column header="Личный №" style="width: 9rem">
        <template #body="{ data }">
          {{ data?.personal_no ?? '' }}
          <Tag v-if="data && !data.is_active" value="Архив" severity="secondary" />
        </template>
      </Column>
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
    <Dialog v-model:visible="transferVisible" header="Перевод в подразделение" modal :style="{ width: '30rem' }">
      <div class="transfer">
        <p class="muted">Выбрано человек: {{ selection.length }}</p>
        <UnitTreeSelect v-model="transferTarget" placeholder="Куда перевести" />
        <div class="dialog-actions">
          <Button label="Отмена" severity="secondary" text @click="transferVisible = false" />
          <Button label="Перевести" :disabled="!transferTarget" :loading="busy" @click="onTransfer" />
        </div>
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
.archived {
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
.table :deep(.archived-row) {
  color: var(--p-text-muted-color);
}
.fio {
  font-weight: 600;
}
.skeleton {
  display: inline-block;
  width: 12rem;
  height: 0.8rem;
  border-radius: 4px;
  background: var(--p-content-border-color);
}
.transfer {
  display: grid;
  gap: 0.75rem;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
