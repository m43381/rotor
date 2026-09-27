<script setup lang="ts">
// Тип наряда: владелец, шаблон времени (начало + длительность, ADR-0008), отдых, вес нагрузки.
// При создании сразу задаётся состав по ролям; требования ролей настраиваются после.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import { computed, ref, watch } from 'vue'

import type { DutyType, DutyTypeCreate, DutyTypeUpdate, Unit } from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { formatDuration, formatInterval } from '@/utils/duty'

const props = defineProps<{ dutyType?: DutyType | null; busy: boolean; defaultOwnerId?: string | null }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{
  create: [value: DutyTypeCreate]
  update: [value: DutyTypeUpdate]
}>()
const units = useUnitsStore()

const name = ref('')
const shortName = ref('')
const ownerId = ref<string | null>(null)
const assignedId = ref<string | null>(null)
const start = ref<Date | null>(null)
const hours = ref(24)
const minutes = ref(0)
const restHours = ref(48)
const loadWeight = ref(1)
const active = ref(true)
const roles = ref<{ name: string; headcount: number }[]>([])

watch(visible, (open) => {
  if (!open) return
  const t = props.dutyType
  name.value = t?.name ?? ''
  shortName.value = t?.short_name ?? ''
  ownerId.value = t?.owner_unit_id ?? props.defaultOwnerId ?? null
  assignedId.value = t?.assigned_unit_id ?? null
  const [h = 18, m = 0] = (t?.start_time ?? '18:00').split(':').map(Number)
  start.value = new Date(2000, 0, 1, h, m)
  hours.value = Math.floor((t?.duration_minutes ?? 1440) / 60)
  minutes.value = (t?.duration_minutes ?? 1440) % 60
  restHours.value = t?.rest_hours ?? 48
  loadWeight.value = t?.load_weight ?? 1
  active.value = t?.is_active ?? true
  roles.value = [{ name: 'Дежурный', headcount: 1 }]
})

const owner = computed(() => (ownerId.value ? units.byId.get(ownerId.value) : undefined))
const canOwn = (u: Unit) => u.is_active && u.permissions?.create_child !== false
// Закреплённое подразделение — внутри поддерева владельца (сам владелец или ниже)
const insideOwner = (u: Unit) =>
  !!owner.value && u.is_active && (u.path === owner.value.path || u.path.startsWith(`${owner.value.path}.`))
watch(ownerId, () => {
  const a = assignedId.value ? units.byId.get(assignedId.value) : undefined
  if (a && !insideOwner(a)) assignedId.value = null
})

const startTime = computed(() => {
  const d = start.value
  return d ? `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : ''
})
const duration = computed(() => (hours.value || 0) * 60 + (minutes.value || 0))
const durationOk = computed(() => duration.value >= 60 && duration.value <= 7 * 24 * 60)
const valid = computed(
  () =>
    name.value.trim().length > 0 &&
    !!ownerId.value &&
    !!start.value &&
    durationOk.value &&
    (props.dutyType ? true : roles.value.length > 0 && roles.value.every((r) => r.name.trim())),
)

function submit() {
  if (!valid.value || !ownerId.value) return
  const base = {
    name: name.value.trim(),
    short_name: shortName.value.trim() || null,
    assigned_unit_id: assignedId.value,
    start_time: startTime.value,
    duration_minutes: duration.value,
    rest_hours: restHours.value,
    load_weight: loadWeight.value,
  }
  const t = props.dutyType
  if (t) {
    emit('update', { ...base, version: t.version, is_active: active.value })
  } else {
    emit('create', {
      ...base,
      owner_unit_id: ownerId.value,
      roles: roles.value.map((r, i) => ({
        name: r.name.trim(),
        headcount: r.headcount,
        sort_order: i,
        is_active: true,
      })),
    })
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    :header="dutyType ? 'Изменить наряд' : 'Новый наряд'"
    modal
    :style="{ width: '42rem' }"
  >
    <form class="form" @submit.prevent="submit">
      <div class="row">
        <div class="field grow">
          <label for="dt-name">Название</label>
          <InputText id="dt-name" v-model="name" maxlength="200" placeholder="Например, суточный наряд по курсу" />
        </div>
        <div class="field">
          <label for="dt-short">Сокращение</label>
          <InputText id="dt-short" v-model="shortName" maxlength="50" class="short" />
        </div>
      </div>
      <div class="row">
        <div class="field grow">
          <label for="dt-owner">Подразделение-владелец</label>
          <UnitTreeSelect
            v-if="!dutyType"
            v-model="ownerId"
            input-id="dt-owner"
            :selectable="canOwn"
            placeholder="Чей наряд"
          />
          <InputText v-else id="dt-owner" :model-value="dutyType.owner_unit_name ?? ''" disabled />
        </div>
        <div class="field grow">
          <label for="dt-assigned">Закреплён за (необязательно)</label>
          <UnitTreeSelect
            v-model="assignedId"
            input-id="dt-assigned"
            :selectable="insideOwner"
            placeholder="Не закреплён"
            show-clear
          />
        </div>
      </div>

      <div class="row">
        <div class="field">
          <label for="dt-start">Начало</label>
          <DatePicker v-model="start" input-id="dt-start" time-only hour-format="24" :step-minute="5" class="time" />
        </div>
        <div class="field">
          <label for="dt-hours">Длительность</label>
          <div class="duration">
            <InputNumber v-model="hours" input-id="dt-hours" :min="0" :max="168" suffix=" ч" class="num" />
            <InputNumber v-model="minutes" :min="0" :max="59" :step="5" suffix=" мин" class="num" aria-label="Минуты" />
          </div>
        </div>
        <div class="field">
          <label for="dt-rest">Отдых после, ч</label>
          <InputNumber v-model="restHours" input-id="dt-rest" :min="0" :max="720" class="num" />
        </div>
        <div class="field">
          <label for="dt-weight">Вес нагрузки</label>
          <InputNumber
            v-model="loadWeight"
            input-id="dt-weight"
            :min="0.1"
            :max="99"
            :min-fraction-digits="1"
            :max-fraction-digits="2"
            class="num"
          />
        </div>
      </div>
      <p class="hint" :class="{ error: !durationOk }">
        <template v-if="durationOk && start">
          {{ formatInterval(startTime, duration) }} · {{ formatDuration(duration) }}. Наряд занимает все
          сутки, которые пересекает; в одни сутки — не больше одного наряда.
        </template>
        <template v-else>Длительность — от 1 часа до 7 суток.</template>
      </p>

      <template v-if="!dutyType">
        <h4>Состав по ролям</h4>
        <div v-for="(r, i) in roles" :key="i" class="role-row">
          <InputText v-model="r.name" maxlength="200" placeholder="Роль" :aria-label="`Роль ${i + 1}`" class="grow" />
          <InputNumber
            v-model="r.headcount"
            :min="1"
            :max="100"
            suffix=" чел."
            class="num"
            :aria-label="`Численность роли ${i + 1}`"
          />
          <Button
            icon="pi pi-times"
            text
            rounded
            severity="secondary"
            aria-label="Убрать роль"
            :disabled="roles.length === 1"
            @click="roles.splice(i, 1)"
          />
        </div>
        <div>
          <Button
            label="Добавить роль"
            icon="pi pi-plus"
            text
            size="small"
            @click="roles.push({ name: '', headcount: 1 })"
          />
        </div>
        <p class="hint">Требования к званию, должности и характеристикам задаются у каждой роли после создания.</p>
      </template>
      <label v-else class="check">
        <Checkbox v-model="active" binary input-id="dt-active" />
        <span>Наряд действует</span>
      </label>

      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button type="submit" :label="dutyType ? 'Сохранить' : 'Создать'" :disabled="!valid" :loading="busy" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.form {
  display: grid;
  gap: 0.75rem;
}
.row {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}
.field {
  display: grid;
  gap: 0.35rem;
  align-content: start;
}
.field label {
  font-weight: 600;
}
.grow {
  flex: 1;
  min-width: 14rem;
}
.short {
  width: 9rem;
}
.time {
  width: 7rem;
}
.num :deep(input) {
  width: 7rem;
}
.duration {
  display: flex;
  gap: 0.5rem;
}
.hint {
  margin: 0;
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
}
.hint.error {
  color: var(--p-red-500);
}
h4 {
  margin: 0.5rem 0 0;
}
.role-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
