// Дерево подразделений в пределах scope оператора и операции над ним.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { org, unwrap, type Me, type Unit, type UnitCreate, type UnitType } from '@/api/client'
import { buildTree } from '@/utils/tree'

export const useUnitsStore = defineStore('units', () => {
  const me = ref<Me | null>(null)
  const units = ref<Unit[]>([])
  const types = ref<UnitType[]>([])
  const loading = ref(false)
  // Расформированные показывает только экран структуры (суперадминистратору, ADR-0023)
  const includeInactive = ref(false)

  const tree = computed(() => buildTree(units.value))
  const byId = computed(() => new Map(units.value.map((u) => [u.id, u])))
  const typeById = computed(() => new Map(types.value.map((t) => [t.id, t])))

  async function load(): Promise<void> {
    loading.value = true
    try {
      const [meData, unitList, typeList] = await Promise.all([
        unwrap(org.GET('/me')),
        unwrap(org.GET('/units', { params: { query: { include_inactive: includeInactive.value } } })),
        unwrap(org.GET('/unit-types')),
      ])
      me.value = meData
      units.value = unitList
      types.value = typeList
    } finally {
      loading.value = false
    }
  }

  /** Типы, допустимые для дочернего узла: уровнем ниже родителя (правило сервиса org). */
  function childTypes(parent: Unit): UnitType[] {
    const parentLevel = typeById.value.get(parent.unit_type_id)?.level ?? -1
    return types.value.filter((t) => t.level > parentLevel)
  }

  async function create(body: UnitCreate): Promise<Unit> {
    const unit = await unwrap(org.POST('/units', { body }))
    await load()
    return unit
  }

  async function update(
    unit: Unit,
    changes: { name?: string; short_name?: string | null; unit_type_id?: string; sort_order?: number },
  ): Promise<void> {
    await unwrap(
      org.PATCH('/units/{unit_id}', {
        params: { path: { unit_id: unit.id } },
        body: { ...changes, version: unit.version },
      }),
    )
    await load()
  }

  async function move(unit: Unit, newParentId: string): Promise<void> {
    await unwrap(
      org.POST('/units/{unit_id}/move', {
        params: { path: { unit_id: unit.id } },
        body: { new_parent_id: newParentId, version: unit.version },
      }),
    )
    await load()
  }

  async function deactivate(unit: Unit): Promise<void> {
    await unwrap(
      org.DELETE('/units/{unit_id}', {
        params: { path: { unit_id: unit.id }, query: { version: unit.version } },
      }),
    )
    await load()
  }

  async function restore(unit: Unit): Promise<void> {
    await unwrap(
      org.POST('/units/{unit_id}/restore', {
        params: { path: { unit_id: unit.id }, query: { version: unit.version } },
      }),
    )
    await load()
  }

  /** Удалить навсегда: сервер откажет, если на подразделение что-то ссылается. */
  async function purge(unit: Unit): Promise<void> {
    await unwrap(
      org.POST('/units/{unit_id}/purge', {
        params: { path: { unit_id: unit.id }, query: { version: unit.version } },
      }),
    )
    await load()
  }

  return {
    me,
    units,
    types,
    loading,
    includeInactive,
    tree,
    byId,
    typeById,
    load,
    childTypes,
    create,
    update,
    move,
    deactivate,
    restore,
    purge,
  }
})
