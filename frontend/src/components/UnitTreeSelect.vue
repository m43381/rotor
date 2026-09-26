<script setup lang="ts">
// Выбор подразделения деревом (подразделения в scope оператора из стора units).
import type { TreeNode as PrimeTreeNode } from 'primevue/treenode'
import TreeSelect from 'primevue/treeselect'
import { computed } from 'vue'

import type { Unit } from '@/api/client'
import { useUnitsStore } from '@/stores/units'
import { expandedKeys, type TreeNode } from '@/utils/tree'

const props = withDefaults(
  defineProps<{
    placeholder?: string
    /** Какие узлы можно выбрать (остальные видны, но приглушены). */
    selectable?: (unit: Unit) => boolean
    showClear?: boolean
    inputId?: string
  }>(),
  { placeholder: 'Подразделение', selectable: undefined, showClear: false, inputId: undefined },
)
const model = defineModel<string | null>({ required: true })
const store = useUnitsStore()

const options = computed(() => {
  const convert = (n: TreeNode<Unit>): PrimeTreeNode => {
    const ok = props.selectable ? props.selectable(n.data) : true
    return {
      key: n.key,
      label: n.data.name,
      selectable: ok,
      styleClass: ok ? undefined : 'move-target-disabled',
      children: n.children.map(convert),
    }
  }
  return store.tree.map(convert)
})
const expanded = computed(() => expandedKeys(store.tree, 2))

// TreeSelect хранит выбор как {key: true}; наружу отдаём просто id.
const selection = computed({
  get: () => (model.value ? { [model.value]: true } : null),
  set: (value: Record<string, boolean> | null) => {
    model.value = Object.keys(value ?? {})[0] ?? null
  },
})
</script>

<template>
  <TreeSelect
    v-model="selection"
    :input-id="inputId"
    :options="options"
    :expanded-keys="expanded"
    selection-mode="single"
    :placeholder="placeholder"
    :show-clear="showClear"
    filter
    fluid
  />
</template>
