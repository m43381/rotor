<script setup lang="ts">
// Производственный календарь (org): хранятся только исключения из обычной недели — праздники,
// рабочие переносы на выходные и предпраздничные дни. Выходные/будни считаются сами.
// Влияет на наряды в праздники и лимиты праздничных нарядов (open-questions №9).
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'

import { ApiError, org, unwrap } from '@/api/client'
import { formatDate, fromIso, toIso } from '@/utils/dates'

type DayKind = 'holiday' | 'workday' | 'preholiday'
interface CalendarDay {
  date: string
  kind: DayKind
  name?: string | null
}

const KINDS: { value: DayKind; label: string; severity: string }[] = [
  { value: 'holiday', label: 'Праздничный (нерабочий)', severity: 'danger' },
  { value: 'workday', label: 'Рабочий (перенос на выходной)', severity: 'info' },
  { value: 'preholiday', label: 'Предпраздничный (сокращённый)', severity: 'warn' },
]
const kindOf = (k: DayKind) => KINDS.find((x) => x.value === k) ?? KINDS[0]!
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']

const toast = useToast()
const confirm = useConfirm()
const year = ref(new Date().getFullYear())
const days = ref<CalendarDay[]>([])
const loading = ref(false)

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

async function load() {
  loading.value = true
  try {
    const query = { date_from: `${year.value}-01-01`, date_to: `${year.value}-12-31` }
    days.value = await unwrap(org.GET('/calendar', { params: { query } }))
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(year, load)

const counts = computed(() => ({
  holiday: days.value.filter((d) => d.kind === 'holiday').length,
  workday: days.value.filter((d) => d.kind === 'workday').length,
}))

// --- добавление и изменение дня --------------------------------------------------------------------
const visible = ref(false)
const editing = ref(false)
const form = ref<{ date: Date | null; kind: DayKind; name: string }>({ date: null, kind: 'holiday', name: '' })
const busy = ref(false)

function open(day?: CalendarDay) {
  editing.value = !!day
  form.value = day
    ? { date: fromIso(day.date), kind: day.kind, name: day.name ?? '' }
    : { date: new Date(year.value, 0, 1), kind: 'holiday', name: '' }
  visible.value = true
}

async function save() {
  if (!form.value.date) return
  const day = toIso(form.value.date)
  busy.value = true
  try {
    const body = { date: day, kind: form.value.kind, name: form.value.name.trim() || null }
    await unwrap(org.PUT('/calendar/{day}', { params: { path: { day } }, body }))
    visible.value = false
    if (form.value.date.getFullYear() !== year.value) year.value = form.value.date.getFullYear()
    else await load()
    toast.add({ severity: 'success', summary: 'Сохранено', life: 3000 })
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

function remove(day: CalendarDay) {
  confirm.require({
    header: 'Убрать день из календаря?',
    message: `${formatDate(day.date)} станет обычным днём недели.`,
    icon: 'pi pi-trash',
    acceptProps: { label: 'Убрать', severity: 'danger' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: async () => {
      try {
        await unwrap(org.DELETE('/calendar/{day}', { params: { path: { day: day.date } } }))
        await load()
      } catch (e) {
        showError(e)
      }
    },
  })
}
</script>

<template>
  <p class="hint-box">
    <i class="pi pi-info-circle" />
    <span>
      Указываются только отличия от обычной недели: праздники, рабочие дни, перенесённые на выходные,
      и предпраздничные дни. Праздники учитываются в лимитах праздничных нарядов и в аналитике.
    </span>
  </p>
  <div class="toolbar">
    <label for="cal-year">Год</label>
    <InputNumber id="cal-year" v-model="year" :min="2000" :max="2100" :use-grouping="false" show-buttons input-class="year" />
    <span class="muted">праздников: {{ counts.holiday }}, рабочих переносов: {{ counts.workday }}</span>
    <Button label="Добавить день" icon="pi pi-plus" class="push" @click="open()" />
  </div>
  <DataTable :value="days" data-key="date" :loading="loading">
    <template #empty>За {{ year }} год исключений нет — все дни считаются по обычной неделе.</template>
    <Column header="Дата" style="width: 12rem">
      <template #body="{ data }">
        {{ formatDate(data.date) }} <span class="muted">{{ WEEKDAYS[fromIso(data.date).getDay()] }}</span>
      </template>
    </Column>
    <Column header="Вид" style="width: 18rem">
      <template #body="{ data }">
        <Tag :value="kindOf(data.kind).label" :severity="kindOf(data.kind).severity" />
      </template>
    </Column>
    <Column field="name" header="Название" />
    <Column style="width: 7rem">
      <template #body="{ data }">
        <Button icon="pi pi-pencil" text rounded aria-label="Изменить" @click="open(data)" />
        <Button icon="pi pi-trash" text rounded severity="danger" aria-label="Убрать" @click="remove(data)" />
      </template>
    </Column>
  </DataTable>

  <Dialog v-model:visible="visible" :header="editing ? 'Изменить день' : 'Добавить день'" modal :style="{ width: '28rem' }">
    <form class="form" @submit.prevent="save">
      <label for="cal-date">Дата</label>
      <DatePicker v-model="form.date" input-id="cal-date" date-format="dd.mm.yy" :disabled="editing" />
      <label for="cal-kind">Вид дня</label>
      <Select id="cal-kind" v-model="form.kind" :options="KINDS" option-label="label" option-value="value" />
      <label for="cal-name">Название (необязательно)</label>
      <InputText id="cal-name" v-model="form.name" maxlength="200" placeholder="Например, День Победы" />
      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button type="submit" label="Сохранить" :disabled="!form.date" :loading="busy" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.hint-box {
  margin: 0 0 0.75rem;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.toolbar :deep(.year) {
  width: 6rem;
}
.push {
  margin-left: auto;
}
.muted {
  color: var(--p-text-muted-color);
}
.form {
  display: grid;
  gap: 0.5rem;
}
.form label {
  font-weight: 600;
  margin-top: 0.4rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}
</style>
