<script setup lang="ts">
// Дерево подразделений оператора: просмотр и изменение структуры (сценарий фазы 1),
// численность личного состава по узлам (фаза 8) и быстрый переход к людям и графику.
import Button from 'primevue/button'
import Column from 'primevue/column'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import ToggleSwitch from 'primevue/toggleswitch'
import TreeTable from 'primevue/treetable'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, personnel, unwrap, type Unit } from '@/api/client'
import MoveUnitDialog from '@/components/MoveUnitDialog.vue'
import UnitFormDialog from '@/components/UnitFormDialog.vue'
import { useUnitsStore } from '@/stores/units'
import { expandedKeys } from '@/utils/tree'

const store = useUnitsStore()
const toast = useToast()
const confirm = useConfirm()
const router = useRouter()

const expanded = ref<Record<string, boolean>>({})
const filter = ref('')
const busy = ref(false)

const formVisible = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const formUnit = ref<Unit | null>(null)
const moveVisible = ref(false)
const moveUnit = ref<Unit | null>(null)

const formTypes = computed(() => {
  if (!formUnit.value) return []
  if (formMode.value === 'create') return store.childTypes(formUnit.value)
  const parent = formUnit.value.parent_id ? store.byId.get(formUnit.value.parent_id) : undefined
  return parent ? store.childTypes(parent) : store.types
})

// Численность: люди прямо в подразделении и во всём поддереве (один запрос к personnel)
const direct = ref<Map<string, number>>(new Map())
async function loadCounts() {
  try {
    const rows = await unwrap(personnel.GET('/people/counts'))
    direct.value = new Map(rows.map((r) => [r.unit_id, r.people]))
  } catch {
    direct.value = new Map() // численность — справочная, без неё дерево работает
  }
}
const subtreeCount = computed(() => {
  const totals = new Map<string, number>()
  const byPath = new Map(store.units.map((u) => [u.path, u.id]))
  for (const u of store.units) {
    const n = direct.value.get(u.id) ?? 0
    if (!n) continue
    // Путь ltree — метки предков: добавляем к себе и к каждому видимому предку
    const labels = u.path.split('.')
    for (let i = labels.length; i > 0; i--) {
      const id = byPath.get(labels.slice(0, i).join('.'))
      if (id) totals.set(id, (totals.get(id) ?? 0) + n)
    }
  }
  return totals
})

onMounted(async () => {
  await Promise.all([run(store.load), loadCounts()])
  expanded.value = expandedKeys(store.tree, 2)
})

function openPeople(unit: Unit) {
  void router.push({ path: '/people', query: { unit: unit.id } })
}
function openSchedule(unit: Unit) {
  void router.push({ path: '/schedules', query: { unit: unit.id } })
}

async function run(action: () => Promise<unknown>, success?: string): Promise<boolean> {
  busy.value = true
  try {
    await action()
    if (success) toast.add({ severity: 'success', summary: success, life: 3000 })
    return true
  } catch (e) {
    const message = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
    toast.add({ severity: 'error', summary: 'Ошибка', detail: message, life: 6000 })
    // Конфликт версий — данные устарели, перечитываем дерево.
    if (e instanceof ApiError && e.status === 409) await store.load().catch(() => undefined)
    return false
  } finally {
    busy.value = false
  }
}

function openCreate(parent: Unit) {
  formMode.value = 'create'
  formUnit.value = parent
  formVisible.value = true
}

function openEdit(unit: Unit) {
  formMode.value = 'edit'
  formUnit.value = unit
  formVisible.value = true
}

function openMove(unit: Unit) {
  moveUnit.value = unit
  moveVisible.value = true
}

async function onFormSubmit(value: {
  name: string
  short_name: string | null
  unit_type_id: string
  sort_order: number
}) {
  const unit = formUnit.value
  if (!unit) return
  const ok =
    formMode.value === 'create'
      ? await run(async () => {
          await store.create({ parent_id: unit.id, ...value })
          expanded.value = { ...expanded.value, [unit.id]: true }
        }, 'Подразделение создано')
      : await run(() => store.update(unit, value), 'Изменения сохранены')
  if (ok) formVisible.value = false
}

async function onMoveSubmit(newParentId: string) {
  const unit = moveUnit.value
  if (!unit) return
  const ok = await run(async () => {
    await store.move(unit, newParentId)
    expanded.value = { ...expanded.value, [newParentId]: true }
  }, 'Подразделение перенесено')
  if (ok) moveVisible.value = false
}

// Суперадминистратор: показать расформированные, вернуть их или удалить пустое навсегда (ADR-0023)
const isSuperadmin = computed(() => store.me?.roles.includes('superadmin') ?? false)
watch(
  () => store.includeInactive,
  () => run(() => store.load(), ''),
)
onBeforeUnmount(() => {
  if (store.includeInactive) {
    store.includeInactive = false
    void store.load()
  }
})

function askRestore(unit: Unit) {
  confirm.require({
    header: 'Восстановить подразделение?',
    message: `«${unit.name}» вернётся в структуру на прежнее место.`,
    icon: 'pi pi-replay',
    acceptProps: { label: 'Восстановить' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: () => run(() => store.restore(unit), 'Подразделение восстановлено'),
  })
}

function askPurge(unit: Unit) {
  confirm.require({
    header: 'Удалить подразделение навсегда?',
    message:
      `«${unit.name}» будет удалено без возможности восстановления — только если в нём нет людей ` +
      '(включая архивных), дочерних подразделений, нарядов, графиков, лимитов и операторов.',
    icon: 'pi pi-exclamation-triangle',
    acceptProps: { label: 'Удалить навсегда', severity: 'danger' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: () => run(() => store.purge(unit), 'Подразделение удалено'),
  })
}

function askDeactivate(unit: Unit) {
  confirm.require({
    header: 'Расформировать подразделение?',
    message: `«${unit.name}» исчезнет из структуры. Данные и история сохранятся.`,
    icon: 'pi pi-exclamation-triangle',
    acceptProps: { label: 'Расформировать', severity: 'danger' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: () => run(() => store.deactivate(unit), 'Подразделение расформировано'),
  })
}

const filters = computed(() => ({ global: filter.value }))

function canParent(parent: Unit, child: Unit): boolean {
  const parentType = store.typeById.get(parent.unit_type_id)
  const childType = store.typeById.get(child.unit_type_id)
  return !!parentType && !!childType && parentType.can_have_children && parentType.level < childType.level
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Структура подразделений</h1>
        <p class="muted">
          Подразделений в зоне ответственности: <strong>{{ store.units.length }}</strong> · личного
          состава: <strong>{{ [...direct.values()].reduce((a, b) => a + b, 0) }}</strong>
        </p>
      </div>
      <label v-if="isSuperadmin" class="inactive-toggle">
        <ToggleSwitch v-model="store.includeInactive" /> Показать расформированные
      </label>
      <IconField class="search">
        <InputIcon class="pi pi-search" />
        <InputText v-model="filter" placeholder="Поиск по названию" aria-label="Поиск по названию" />
      </IconField>
    </header>

    <TreeTable
      v-model:expanded-keys="expanded"
      :value="store.tree"
      :loading="store.loading"
      :filters="filters"
      filter-mode="lenient"
      scrollable
      scroll-height="flex"
      class="tree"
    >
      <template #empty>Нет доступных подразделений</template>
      <Column field="name" header="Подразделение" expander filter-match-mode="contains">
        <template #body="{ node }">
          <span :class="{ inactive: !node.data.is_active }">{{ node.data.name }}</span>
          <span v-if="node.data.short_name" class="muted"> · {{ node.data.short_name }}</span>
        </template>
      </Column>
      <Column header="Тип" style="width: 12rem">
        <template #body="{ node }">
          <Tag :value="store.typeById.get(node.data.unit_type_id)?.name ?? '—'" severity="secondary" />
        </template>
      </Column>
      <Column header="Личный состав" style="width: 11rem">
        <template #body="{ node }">
          <button
            v-if="subtreeCount.get(node.data.id)"
            v-tooltip.top="
              direct.get(node.data.id) !== subtreeCount.get(node.data.id)
                ? `Всего с нижестоящими; прямо в подразделении — ${direct.get(node.data.id) ?? 0}`
                : 'Открыть список'
            "
            type="button"
            class="count-link"
            @click="openPeople(node.data)"
          >
            <i class="pi pi-users" /> {{ subtreeCount.get(node.data.id) }}
          </button>
          <span v-else class="muted-cell">—</span>
        </template>
      </Column>
      <Column header="Действия" style="width: 19rem">
        <template #body="{ node }">
          <div class="row-actions">
            <Button
              v-tooltip.top="'График нарядов'"
              icon="pi pi-calendar"
              text
              rounded
              severity="secondary"
              aria-label="График нарядов"
              @click="openSchedule(node.data)"
            />
            <Button
              v-tooltip.top="'Добавить дочернее'"
              icon="pi pi-plus"
              text
              rounded
              severity="secondary"
              aria-label="Добавить дочернее"
              :disabled="!node.data.permissions?.create_child"
              @click="openCreate(node.data)"
            />
            <Button
              v-tooltip.top="'Изменить'"
              icon="pi pi-pencil"
              text
              rounded
              severity="secondary"
              aria-label="Изменить"
              :disabled="!node.data.permissions?.update"
              @click="openEdit(node.data)"
            />
            <Button
              v-tooltip.top="'Перенести'"
              icon="pi pi-arrow-right-arrow-left"
              text
              rounded
              severity="secondary"
              aria-label="Перенести"
              :disabled="!node.data.permissions?.move"
              @click="openMove(node.data)"
            />
            <Button
              v-tooltip.top="'Расформировать'"
              icon="pi pi-trash"
              text
              rounded
              severity="danger"
              aria-label="Расформировать"
              :disabled="!node.data.permissions?.delete"
              @click="askDeactivate(node.data)"
            />
            <Button
              v-if="node.data.permissions?.restore"
              v-tooltip.top="'Восстановить'"
              icon="pi pi-replay"
              text
              rounded
              aria-label="Восстановить"
              @click="askRestore(node.data)"
            />
            <Button
              v-if="node.data.permissions?.purge"
              v-tooltip.top="'Удалить навсегда (только пустое)'"
              icon="pi pi-times-circle"
              text
              rounded
              severity="danger"
              aria-label="Удалить навсегда"
              @click="askPurge(node.data)"
            />
          </div>
        </template>
      </Column>
    </TreeTable>

    <UnitFormDialog
      v-model:visible="formVisible"
      :mode="formMode"
      :unit="formUnit"
      :types="formTypes"
      :busy="busy"
      @submit="onFormSubmit"
    />
    <MoveUnitDialog
      v-model:visible="moveVisible"
      :unit="moveUnit"
      :units="store.units"
      :busy="busy"
      :can-parent="canParent"
      @submit="onMoveSubmit"
    />
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 1rem;
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
.search :deep(input) {
  width: 18rem;
  max-width: 100%;
}
.tree {
  flex: 1;
  min-height: 0;
}
.row-actions {
  display: flex;
  gap: 0.125rem;
  opacity: 0.35;
  transition: opacity 0.15s;
}
/* Действия строки проявляются при наведении или фокусе — таблица не пестрит иконками */
.tree :deep(tr:hover) .row-actions,
.row-actions:focus-within {
  opacity: 1;
}
.count-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border: none;
  background: none;
  padding: 0.15rem 0.4rem;
  border-radius: 6px;
  font: inherit;
  color: var(--app-accent);
  cursor: pointer;
}
.count-link:hover {
  background: var(--app-accent-soft);
}
.muted-cell {
  color: var(--p-text-muted-color);
}
.inactive-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
  white-space: nowrap;
}
.inactive {
  text-decoration: line-through;
  color: var(--p-text-muted-color);
}
</style>
