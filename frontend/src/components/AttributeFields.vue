<script setup lang="ts">
// Поля расширяемых характеристик: вид поля — по типу определения (ADR-0005).
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'

import type { AttributeDefinition } from '@/api/client'
import { fromIso, toIso } from '@/utils/dates'

defineProps<{ definitions: AttributeDefinition[]; disabled?: boolean }>()
const values = defineModel<Record<string, unknown>>({ required: true })

function set(code: string, value: unknown) {
  values.value = { ...values.value, [code]: value === '' || value === undefined ? null : value }
}
function dateValue(code: string): Date | null {
  const v = values.value[code]
  return typeof v === 'string' ? fromIso(v) : null
}
</script>

<template>
  <div class="attrs">
    <div v-for="d in definitions" :key="d.id" class="attr">
      <label :for="`attr-${d.code}`">{{ d.name }}<span v-if="d.is_required" class="req"> *</span></label>
      <Checkbox
        v-if="d.value_type === 'bool'"
        :input-id="`attr-${d.code}`"
        binary
        :model-value="values[d.code] === true"
        :disabled="disabled"
        @update:model-value="set(d.code, $event)"
      />
      <InputNumber
        v-else-if="d.value_type === 'int'"
        :input-id="`attr-${d.code}`"
        :model-value="(values[d.code] as number | null) ?? null"
        :disabled="disabled"
        :use-grouping="false"
        @update:model-value="set(d.code, $event)"
      />
      <Select
        v-else-if="d.value_type === 'enum'"
        :input-id="`attr-${d.code}`"
        :model-value="values[d.code] ?? null"
        :options="d.enum_options ?? []"
        :disabled="disabled"
        show-clear
        placeholder="Не указано"
        @update:model-value="set(d.code, $event)"
      />
      <DatePicker
        v-else-if="d.value_type === 'date'"
        :input-id="`attr-${d.code}`"
        :model-value="dateValue(d.code)"
        date-format="dd.mm.yy"
        :disabled="disabled"
        show-button-bar
        @update:model-value="set(d.code, $event instanceof Date ? toIso($event) : null)"
      />
      <InputText
        v-else
        :id="`attr-${d.code}`"
        :model-value="(values[d.code] as string | null) ?? ''"
        :disabled="disabled"
        maxlength="500"
        @update:model-value="set(d.code, $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.attrs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr));
  gap: 0.75rem 1rem;
}
.attr {
  display: grid;
  gap: 0.35rem;
}
.attr label {
  font-weight: 600;
}
.req {
  color: var(--p-red-500);
}
</style>
