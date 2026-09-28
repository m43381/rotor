<script setup lang="ts">
// Сводный журнал аудита (фаза 7b, ADR-0010, open-questions №64): все изменения всех сервисов —
// кто, что, когда, было → стало. Администратор и оператор видят своё поддерево, суперадминистратор —
// всё. Фильтры и выгрузка в xlsx.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'

import { analytics, ApiError, saveFile, unwrap } from '@/api/client'
import type { components } from '@/api/generated/analytics'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { ACTION_LABELS, changes, ENTITY_LABELS, fieldLabel, SERVICE_LABELS, valueText } from '@/utils/audit'
import { formatDateTime, toIso } from '@/utils/dates'

type Entry = components['schemas']['JournalEntry']

const units = useUnitsStore()
const toast = useToast()

const today = new Date()
const range = ref<Date[]>([new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6), today])
const unitId = ref<string | null>(null)
const actor = ref('')
const entityType = ref<string | null>(null)
const service = ref<string | null>(null)
const rows = ref<Entry[]>([])
const total = ref(0)
const first = ref(0)
const pageSize = ref(50)
const loading = ref(false)
const expanded = ref<Record<string, boolean>>({})
const facets = ref<{ entity_type: string[]; action: string[]; service: string[] }>({
  entity_type: [],
  action: [],
  service: [],
})

const entityOptions = computed(() =>
  facets.value.entity_type.map((e) => ({ value: e, label: ENTITY_LABELS[e] ?? e })),
)
const serviceOptions = computed(() =>
  facets.value.service.map((s) => ({ value: s, label: SERVICE_LABELS[s] ?? s })),
)

function query() {
  const [from, to] = range.value
  return {
    date_from: from ? toIso(from) : undefined,
    date_to: to ? toIso(to) : from ? toIso(from) : undefined,
    unit_id: unitId.value ?? undefined,
    actor: actor.value.trim() || undefined,
    entity_type: entityType.value ?? undefined,
    service: service.value ?? undefined,
  }
}

async function load() {
  loading.value = true
  try {
    const page = await unwrap(
      analytics.GET('/audit', { params: { query: { ...query(), limit: pageSize.value, offset: first.value } } }),
    )
    rows.value = page.items
    total.value = page.total
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : 'Журнал недоступен'
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
  } finally {
    loading.value = false
  }
}

async function exportXlsx() {
  try {
    await saveFile(analytics.GET('/audit/export', { params: { query: query() }, parseAs: 'blob' }), 'audit.xlsx')
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : 'Не удалось выгрузить журнал'
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
  }
}

function unitName(id: string): string | undefined {
  return units.byId.get(id)?.name
}

function onPage(e: DataTablePageEvent) {
  first.value = e.first
  pageSize.value = e.rows
  void load()
}

let timer: ReturnType<typeof setTimeout> | undefined
watch(actor, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    first.value = 0
    void load()
  }, 300)
})
watch([range, unitId, entityType, service], () => {
  if (range.value.length && !range.value[0]) return
  first.value = 0
  void load()
})
onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  facets.value = await unwrap(analytics.GET('/audit/facets')).catch(() => facets.value)
  await load()
})
</script>

<template>
  <section class="page">
    <header>
      <h1>Журнал изменений</h1>
      <p class="muted">
        Все изменения данных во всех разделах: кто, что, когда, было → стало. Показаны записи вашей зоны
        ответственности.
      </p>
    </header>

    <div class="filters">
      <DatePicker v-model="range" selection-mode="range" date-format="dd.mm.yy" show-icon input-id="audit-range" class="range" />
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Все подразделения" show-clear />
      </div>
      <IconField>
        <InputIcon class="pi pi-user" />
        <InputText v-model="actor" placeholder="Кто изменил" aria-label="Кто изменил" />
      </IconField>
      <Select v-model="entityType" :options="entityOptions" option-label="label" option-value="value" placeholder="Что изменено" show-clear class="select" />
      <Select v-model="service" :options="serviceOptions" option-label="label" option-value="value" placeholder="Раздел" show-clear class="select" />
      <span class="spacer" />
      <span class="muted">Записей: {{ total }}</span>
      <Button label="В Excel" icon="pi pi-file-excel" severity="secondary" text @click="exportXlsx" />
    </div>

    <DataTable
      v-model:expanded-rows="expanded"
      :value="rows"
      data-key="id"
      lazy
      paginator
      :first="first"
      :rows="pageSize"
      :rows-per-page-options="[50, 100, 200]"
      :total-records="total"
      :loading="loading"
      scrollable
      scroll-height="flex"
      class="table"
      @page="onPage"
    >
      <template #empty>Записей нет</template>
      <Column expander style="width: 3rem" />
      <Column header="Когда" style="width: 11rem">
        <template #body="{ data }">{{ formatDateTime(data.occurred_at) }}</template>
      </Column>
      <Column header="Кто" style="width: 14rem">
        <template #body="{ data }">{{ data.actor_name }}</template>
      </Column>
      <Column header="Что сделано">
        <template #body="{ data }">
          <div>{{ ACTION_LABELS[data.action] ?? data.action }}</div>
          <small class="muted">
            {{ ENTITY_LABELS[data.entity_type] ?? data.entity_type }}
            <template v-if="data.unit_name"> · {{ data.unit_name }}</template>
          </small>
          <div v-if="data.comment" class="comment">«{{ data.comment }}»</div>
        </template>
      </Column>
      <Column header="Раздел" style="width: 9rem">
        <template #body="{ data }"><Tag :value="SERVICE_LABELS[data.service] ?? data.service" severity="secondary" /></template>
      </Column>
      <template #expansion="{ data }">
        <table class="diff">
          <thead>
            <tr><th>Поле</th><th>Было</th><th>Стало</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in changes(data.before, data.after)" :key="c.field">
              <td>{{ fieldLabel(c.field) }}</td>
              <td class="before">{{ valueText(c.before, unitName) }}</td>
              <td class="after">{{ valueText(c.after, unitName) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0.75rem;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.filters {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}
.range {
  width: 15rem;
}
.unit-filter {
  width: 18rem;
}
.select {
  width: 13rem;
}
.spacer {
  flex: 1;
}
.table {
  flex: 1;
  min-height: 0;
}
.comment {
  font-size: 0.85rem;
  font-style: italic;
}
.diff {
  border-collapse: collapse;
  font-size: 0.9rem;
  margin: 0.25rem 0 0.25rem 3rem;
}
.diff th,
.diff td {
  border: 1px solid var(--p-content-border-color);
  padding: 0.25rem 0.6rem;
  text-align: left;
  vertical-align: top;
}
.diff .before {
  color: var(--p-text-muted-color);
}
.diff .after {
  font-weight: 600;
}
</style>
