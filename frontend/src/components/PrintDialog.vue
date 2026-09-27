<script setup lang="ts">
// Печать (фаза 6b): график на месяц (PDF, XLSX) или суточный наряд подразделения и его
// поддерева на дату — ведомость или приказ (PDF, DOCX). Реквизиты — со страницы «Документы».
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import RadioButton from 'primevue/radiobutton'
import SelectButton from 'primevue/selectbutton'
import { computed, ref, watch } from 'vue'

import { ApiError, documents, saveFile } from '@/api/client'
import { fromIso, toIso } from '@/utils/dates'

const props = defineProps<{
  scheduleId: string
  unitId: string
  // Первый день месяца графика, YYYY-MM-DD
  month: string
  status: string
}>()
const visible = defineModel<boolean>('visible', { required: true })

type FormCode = 'schedule_month' | 'daily_roster' | 'daily_order'
const FORMS: { value: FormCode; label: string; formats: string[] }[] = [
  { value: 'schedule_month', label: 'График нарядов на месяц', formats: ['pdf', 'xlsx'] },
  { value: 'daily_roster', label: 'Ведомость суточного наряда на дату', formats: ['pdf', 'docx'] },
  { value: 'daily_order', label: 'Приказ о назначении суточного наряда', formats: ['pdf', 'docx'] },
]
const FORMAT_LABELS: Record<string, string> = { pdf: 'PDF', xlsx: 'Excel (XLSX)', docx: 'Word (DOCX)' }

const form = ref<FormCode>('schedule_month')
const format = ref('pdf')
const date = ref<Date>(new Date())
const busy = ref(false)
const error = ref<string | null>(null)

const formats = computed(() =>
  (FORMS.find((f) => f.value === form.value)?.formats ?? []).map((f) => ({ value: f, label: FORMAT_LABELS[f] })),
)
const daily = computed(() => form.value !== 'schedule_month')
const monthStart = computed(() => fromIso(props.month))
const monthEnd = computed(() => new Date(monthStart.value.getFullYear(), monthStart.value.getMonth() + 1, 0))

watch(form, () => {
  if (!formats.value.some((f) => f.value === format.value)) format.value = 'pdf'
})
watch(visible, (open) => {
  if (!open) return
  error.value = null
  // По умолчанию — сегодня, если он в месяце графика, иначе первое число
  const today = new Date()
  date.value = today >= monthStart.value && today <= monthEnd.value ? today : monthStart.value
})

async function download() {
  busy.value = true
  error.value = null
  try {
    if (form.value === 'schedule_month') {
      await saveFile(
        documents.GET('/print/schedules/{schedule_id}', {
          params: { path: { schedule_id: props.scheduleId }, query: { format: format.value as 'pdf' | 'xlsx' } },
          parseAs: 'blob',
        }),
        `schedule.${format.value}`,
      )
    } else {
      await saveFile(
        documents.GET('/print/daily', {
          params: {
            query: {
              unit_id: props.unitId,
              date: toIso(date.value),
              form: form.value,
              format: format.value as 'pdf' | 'docx',
            },
          },
          parseAs: 'blob',
        }),
        `daily.${format.value}`,
      )
    }
    visible.value = false
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось подготовить документ'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" header="Печать" modal :style="{ width: '34rem' }">
    <div class="form">
      <fieldset>
        <legend>Документ</legend>
        <label v-for="f in FORMS" :key="f.value" class="radio">
          <RadioButton v-model="form" :value="f.value" :input-id="`print-${f.value}`" />
          <span>{{ f.label }}</span>
        </label>
      </fieldset>
      <fieldset v-if="daily">
        <legend>Дата заступления</legend>
        <DatePicker v-model="date" date-format="dd.mm.yy" input-id="print-date" show-icon />
        <small class="muted">Наряды подразделения графика и всех нижестоящих на эту дату.</small>
      </fieldset>
      <fieldset>
        <legend>Формат</legend>
        <SelectButton v-model="format" :options="formats" option-label="label" option-value="value" :allow-empty="false" />
      </fieldset>
      <Message v-if="status === 'draft'" severity="warn" :closable="false">
        График не опубликован: документ будет с пометкой «ПРОЕКТ» и без грифа «УТВЕРЖДАЮ».
      </Message>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button label="Скачать" icon="pi pi-download" :loading="busy" @click="download" />
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.form {
  display: grid;
  gap: 0.9rem;
}
fieldset {
  border: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.4rem;
}
legend {
  font-weight: 600;
  margin-bottom: 0.25rem;
}
.radio {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.muted {
  color: var(--p-text-muted-color);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
