<script setup lang="ts">
// Отчёт о несоответствиях допусков (ADR-0009): действующие допуски, которые сейчас не проходят
// требования роли — выданные вопреки требованиям или устаревшие после смены звания,
// должности, характеристик или самих требований.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, personnel, unwrap, type MismatchItem } from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { formatDate } from '@/utils/dates'

const units = useUnitsStore()
const toast = useToast()
const router = useRouter()

const unitId = ref<string | null>(null)
const rows = ref<MismatchItem[]>([])
const total = ref(0)
const first = ref(0)
const pageSize = ref(50)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await unwrap(
      personnel.GET('/reports/clearance-mismatches', {
        params: { query: { unit_id: unitId.value ?? undefined, offset: first.value, limit: pageSize.value } },
      }),
    )
    rows.value = page.items
    total.value = page.total
  } catch (e) {
    const detail = e instanceof ApiError ? e.message : 'Не удалось загрузить отчёт'
    toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
  } finally {
    loading.value = false
  }
}

function onPage(event: DataTablePageEvent) {
  first.value = event.first
  pageSize.value = event.rows
  void load()
}
watch(unitId, () => {
  first.value = 0
  void load()
})
onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  await load()
})
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <Button icon="pi pi-arrow-left" text rounded aria-label="Назад" @click="router.push('/people')" />
        <h1>Несоответствия допусков</h1>
      </div>
      <p class="muted">
        Действующие допуски, которые не проходят текущие требования роли. Такой допуск продолжает
        действовать (допуск важнее требований), но его стоит проверить: отозвать или подтвердить.
      </p>
    </header>

    <div class="filters">
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Все подразделения" show-clear />
      </div>
      <span class="muted">Найдено: {{ total }}</span>
    </div>

    <DataTable
      :value="rows"
      data-key="clearance_id"
      lazy
      paginator
      :first="first"
      :rows="pageSize"
      :rows-per-page-options="[25, 50, 100]"
      :total-records="total"
      :loading="loading"
      scrollable
      scroll-height="flex"
      class="table"
      @page="onPage"
      @row-click="(e) => router.push(`/people/${e.data.person_id}`)"
    >
      <template #empty>Несоответствий нет</template>
      <Column header="Человек" style="width: 16rem">
        <template #body="{ data }">
          <div class="name">{{ data.person_name }}</div>
          <small class="sub">{{ data.unit_name }}</small>
        </template>
      </Column>
      <Column header="Роль и наряд" style="width: 18rem">
        <template #body="{ data }">
          {{ data.role_name }}
          <div class="sub">{{ data.duty_type_name }} · {{ data.owner_unit_name }}</div>
        </template>
      </Column>
      <Column header="Что не так">
        <template #body="{ data }">
          <ul class="violations">
            <li v-for="v in data.violations" :key="v.message">{{ v.message }}</li>
          </ul>
        </template>
      </Column>
      <Column header="Допуск" style="width: 14rem">
        <template #body="{ data }">
          <Tag v-if="data.overrides_requirements" value="Выдан вопреки требованиям" severity="warn" />
          <Tag v-else value="Требования изменились" severity="secondary" />
          <div v-if="data.override_comment" class="sub">{{ data.override_comment }}</div>
          <div v-if="data.valid_to" class="sub">до {{ formatDate(data.valid_to) }}</div>
        </template>
      </Column>
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
.page-header > div {
  display: flex;
  align-items: center;
  gap: 0.5rem;
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
  gap: 1rem;
  align-items: center;
}
.unit-filter {
  width: 22rem;
  max-width: 100%;
}
.table {
  flex: 1;
  min-height: 0;
}
.table :deep(tbody tr) {
  cursor: pointer;
}
.name {
  font-weight: 600;
}
.sub {
  color: var(--p-text-muted-color);
  font-size: 0.85rem;
}
.violations {
  margin: 0;
  padding-left: 1.1rem;
}
</style>
