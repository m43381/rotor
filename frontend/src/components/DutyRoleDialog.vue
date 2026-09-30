<script setup lang="ts">
// Роль наряда: название, численность, кто заступает (закрепление за подразделением и категории
// личного состава, ADR-0018) и дополнительные требования к человеку (ADR-0009). Требования
// проверяются при выдаче допуска; движок распределения их не видит.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import DatePicker from 'primevue/datepicker'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import MultiSelect from 'primevue/multiselect'
import Select from 'primevue/select'
import { computed, ref, watch } from 'vue'

import type { AttributeRequirement, DutyRole, DutyRoleIn, Unit } from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'
import { fromIso, toIso } from '@/utils/dates'
import { defaultRequirement, OPS, opsFor } from '@/utils/duty'

const props = defineProps<{
  role?: DutyRole | null
  busy: boolean
  title: string
  /** Владелец наряда: закрепить роль можно за ним или нижестоящим подразделением */
  ownerUnitId?: string | null
}>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ submit: [value: DutyRoleIn] }>()
const refs = useRefsStore()
const units = useUnitsStore()

const name = ref('')
const headcount = ref(1)
const weight = ref(1)
const minRank = ref<number | null>(null)
const positions = ref<string[]>([])
const assignedId = ref<string | null>(null)
const categories = ref<string[]>([])
const requirements = ref<AttributeRequirement[]>([])
const active = ref(true)

watch(visible, (open) => {
  if (!open) return
  const r = props.role
  name.value = r?.name ?? ''
  headcount.value = r?.headcount ?? 1
  weight.value = r?.load_weight ?? 1
  minRank.value = r?.min_rank_order ?? null
  positions.value = [...(r?.allowed_position_ids ?? [])]
  assignedId.value = r?.assigned_unit_id ?? null
  categories.value = [...(r?.allowed_category_ids ?? [])]
  requirements.value = (r?.attribute_requirements ?? []).map((x) => ({ ...x }))
  active.value = r?.is_active ?? true
})

const owner = computed(() => (props.ownerUnitId ? units.byId.get(props.ownerUnitId) : undefined))
const insideOwner = (u: Unit) =>
  !!owner.value && u.is_active && (u.path === owner.value.path || u.path.startsWith(`${owner.value.path}.`))
const assigned = computed(() => (assignedId.value ? units.byId.get(assignedId.value) : undefined))
const categoryOptions = computed(() =>
  refs.categories.filter((c) => c.is_active || categories.value.includes(c.id)),
)

// Звания по старшинству; требование хранит порядок звания (`rank.order`).
const rankOptions = computed(() =>
  [...refs.activeRanks].sort((a, b) => a.order - b.order).map((r) => ({ label: r.name, value: r.order })),
)
// Характеристики, которые ещё не заняты требованием этой роли
const freeAttributes = computed(() =>
  refs.activeAttributes.filter((a) => !requirements.value.some((r) => r.code === a.code)),
)
const defOf = (code: string) => refs.attributes.find((a) => a.code === code)

function addRequirement() {
  const def = freeAttributes.value[0]
  if (def) requirements.value.push(defaultRequirement(def))
}

function changeAttribute(index: number, code: string) {
  const def = defOf(code)
  if (def) requirements.value[index] = defaultRequirement(def)
}

function changeOp(index: number, op: string) {
  const req = requirements.value[index]
  if (!req) return
  const wasList = req.op === 'in'
  const isList = op === 'in'
  let value = req.value
  if (isList && !wasList) value = value === null || value === undefined ? [] : [value]
  if (!isList && wasList) value = Array.isArray(value) ? (value[0] ?? null) : value
  requirements.value[index] = { ...req, op: op as AttributeRequirement['op'], value }
}

function setValue(index: number, value: unknown) {
  const req = requirements.value[index]
  if (req) requirements.value[index] = { ...req, value }
}

const asNumber = (v: unknown) => (typeof v === 'number' ? v : null)

/** Список значений для «одно из» у строк и чисел: вводится через «;». */
function setList(index: number, text: string | undefined) {
  const req = requirements.value[index]
  if (!req) return
  const isInt = defOf(req.code)?.value_type === 'int'
  const items = String(text ?? '')
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
  setValue(index, isInt ? items.map(Number) : items)
}

function isFilled(r: AttributeRequirement) {
  if (r.op === 'in') return Array.isArray(r.value) && r.value.length > 0
  return r.value !== null && r.value !== undefined && r.value !== ''
}

const valid = computed(
  () => name.value.trim().length > 0 && headcount.value >= 1 && requirements.value.every(isFilled),
)

function submit() {
  if (!valid.value) return
  emit('submit', {
    name: name.value.trim(),
    headcount: headcount.value,
    load_weight: weight.value,
    sort_order: props.role?.sort_order ?? 0,
    min_rank_order: minRank.value,
    allowed_position_ids: positions.value.length ? positions.value : null,
    attribute_requirements: requirements.value,
    assigned_unit_id: assignedId.value,
    allowed_category_ids: categories.value.length ? categories.value : null,
    is_active: active.value,
  })
}
</script>

<template>
  <Dialog v-model:visible="visible" :header="title" modal :style="{ width: '46rem' }">
    <form class="form" @submit.prevent="submit">
      <div class="row">
        <div class="field grow">
          <label for="role-name">Роль</label>
          <InputText id="role-name" v-model="name" maxlength="200" placeholder="Например, дневальный" />
        </div>
        <div class="field">
          <label for="role-count">Человек</label>
          <InputNumber v-model="headcount" input-id="role-count" :min="1" :max="100" show-buttons />
        </div>
        <div class="field">
          <label for="role-weight">Вес нагрузки</label>
          <InputNumber
            v-model="weight"
            input-id="role-weight"
            :min="0.1"
            :max="99"
            :step="0.25"
            :min-fraction-digits="1"
            :max-fraction-digits="2"
            show-buttons
          />
        </div>
      </div>

      <section class="block">
        <h4><i class="pi pi-users" /> Кто заступает</h4>
        <div class="row">
          <div class="field grow">
            <label for="role-unit">Закреплена за подразделением</label>
            <UnitTreeSelect
              v-model="assignedId"
              input-id="role-unit"
              :selectable="insideOwner"
              placeholder="Не закреплена"
              show-clear
            />
          </div>
          <div class="field grow">
            <label for="role-cat">Категории личного состава</label>
            <MultiSelect
              v-model="categories"
              input-id="role-cat"
              :options="categoryOptions"
              option-label="name"
              option-value="id"
              display="chip"
              placeholder="Любая категория"
            />
          </div>
        </div>
        <p class="hint">
          <template v-if="assigned && assigned.id !== ownerUnitId">
            <i class="pi pi-arrow-down-right" /> Ячейки роли сразу уйдут подразделению
            «{{ assigned.name }}» по цепочке и будут ждать его принятия. Вышестоящие не смогут
            передать их другому, допуск выдаётся только личному составу «{{ assigned.name }}».
          </template>
          <template v-else-if="assigned">
            <i class="pi pi-lock" /> Роль закрывает сам владелец наряда; допуск выдаётся только его
            личному составу.
          </template>
          <template v-else>
            <i class="pi pi-info-circle" /> Без закрепления владелец наряда сам решает, кому передать
            роль: вручную или автораспределением.
          </template>
          <br />
          <i class="pi pi-shield" /> Категория — строгое условие: людям других категорий допуск к
          роли не выдаётся даже с подтверждением.
        </p>
      </section>

      <h4>Дополнительные требования</h4>
      <p class="hint">
        Проверяются при выдаче допуска. Если человек им не соответствует, допуск можно выдать
        с подтверждением и комментарием.
      </p>
      <div class="row">
        <div class="field grow">
          <label for="role-rank">Звание не ниже</label>
          <Select
            v-model="minRank"
            input-id="role-rank"
            :options="rankOptions"
            option-label="label"
            option-value="value"
            show-clear
            filter
            placeholder="Любое"
          />
        </div>
        <div class="field grow">
          <label for="role-pos">Должности</label>
          <MultiSelect
            v-model="positions"
            input-id="role-pos"
            :options="refs.positions.filter((p) => p.is_active || positions.includes(p.id))"
            option-label="name"
            option-value="id"
            filter
            display="chip"
            placeholder="Любая"
          />
        </div>
      </div>

      <div class="field">
        <label>Характеристики</label>
        <div v-for="(req, i) in requirements" :key="i" class="req-row">
          <Select
            :model-value="req.code"
            :options="[...(defOf(req.code) ? [defOf(req.code)!] : []), ...freeAttributes]"
            option-label="name"
            option-value="code"
            class="req-attr"
            :aria-label="`Характеристика ${i + 1}`"
            @update:model-value="changeAttribute(i, $event)"
          />
          <Select
            :model-value="req.op"
            :options="opsFor(defOf(req.code)?.value_type ?? 'string').map((o) => ({ value: o, label: OPS[o] }))"
            option-label="label"
            option-value="value"
            class="req-op"
            :aria-label="`Условие ${i + 1}`"
            @update:model-value="changeOp(i, $event)"
          />
          <template v-if="defOf(req.code)?.value_type === 'enum'">
            <MultiSelect
              v-if="req.op === 'in'"
              :model-value="req.value"
              :options="defOf(req.code)?.enum_options ?? []"
              class="req-value"
              display="chip"
              :aria-label="`Значение ${i + 1}`"
              @update:model-value="setValue(i, $event)"
            />
            <Select
              v-else
              :model-value="req.value"
              :options="defOf(req.code)?.enum_options ?? []"
              class="req-value"
              :aria-label="`Значение ${i + 1}`"
              @update:model-value="setValue(i, $event)"
            />
          </template>
          <Select
            v-else-if="defOf(req.code)?.value_type === 'bool'"
            :model-value="req.value"
            :options="[
              { label: 'да', value: true },
              { label: 'нет', value: false },
            ]"
            option-label="label"
            option-value="value"
            class="req-value"
            @update:model-value="setValue(i, $event)"
          />
          <InputNumber
            v-else-if="defOf(req.code)?.value_type === 'int' && req.op !== 'in'"
            :model-value="asNumber(req.value)"
            :use-grouping="false"
            class="req-value"
            @update:model-value="setValue(i, $event)"
          />
          <DatePicker
            v-else-if="defOf(req.code)?.value_type === 'date'"
            :model-value="typeof req.value === 'string' ? fromIso(req.value) : null"
            date-format="dd.mm.yy"
            class="req-value"
            @update:model-value="setValue(i, $event instanceof Date ? toIso($event) : null)"
          />
          <InputText
            v-else-if="req.op === 'in'"
            :model-value="Array.isArray(req.value) ? req.value.join('; ') : ''"
            placeholder="Значения через «;»"
            class="req-value"
            @update:model-value="setList(i, $event)"
          />
          <InputText
            v-else
            :model-value="typeof req.value === 'string' ? req.value : ''"
            class="req-value"
            @update:model-value="setValue(i, $event)"
          />
          <Button
            icon="pi pi-times"
            text
            rounded
            severity="secondary"
            aria-label="Убрать требование"
            @click="requirements.splice(i, 1)"
          />
        </div>
        <div>
          <Button
            label="Добавить требование"
            icon="pi pi-plus"
            text
            size="small"
            :disabled="!freeAttributes.length"
            @click="addRequirement"
          />
        </div>
      </div>

      <label v-if="role" class="check">
        <Checkbox v-model="active" binary input-id="role-active" />
        <span>Роль действует</span>
      </label>

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
.grow {
  flex: 1;
  min-width: 14rem;
}
.field label {
  font-weight: 600;
}
h4 {
  margin: 0.5rem 0 0;
}
h4 .pi {
  color: var(--app-accent);
  margin-right: 0.3rem;
}
.block {
  display: grid;
  gap: 0.6rem;
  padding: 0.25rem 0.9rem 0.8rem;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  background: var(--app-subtle);
}
.hint .pi {
  font-size: 0.8rem;
  margin-right: 0.2rem;
}
.hint {
  margin: 0;
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
}
.req-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.req-attr {
  width: 12rem;
}
.req-op {
  width: 9rem;
}
.req-value {
  flex: 1;
  min-width: 0;
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
