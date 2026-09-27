<script setup lang="ts">
// Типы нарядов: свои и своего поддерева (можно менять), а также вышестоящих подразделений
// (только просмотр: их роли могут прийти по делегированию). Состав по ролям с требованиями.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'

import {
  ApiError,
  scheduling,
  unwrap,
  type DutyRole,
  type DutyRoleIn,
  type DutyType,
  type DutyTypeCreate,
  type DutyTypeUpdate,
} from '@/api/client'
import DutyRoleDialog from '@/components/DutyRoleDialog.vue'
import DutyTypeDialog from '@/components/DutyTypeDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'
import { describeRequirements, formatDuration, formatInterval } from '@/utils/duty'

const units = useUnitsStore()
const refs = useRefsStore()
const toast = useToast()

const types = ref<DutyType[]>([])
const loading = ref(false)
const busy = ref(false)
const unitId = ref<string | null>(null)
const includeInactive = ref(false)
const expanded = ref<Record<string, boolean>>({})

const canCreate = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))

async function load() {
  loading.value = true
  try {
    types.value = await unwrap(
      scheduling.GET('/duty-types', {
        params: { query: { unit_id: unitId.value ?? undefined, include_inactive: includeInactive.value } },
      }),
    )
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}
watch([unitId, includeInactive], load)
onMounted(async () => {
  await Promise.all([units.me ? Promise.resolve() : units.load(), refs.ensure()]).catch(showError)
  await load()
})

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

function replace(updated: DutyType) {
  const i = types.value.findIndex((t) => t.id === updated.id)
  if (i >= 0) types.value[i] = updated
  else types.value.push(updated)
}

async function run(action: () => Promise<DutyType>, success: string): Promise<boolean> {
  busy.value = true
  try {
    const t = await action()
    replace(t)
    expanded.value = { ...expanded.value, [t.id]: true }
    toast.add({ severity: 'success', summary: success, life: 3000 })
    return true
  } catch (e) {
    showError(e)
    if (e instanceof ApiError && e.status === 409) await load()
    return false
  } finally {
    busy.value = false
  }
}

const composition = (t: DutyType) =>
  t.roles
    .filter((r) => r.is_active)
    .map((r) => `${r.name} ×${r.headcount}`)
    .join(', ')

const requirementsText = (r: DutyRole) =>
  describeRequirements(r, refs.ranks, refs.positions, refs.attributes).join('; ') || 'без требований'

// --- тип наряда -------------------------------------------------------------------------------
const typeVisible = ref(false)
const editingType = ref<DutyType | null>(null)

function openType(t: DutyType | null) {
  editingType.value = t
  typeVisible.value = true
}

async function onCreate(value: DutyTypeCreate) {
  const ok = await run(() => unwrap(scheduling.POST('/duty-types', { body: value })), 'Наряд создан')
  if (ok) typeVisible.value = false
}

async function onUpdate(value: DutyTypeUpdate) {
  const t = editingType.value
  if (!t) return
  const ok = await run(
    () => unwrap(scheduling.PUT('/duty-types/{type_id}', { params: { path: { type_id: t.id } }, body: value })),
    'Наряд изменён',
  )
  if (ok) {
    typeVisible.value = false
    if (!value.is_active && !includeInactive.value) types.value = types.value.filter((x) => x.id !== t.id)
  }
}

// --- роли -------------------------------------------------------------------------------------
const roleVisible = ref(false)
const roleType = ref<DutyType | null>(null)
const editingRole = ref<DutyRole | null>(null)

function openRole(t: DutyType, r: DutyRole | null) {
  roleType.value = t
  editingRole.value = r
  roleVisible.value = true
}

async function onRole(value: DutyRoleIn) {
  const t = roleType.value
  const r = editingRole.value
  if (!t) return
  const ok = await run(
    () =>
      r
        ? unwrap(
            scheduling.PUT('/duty-roles/{role_id}', {
              params: { path: { role_id: r.id } },
              body: { ...value, version: r.version },
            }),
          )
        : unwrap(
            scheduling.POST('/duty-types/{type_id}/roles', {
              params: { path: { type_id: t.id } },
              body: { ...value, sort_order: t.roles.length },
            }),
          ),
    r ? 'Роль изменена' : 'Роль добавлена',
  )
  if (ok) roleVisible.value = false
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Наряды</h1>
        <p class="muted">
          Свои наряды и наряды вышестоящих подразделений. Состав — по ролям, у роли — требования
          к человеку.
        </p>
      </div>
      <div class="actions">
        <Button v-if="canCreate" label="Новый наряд" icon="pi pi-plus" @click="openType(null)" />
      </div>
    </header>

    <div class="filters">
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Касаются подразделения…" show-clear />
      </div>
      <label class="check">
        <Checkbox v-model="includeInactive" binary input-id="inactive" />
        <span>Показывать выведенные из действия</span>
      </label>
    </div>

    <DataTable
      v-model:expanded-rows="expanded"
      :value="types"
      data-key="id"
      :loading="loading"
      class="table"
      :row-class="(row: DutyType) => (row.is_active ? '' : 'inactive-row')"
    >
      <template #empty>Нарядов нет</template>
      <Column expander style="width: 3rem" />
      <Column header="Наряд">
        <template #body="{ data }">
          <span class="name">{{ data.name }}</span>
          <span v-if="data.short_name" class="muted-inline"> ({{ data.short_name }})</span>
          <Tag v-if="!data.is_active" value="Не действует" severity="secondary" class="tag" />
          <Tag v-else-if="!data.can_edit" value="Вышестоящий" severity="info" class="tag" />
        </template>
      </Column>
      <Column header="Подразделение" style="width: 14rem">
        <template #body="{ data }">
          {{ data.owner_unit_name }}
          <div v-if="data.assigned_unit_name" class="muted-inline">закреплён: {{ data.assigned_unit_name }}</div>
        </template>
      </Column>
      <Column header="Время" style="width: 15rem">
        <template #body="{ data }">
          {{ formatInterval(data.start_time, data.duration_minutes) }}
          <div class="muted-inline">{{ formatDuration(data.duration_minutes) }}, отдых {{ data.rest_hours }} ч</div>
        </template>
      </Column>
      <Column header="Состав">
        <template #body="{ data }">{{ composition(data) }}</template>
      </Column>
      <Column style="width: 4rem">
        <template #body="{ data }">
          <Button
            v-if="data.can_edit"
            icon="pi pi-pencil"
            text
            rounded
            aria-label="Изменить наряд"
            @click="openType(data)"
          />
        </template>
      </Column>
      <template #expansion="{ data }">
        <div class="roles">
          <DataTable :value="data.roles" data-key="id" size="small">
            <Column header="Роль">
              <template #body="{ data: role }">
                {{ role.name }}
                <Tag v-if="!role.is_active" value="Не действует" severity="secondary" class="tag" />
              </template>
            </Column>
            <Column field="headcount" header="Человек" style="width: 6rem" />
            <Column header="Требования">
              <template #body="{ data: role }">
                <span :class="{ 'muted-inline': requirementsText(role) === 'без требований' }">
                  {{ requirementsText(role) }}
                </span>
              </template>
            </Column>
            <Column v-if="data.can_edit" style="width: 4rem">
              <template #body="{ data: role }">
                <Button
                  icon="pi pi-pencil"
                  text
                  rounded
                  :aria-label="`Изменить роль ${role.name}`"
                  @click="openRole(data, role)"
                />
              </template>
            </Column>
          </DataTable>
          <Button
            v-if="data.can_edit"
            label="Добавить роль"
            icon="pi pi-plus"
            text
            size="small"
            @click="openRole(data, null)"
          />
        </div>
      </template>
    </DataTable>

    <DutyTypeDialog
      v-model:visible="typeVisible"
      :duty-type="editingType"
      :busy="busy"
      :default-owner-id="unitId ?? units.me?.unit.id ?? null"
      @create="onCreate"
      @update="onUpdate"
    />
    <DutyRoleDialog
      v-model:visible="roleVisible"
      :role="editingRole"
      :busy="busy"
      :title="editingRole ? `Роль: ${editingRole.name}` : `Новая роль — ${roleType?.name ?? ''}`"
      @submit="onRole"
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
.muted-inline {
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
}
.filters {
  display: flex;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
}
.unit-filter {
  width: 22rem;
  max-width: 100%;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}
.table {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.table :deep(.inactive-row) {
  color: var(--p-text-muted-color);
}
.name {
  font-weight: 600;
}
.tag {
  margin-left: 0.5rem;
}
.roles {
  padding: 0.25rem 0 0.25rem 2.5rem;
  display: grid;
  gap: 0.25rem;
  justify-items: start;
}
.roles > :first-child {
  width: 100%;
}
</style>
