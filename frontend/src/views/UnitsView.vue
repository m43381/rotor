<script setup lang="ts">
// Дерево подразделений оператора: просмотр и изменение структуры (сценарий фазы 1).
import Button from 'primevue/button'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import TreeTable from 'primevue/treetable'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref } from 'vue'

import { ApiError, type Unit } from '@/api/client'
import MoveUnitDialog from '@/components/MoveUnitDialog.vue'
import UnitFormDialog from '@/components/UnitFormDialog.vue'
import { useUnitsStore } from '@/stores/units'
import { expandedKeys } from '@/utils/tree'

const store = useUnitsStore()
const toast = useToast()
const confirm = useConfirm()

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

onMounted(async () => {
  await run(store.load)
  expanded.value = expandedKeys(store.tree, 2)
})

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
        <p class="muted">Показаны подразделения в зоне ответственности: {{ store.units.length }}</p>
      </div>
      <span class="search">
        <i class="pi pi-search" />
        <InputText v-model="filter" placeholder="Поиск по названию" aria-label="Поиск по названию" />
      </span>
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
      <Column header="Тип" style="width: 14rem">
        <template #body="{ node }">
          <Tag :value="store.typeById.get(node.data.unit_type_id)?.name ?? '—'" severity="secondary" />
        </template>
      </Column>
      <Column header="Действия" style="width: 13rem">
        <template #body="{ node }">
          <div class="row-actions">
            <Button
              v-tooltip.top="'Добавить дочернее'"
              icon="pi pi-plus"
              text
              rounded
              aria-label="Добавить дочернее"
              :disabled="!node.data.permissions?.create_child"
              @click="openCreate(node.data)"
            />
            <Button
              v-tooltip.top="'Изменить'"
              icon="pi pi-pencil"
              text
              rounded
              aria-label="Изменить"
              :disabled="!node.data.permissions?.update"
              @click="openEdit(node.data)"
            />
            <Button
              v-tooltip.top="'Перенести'"
              icon="pi pi-arrow-right-arrow-left"
              text
              rounded
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
  max-width: 100%;
}
.tree {
  flex: 1;
  min-height: 0;
}
.row-actions {
  display: flex;
  gap: 0.125rem;
}
.inactive {
  text-decoration: line-through;
  color: var(--p-text-muted-color);
}
</style>
