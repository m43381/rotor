<script setup lang="ts">
// Перенос подразделения (вместе с поддеревом) к новому родителю.
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import type { TreeNode as PrimeTreeNode } from 'primevue/treenode'
import TreeSelect from 'primevue/treeselect'
import { computed, ref, watch } from 'vue'

import type { Unit } from '@/api/client'
import { buildTree, expandedKeys, subtreeIds } from '@/utils/tree'

const props = defineProps<{
  unit: Unit | null
  units: Unit[]
  busy: boolean
  /** Может ли узел быть новым родителем по иерархии типов (уровень родителя выше). */
  canParent: (parent: Unit, child: Unit) => boolean
}>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ submit: [newParentId: string] }>()

const selection = ref<Record<string, boolean> | null>(null)
watch(visible, (open) => {
  if (open) selection.value = null
})

// Кандидаты: куда оператор может добавлять дочерние и куда узел проходит по иерархии типов,
// кроме самого узла, его поддерева и текущего родителя. Недоступные узлы остаются в дереве
// для ориентации, но приглушены и не выбираются.
const options = computed(() => {
  if (!props.unit) return []
  const excluded = subtreeIds(props.units, props.unit.id)
  const tree = buildTree(props.units)
  type Node = (typeof tree)[number]
  const moving = props.unit
  const convert = (n: Node): PrimeTreeNode => {
    const selectable =
      !excluded.has(n.key) &&
      n.key !== moving.parent_id &&
      n.data.permissions?.create_child === true &&
      props.canParent(n.data, moving)
    return {
      key: n.key,
      label: n.data.name,
      selectable,
      styleClass: selectable ? undefined : 'move-target-disabled',
      children: n.children.filter((c) => !excluded.has(c.key)).map(convert),
    }
  }
  return tree.map(convert)
})
const expanded = computed(() => expandedKeys(buildTree(props.units), 2))
const targetId = computed(() => Object.keys(selection.value ?? {})[0] ?? null)

function submit() {
  if (targetId.value) emit('submit', targetId.value)
}
</script>

<template>
  <Dialog v-model:visible="visible" :header="`Перенести «${unit?.name ?? ''}»`" modal :style="{ width: '34rem' }">
    <div class="body">
      <Message severity="info" :closable="false">
        Подразделение переносится вместе со всеми дочерними.
      </Message>
      <label for="move-target">Новое вышестоящее подразделение</label>
      <TreeSelect
        v-model="selection"
        input-id="move-target"
        :options="options"
        :expanded-keys="expanded"
        selection-mode="single"
        placeholder="Выберите подразделение"
        filter
        fluid
      />
      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button label="Перенести" :disabled="!targetId" :loading="busy" @click="submit" />
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.body {
  display: grid;
  gap: 0.75rem;
}
.body label {
  font-weight: 600;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
