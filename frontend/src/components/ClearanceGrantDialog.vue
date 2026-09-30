<script setup lang="ts">
// Выдача допуска человеку на роль наряда (ADR-0009). Сразу видно, проходит ли человек
// требования роли; если нет — допуск можно выдать с обязательным обоснованием (попадает в аудит).
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { computed, ref, watch } from 'vue'

import { personnel, unwrap, type ClearanceOption } from '@/api/client'
import { toIso } from '@/utils/dates'

const props = defineProps<{ personId: string; busy: boolean }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{
  submit: [
    value: {
      duty_role_id: string
      valid_from: string | null
      valid_to: string | null
      confirm_override: boolean
      override_comment: string | null
    },
  ]
  error: [e: unknown]
}>()

const options = ref<ClearanceOption[]>([])
const loading = ref(false)
const roleId = ref<string | null>(null)
const validFrom = ref<Date | null>(null)
const validTo = ref<Date | null>(null)
const comment = ref('')

watch(visible, async (open) => {
  if (!open) return
  roleId.value = null
  validFrom.value = null
  validTo.value = null
  comment.value = ''
  loading.value = true
  try {
    options.value = await unwrap(
      personnel.GET('/people/{person_id}/clearance-options', {
        params: { path: { person_id: props.personId } },
      }),
    )
  } catch (e) {
    emit('error', e)
  } finally {
    loading.value = false
  }
})

// Категория — строгое условие (ADR-0018): такой допуск не выдаётся даже с обоснованием
const blockedBy = (o: ClearanceOption) => o.violations.find((v) => v.hard)

// Роли сгруппированы по нарядам; уже выданные и недоступные по категории — не выбрать
const groups = computed(() => {
  const byType = new Map<string, { label: string; items: (ClearanceOption & { label: string; disabled: boolean })[] }>()
  for (const o of options.value) {
    const key = o.duty_type_id ?? o.duty_type_name
    const group = byType.get(key) ?? { label: `${o.duty_type_name} — ${o.owner_unit_name ?? ''}`, items: [] }
    group.items.push({ ...o, label: o.role_name, disabled: o.granted || !!blockedBy(o) })
    byType.set(key, group)
  }
  return [...byType.values()]
})
const selected = computed(() => options.value.find((o) => o.duty_role_id === roleId.value))
const needsOverride = computed(() => (selected.value?.violations.length ?? 0) > 0)
const datesOk = computed(() => !validFrom.value || !validTo.value || validTo.value >= validFrom.value)
const valid = computed(
  () => !!selected.value && datesOk.value && (!needsOverride.value || comment.value.trim().length > 0),
)

function submit() {
  if (!valid.value || !roleId.value) return
  emit('submit', {
    duty_role_id: roleId.value,
    valid_from: validFrom.value ? toIso(validFrom.value) : null,
    valid_to: validTo.value ? toIso(validTo.value) : null,
    confirm_override: needsOverride.value,
    override_comment: needsOverride.value ? comment.value.trim() : null,
  })
}
</script>

<template>
  <Dialog v-model:visible="visible" header="Выдать допуск" modal :style="{ width: '36rem' }">
    <form class="form" @submit.prevent="submit">
      <label for="cl-role">Роль наряда</label>
      <Select
        v-model="roleId"
        input-id="cl-role"
        :options="groups"
        option-group-label="label"
        option-group-children="items"
        option-label="label"
        option-value="duty_role_id"
        option-disabled="disabled"
        :loading="loading"
        filter
        placeholder="Выберите роль"
        empty-message="Нет нарядов, которые касаются подразделения человека"
      >
        <template #option="{ option }">
          <span class="opt">
            <span>{{ option.label }}</span>
            <small v-if="option.granted" class="muted">уже выдан</small>
            <small v-else-if="blockedBy(option)" class="muted" :title="blockedBy(option)?.message">
              <i class="pi pi-lock" /> другая категория
            </small>
            <small v-else-if="option.assigned_unit_name" class="muted">
              <i class="pi pi-map-marker" /> {{ option.assigned_unit_name }}
            </small>
            <i
              v-else-if="option.violations.length"
              class="pi pi-exclamation-triangle warn"
              title="Не проходит требования роли"
            />
            <i v-else-if="option.has_requirements" class="pi pi-check ok" title="Проходит требования" />
          </span>
        </template>
      </Select>

      <div class="dates">
        <div class="field">
          <label for="cl-from">Действует с</label>
          <DatePicker v-model="validFrom" input-id="cl-from" date-format="dd.mm.yy" show-button-bar placeholder="Сразу" />
        </div>
        <div class="field">
          <label for="cl-to">по</label>
          <DatePicker v-model="validTo" input-id="cl-to" date-format="dd.mm.yy" show-button-bar placeholder="Бессрочно" />
        </div>
      </div>
      <small v-if="!datesOk" class="error">Дата окончания раньше даты начала</small>

      <template v-if="needsOverride && selected">
        <Message severity="warn" :closable="false">
          <div>Человек не проходит требования роли:</div>
          <ul class="violations">
            <li v-for="v in selected.violations" :key="v.message">{{ v.message }}</li>
          </ul>
          <div>Допуск можно выдать вопреки требованиям — с обоснованием. Он будет действовать как обычный и попадёт в отчёт о несоответствиях.</div>
        </Message>
        <label for="cl-comment">Обоснование (обязательно)</label>
        <Textarea
          id="cl-comment"
          v-model="comment"
          rows="2"
          maxlength="2000"
          auto-resize
          placeholder="Например, приказ начальника факультета № …"
        />
      </template>

      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button
          type="submit"
          :label="needsOverride ? 'Выдать вопреки требованиям' : 'Выдать'"
          :severity="needsOverride ? 'warn' : undefined"
          :disabled="!valid"
          :loading="busy"
        />
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
  margin-top: 0.25rem;
}
.opt {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  width: 100%;
}
.opt > span {
  flex: 1;
}
.muted {
  color: var(--p-text-muted-color);
}
.warn {
  color: var(--p-orange-500);
}
.ok {
  color: var(--p-green-500);
}
.error {
  color: var(--p-red-500);
}
.dates {
  display: flex;
  gap: 1rem;
}
.field {
  display: grid;
  gap: 0.35rem;
}
.violations {
  margin: 0.25rem 0 0.5rem;
  padding-left: 1.25rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
