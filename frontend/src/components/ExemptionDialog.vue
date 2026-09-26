<script setup lang="ts">
// Освобождение: причина и период (даты включительно). Для одного человека или группы.
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { computed, ref, watch } from 'vue'

import type { Exemption } from '@/api/client'
import { useRefsStore } from '@/stores/refs'
import { fromIso, toIso } from '@/utils/dates'

const props = defineProps<{ title: string; exemption?: Exemption | null; busy: boolean }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{
  submit: [value: { reason_id: string; date_from: string; date_to: string; comment: string | null }]
}>()
const refs = useRefsStore()

const reasonId = ref<string | null>(null)
const range = ref<Date[] | null>(null)
const comment = ref('')

watch(visible, (open) => {
  if (!open) return
  const e = props.exemption
  reasonId.value = e?.reason_id ?? refs.activeReasons[0]?.id ?? null
  range.value = e ? [fromIso(e.date_from), fromIso(e.date_to)] : null
  comment.value = e?.comment ?? ''
})

const valid = computed(
  () => !!reasonId.value && !!range.value?.[0] && !!range.value?.[1],
)

function submit() {
  const [from, to] = range.value ?? []
  if (!reasonId.value || !from || !to) return
  emit('submit', {
    reason_id: reasonId.value,
    date_from: toIso(from),
    date_to: toIso(to),
    comment: comment.value.trim() || null,
  })
}
</script>

<template>
  <Dialog v-model:visible="visible" :header="title" modal :style="{ width: '30rem' }">
    <form class="form" @submit.prevent="submit">
      <label for="ex-reason">Причина</label>
      <Select
        id="ex-reason"
        v-model="reasonId"
        :options="refs.activeReasons"
        option-label="name"
        option-value="id"
      />
      <label for="ex-range">Период (включительно)</label>
      <DatePicker
        v-model="range"
        input-id="ex-range"
        selection-mode="range"
        date-format="dd.mm.yy"
        placeholder="С — по"
        show-button-bar
      />
      <label for="ex-comment">Комментарий</label>
      <Textarea id="ex-comment" v-model="comment" rows="2" maxlength="2000" auto-resize />
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
