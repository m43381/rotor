<script setup lang="ts">
// Массовая выдача допусков (open-questions №16): группе людей на одну или несколько ролей.
// Кто не проходит требования роли, пропускается; им можно выдать допуск вторым шагом —
// вопреки требованиям, с обоснованием.
import Button from 'primevue/button'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import Textarea from 'primevue/textarea'
import { computed, ref, watch } from 'vue'

import { ApiError, personnel, unwrap, type BulkClearanceResult, type ClearanceRole } from '@/api/client'
import { toIso } from '@/utils/dates'

const props = defineProps<{ personIds: string[] }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ done: [granted: number] }>()

const roles = ref<ClearanceRole[]>([])
const roleIds = ref<string[]>([])
const validFrom = ref<Date | null>(null)
const validTo = ref<Date | null>(null)
const comment = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const result = ref<BulkClearanceResult | null>(null)
const granted = ref(0)

watch(visible, async (open) => {
  if (!open) return
  roleIds.value = []
  validFrom.value = null
  validTo.value = null
  comment.value = ''
  error.value = null
  result.value = null
  granted.value = 0
  try {
    roles.value = await unwrap(personnel.GET('/clearance-roles'))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось загрузить роли'
  }
})

const groups = computed(() => {
  const byType = new Map<string, { label: string; items: ClearanceRole[] }>()
  for (const r of roles.value) {
    const key = r.duty_type_id ?? r.duty_type_name
    const group = byType.get(key) ?? { label: `${r.duty_type_name} — ${r.owner_unit_name ?? ''}`, items: [] }
    group.items.push(r)
    byType.set(key, group)
  }
  return [...byType.values()]
})

const overrideCandidates = computed(() =>
  (result.value?.skipped ?? []).filter((s) => s.reason === 'Не проходит требования роли'),
)
const otherSkipped = computed(() =>
  (result.value?.skipped ?? []).filter((s) => s.reason !== 'Не проходит требования роли'),
)

async function send(override: boolean) {
  busy.value = true
  error.value = null
  try {
    const r = await unwrap(
      personnel.POST('/clearances/bulk', {
        body: {
          person_ids: props.personIds,
          duty_role_ids: roleIds.value,
          valid_from: validFrom.value ? toIso(validFrom.value) : null,
          valid_to: validTo.value ? toIso(validTo.value) : null,
          confirm_override: override,
          override_comment: override ? comment.value.trim() : null,
        },
      }),
    )
    granted.value += r.done
    // Во втором шаге «уже выдан» — это выданные на первом шаге; их не показываем повторно
    result.value = override
      ? { ...r, skipped: (r.skipped ?? []).filter((s) => s.reason !== 'Допуск уже выдан') }
      : r
    emit('done', granted.value)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось выдать допуски'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    :header="`Допуск для ${personIds.length} чел.`"
    modal
    :style="{ width: '40rem' }"
  >
    <div class="form">
      <template v-if="!result">
        <label for="bc-roles">Роли</label>
        <MultiSelect
          v-model="roleIds"
          input-id="bc-roles"
          :options="groups"
          option-group-label="label"
          option-group-children="items"
          option-label="role_name"
          option-value="duty_role_id"
          filter
          display="chip"
          placeholder="Выберите роли (можно все роли наряда)"
        />
        <div class="dates">
          <div class="field">
            <label for="bc-from">Действует с</label>
            <DatePicker v-model="validFrom" input-id="bc-from" date-format="dd.mm.yy" show-button-bar placeholder="Сразу" />
          </div>
          <div class="field">
            <label for="bc-to">по</label>
            <DatePicker v-model="validTo" input-id="bc-to" date-format="dd.mm.yy" show-button-bar placeholder="Бессрочно" />
          </div>
        </div>
      </template>

      <template v-else>
        <Message severity="success" :closable="false">Выдано допусков: {{ granted }}</Message>
        <div v-if="otherSkipped.length" class="skipped">
          <strong>Не выдано ({{ otherSkipped.length }}):</strong>
          <ul>
            <li v-for="(s, i) in otherSkipped" :key="i">
              {{ s.name ?? 'Человек' }}<template v-if="s.role_name"> — {{ s.role_name }}</template>: {{ s.reason }}
            </li>
          </ul>
        </div>
        <template v-if="overrideCandidates.length">
          <Message severity="warn" :closable="false">
            Не проходят требования роли ({{ overrideCandidates.length }}):
            <ul class="violations">
              <li v-for="(s, i) in overrideCandidates" :key="i">
                {{ s.name }} — {{ s.role_name }}: {{ (s.violations as string[] | undefined)?.join('; ') }}
              </li>
            </ul>
            Им можно выдать допуск вопреки требованиям — с обоснованием.
          </Message>
          <label for="bc-comment">Обоснование</label>
          <Textarea id="bc-comment" v-model="comment" rows="2" maxlength="2000" auto-resize />
        </template>
      </template>

      <small v-if="error" class="error">{{ error }}</small>

      <div class="actions">
        <Button :label="result ? 'Закрыть' : 'Отмена'" severity="secondary" text @click="visible = false" />
        <Button
          v-if="!result"
          label="Выдать"
          :disabled="!roleIds.length || (!!validFrom && !!validTo && validTo < validFrom)"
          :loading="busy"
          @click="send(false)"
        />
        <Button
          v-else-if="overrideCandidates.length"
          label="Выдать вопреки требованиям"
          severity="warn"
          :disabled="!comment.trim()"
          :loading="busy"
          @click="send(true)"
        />
      </div>
    </div>
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
.dates {
  display: flex;
  gap: 1rem;
}
.field {
  display: grid;
  gap: 0.35rem;
}
.skipped ul,
.violations {
  margin: 0.25rem 0 0.5rem;
  padding-left: 1.25rem;
}
.error {
  color: var(--p-red-500);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
