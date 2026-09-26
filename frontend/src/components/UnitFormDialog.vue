<script setup lang="ts">
// Создание дочернего подразделения или редактирование существующего.
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import { computed, ref, watch } from 'vue'

import type { Unit, UnitType } from '@/api/client'

const props = defineProps<{
  mode: 'create' | 'edit'
  /** create — родитель нового узла; edit — сам редактируемый узел. */
  unit: Unit | null
  types: UnitType[]
  busy: boolean
}>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{
  submit: [value: { name: string; short_name: string | null; unit_type_id: string; sort_order: number }]
}>()

const name = ref('')
const shortName = ref('')
const typeId = ref<string | null>(null)
const sortOrder = ref(0)

watch(visible, (open) => {
  if (!open) return
  if (props.mode === 'edit' && props.unit) {
    name.value = props.unit.name
    shortName.value = props.unit.short_name ?? ''
    typeId.value = props.unit.unit_type_id
    sortOrder.value = props.unit.sort_order
  } else {
    name.value = ''
    shortName.value = ''
    typeId.value = props.types[0]?.id ?? null
    sortOrder.value = 0
  }
})

const title = computed(() =>
  props.mode === 'create' ? `Новое подразделение в «${props.unit?.name ?? ''}»` : 'Изменить подразделение',
)
const valid = computed(() => name.value.trim().length > 0 && typeId.value !== null)

function submit() {
  if (!valid.value || typeId.value === null) return
  emit('submit', {
    name: name.value.trim(),
    short_name: shortName.value.trim() || null,
    unit_type_id: typeId.value,
    sort_order: sortOrder.value,
  })
}
</script>

<template>
  <Dialog v-model:visible="visible" :header="title" modal :style="{ width: '32rem' }">
    <form class="form" @submit.prevent="submit">
      <label for="unit-name">Название</label>
      <InputText id="unit-name" v-model="name" autofocus maxlength="300" />

      <label for="unit-short">Краткое название</label>
      <InputText id="unit-short" v-model="shortName" maxlength="100" />

      <label for="unit-type">Тип</label>
      <Select
        id="unit-type"
        v-model="typeId"
        :options="types"
        option-label="name"
        option-value="id"
        placeholder="Выберите тип"
        empty-message="Нет подходящих типов: нужен тип ниже по иерархии"
      />

      <label for="unit-order">Порядок в списке</label>
      <InputNumber id="unit-order" v-model="sortOrder" :min="0" :max="10000" show-buttons />

      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button type="submit" label="Сохранить" :disabled="!valid" :loading="busy" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.form {
  display: grid;
  gap: 0.5rem;
}
.form label {
  font-weight: 600;
  margin-top: 0.5rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}
</style>
