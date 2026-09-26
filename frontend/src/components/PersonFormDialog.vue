<script setup lang="ts">
// Добавление человека в личный состав. Карточка минимальна (open-questions №29).
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import { computed, ref, watch } from 'vue'

import type { PersonCreate } from '@/api/client'
import AttributeFields from '@/components/AttributeFields.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'

const props = defineProps<{ busy: boolean; defaultUnitId: string | null }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ submit: [value: PersonCreate] }>()
const refs = useRefsStore()

const unitId = ref<string | null>(null)
const lastName = ref('')
const firstName = ref('')
const middleName = ref('')
const rankId = ref<string | null>(null)
const positionId = ref<string | null>(null)
const personalNo = ref('')
const note = ref('')
const attributes = ref<Record<string, unknown>>({})

watch(visible, (open) => {
  if (!open) return
  unitId.value = props.defaultUnitId
  lastName.value = firstName.value = middleName.value = personalNo.value = note.value = ''
  rankId.value = positionId.value = null
  attributes.value = {}
})

const valid = computed(() => !!unitId.value && !!lastName.value.trim() && !!firstName.value.trim())

function submit() {
  if (!valid.value || !unitId.value) return
  emit('submit', {
    unit_id: unitId.value,
    last_name: lastName.value.trim(),
    first_name: firstName.value.trim(),
    middle_name: middleName.value.trim() || null,
    rank_id: rankId.value,
    position_id: positionId.value,
    personal_no: personalNo.value.trim() || null,
    note: note.value.trim() || null,
    attributes: Object.fromEntries(
      Object.entries(attributes.value).filter(([, v]) => v !== null && v !== undefined),
    ),
  })
}
</script>

<template>
  <Dialog v-model:visible="visible" header="Добавить человека" modal :style="{ width: '44rem' }">
    <form class="form" @submit.prevent="submit">
      <div class="grid">
        <div class="field wide">
          <label for="p-unit">Подразделение</label>
          <UnitTreeSelect v-model="unitId" input-id="p-unit" />
        </div>
        <div class="field">
          <label for="p-last">Фамилия</label>
          <InputText id="p-last" v-model="lastName" maxlength="100" autofocus />
        </div>
        <div class="field">
          <label for="p-first">Имя</label>
          <InputText id="p-first" v-model="firstName" maxlength="100" />
        </div>
        <div class="field">
          <label for="p-middle">Отчество</label>
          <InputText id="p-middle" v-model="middleName" maxlength="100" />
        </div>
        <div class="field">
          <label for="p-no">Личный номер</label>
          <InputText id="p-no" v-model="personalNo" maxlength="50" />
        </div>
        <div class="field">
          <label for="p-rank">Звание</label>
          <Select
            id="p-rank"
            v-model="rankId"
            :options="refs.activeRanks"
            option-label="name"
            option-value="id"
            show-clear
            filter
            placeholder="Не указано"
          />
        </div>
        <div class="field">
          <label for="p-position">Должность</label>
          <Select
            id="p-position"
            v-model="positionId"
            :options="refs.activePositions"
            option-label="name"
            option-value="id"
            show-clear
            filter
            placeholder="Не указано"
          />
        </div>
      </div>
      <AttributeFields v-model="attributes" :definitions="refs.activeAttributes" />
      <div class="field">
        <label for="p-note">Примечание</label>
        <Textarea id="p-note" v-model="note" rows="2" maxlength="2000" auto-resize />
      </div>
      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button type="submit" label="Добавить" :disabled="!valid" :loading="busy" />
      </div>
    </form>
  </Dialog>
</template>

<style scoped>
.form {
  display: grid;
  gap: 1rem;
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem 1rem;
}
.field {
  display: grid;
  gap: 0.35rem;
}
.field.wide {
  grid-column: 1 / -1;
}
.field label {
  font-weight: 600;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
