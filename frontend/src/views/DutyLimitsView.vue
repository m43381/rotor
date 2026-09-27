<script setup lang="ts">
// Лимиты нарядов на человека за календарный месяц (open-questions №9, 27). К человеку
// применяется самое специфичное правило: ближайшее подразделение, затем звание и должность.
// Вручную лимит можно превысить с обоснованием (№38), для автораспределения он жёсткий.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import Select from 'primevue/select'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { ApiError, scheduling, unwrap, type DutyLimit, type DutyLimitIn } from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'

const units = useUnitsStore()
const refs = useRefsStore()
const toast = useToast()
const confirm = useConfirm()
const router = useRouter()

const limits = ref<DutyLimit[]>([])
const loading = ref(false)
const busy = ref(false)
const canCreate = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

async function load() {
  loading.value = true
  try {
    limits.value = await unwrap(scheduling.GET('/duty-limits'))
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  await Promise.all([units.me ? Promise.resolve() : units.load(), refs.ensure()]).catch(showError)
  await load()
})

const positionName = (id?: string | null) => (id ? (refs.positions.find((p) => p.id === id)?.name ?? '?') : '')

// --- диалог ---------------------------------------------------------------------------------
const visible = ref(false)
const editing = ref<DutyLimit | null>(null)
const form = ref<DutyLimitIn>({ unit_id: '', applies_to_subtree: true, max_duties: null, max_holiday_duties: null })
const unitId = ref<string | null>(null)

function open(l: DutyLimit | null) {
  editing.value = l
  unitId.value = l?.unit_id ?? units.me?.unit.id ?? null
  form.value = {
    unit_id: l?.unit_id ?? '',
    applies_to_subtree: l?.applies_to_subtree ?? true,
    rank_id: l?.rank_id ?? null,
    position_id: l?.position_id ?? null,
    max_duties: l?.max_duties ?? null,
    max_holiday_duties: l?.max_holiday_duties ?? null,
  }
  visible.value = true
}

const valid = computed(
  () => !!unitId.value && (form.value.max_duties != null || form.value.max_holiday_duties != null),
)

async function save() {
  if (!unitId.value) return
  busy.value = true
  const body = { ...form.value, unit_id: unitId.value }
  try {
    const l = editing.value
    if (l) {
      await unwrap(
        scheduling.PUT('/duty-limits/{limit_id}', {
          params: { path: { limit_id: l.id } },
          body: { ...body, version: l.version },
        }),
      )
    } else {
      await unwrap(scheduling.POST('/duty-limits', { body }))
    }
    visible.value = false
    toast.add({ severity: 'success', summary: 'Лимит сохранён', life: 3000 })
    await load()
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

function remove(l: DutyLimit) {
  confirm.require({
    header: 'Удалить лимит?',
    message: `${l.unit_name}: правило перестанет действовать.`,
    icon: 'pi pi-trash',
    acceptProps: { label: 'Удалить', severity: 'danger' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: async () => {
      try {
        await unwrap(scheduling.DELETE('/duty-limits/{limit_id}', { params: { path: { limit_id: l.id } } }))
        await load()
      } catch (e) {
        showError(e)
      }
    },
  })
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div class="title">
        <Button icon="pi pi-arrow-left" text rounded aria-label="Назад" @click="router.push('/duty-types')" />
        <div>
          <h1>Лимиты нарядов</h1>
          <p class="muted">
            Сколько нарядов в месяц может быть у одного человека. Действует самое точное правило:
            ближайшее подразделение, затем звание и должность.
          </p>
        </div>
      </div>
      <Button v-if="canCreate" label="Новый лимит" icon="pi pi-plus" @click="open(null)" />
    </header>

    <DataTable :value="limits" data-key="id" :loading="loading">
      <template #empty>Лимитов нет — число нарядов не ограничено</template>
      <Column header="Подразделение">
        <template #body="{ data }">
          {{ data.unit_name }}
          <div class="muted small">{{ data.applies_to_subtree ? 'и всё поддерево' : 'только само подразделение' }}</div>
        </template>
      </Column>
      <Column header="Для кого">
        <template #body="{ data }">
          <template v-if="data.rank_name || data.position_id">
            {{ [data.rank_name, positionName(data.position_id)].filter(Boolean).join(', ') }}
          </template>
          <span v-else class="muted">все</span>
        </template>
      </Column>
      <Column header="В месяц" style="width: 8rem">
        <template #body="{ data }">{{ data.max_duties ?? '—' }}</template>
      </Column>
      <Column header="Из них в выходные и праздники" style="width: 14rem">
        <template #body="{ data }">{{ data.max_holiday_duties ?? '—' }}</template>
      </Column>
      <Column style="width: 7rem">
        <template #body="{ data }">
          <template v-if="data.can_edit">
            <Button icon="pi pi-pencil" text rounded aria-label="Изменить лимит" @click="open(data)" />
            <Button icon="pi pi-trash" text rounded severity="danger" aria-label="Удалить лимит" @click="remove(data)" />
          </template>
        </template>
      </Column>
    </DataTable>

    <Dialog v-model:visible="visible" :header="editing ? 'Изменить лимит' : 'Новый лимит'" modal :style="{ width: '32rem' }">
      <div class="form">
        <label for="lim-unit">Подразделение</label>
        <UnitTreeSelect v-model="unitId" input-id="lim-unit" />
        <label class="check">
          <Checkbox v-model="form.applies_to_subtree" binary input-id="lim-subtree" />
          <span>Действует на всё поддерево</span>
        </label>
        <label for="lim-rank">Звание (необязательно)</label>
        <Select
          v-model="form.rank_id"
          input-id="lim-rank"
          :options="refs.activeRanks"
          option-label="name"
          option-value="id"
          show-clear
          placeholder="Любое"
        />
        <label for="lim-pos">Должность (необязательно)</label>
        <Select
          v-model="form.position_id"
          input-id="lim-pos"
          :options="refs.activePositions"
          option-label="name"
          option-value="id"
          show-clear
          filter
          placeholder="Любая"
        />
        <div class="row">
          <div class="field">
            <label for="lim-max">Нарядов в месяц</label>
            <InputNumber v-model="form.max_duties" input-id="lim-max" :min="0" :max="31" show-buttons />
          </div>
          <div class="field">
            <label for="lim-hol">Из них в выходные</label>
            <InputNumber v-model="form.max_holiday_duties" input-id="lim-hol" :min="0" :max="31" show-buttons />
          </div>
        </div>
        <div class="actions">
          <Button label="Отмена" severity="secondary" text @click="visible = false" />
          <Button label="Сохранить" :disabled="!valid" :loading="busy" @click="save" />
        </div>
      </div>
    </Dialog>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 72rem;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.title {
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.small {
  font-size: 0.85rem;
}
.form {
  display: grid;
  gap: 0.5rem;
}
.form label {
  font-weight: 600;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  font-weight: 400 !important;
}
.row {
  display: flex;
  gap: 1rem;
}
.field {
  display: grid;
  gap: 0.35rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
</style>
