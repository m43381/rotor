<script setup lang="ts">
// Запуск автораспределения (фаза 4b): вид задачи, режим, область, история прогонов графика.
// Расчёт ничего не меняет в графике — результат открывается как предпросмотр.
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Message from 'primevue/message'
import RadioButton from 'primevue/radiobutton'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, ref, watch } from 'vue'

import { ApiError, scheduling, unwrap, type Run, type RunBrief } from '@/api/client'
import { METHOD_LABELS, RUN_STATUS } from '@/utils/allocation'
import { formatDateTime } from '@/utils/dates'

const props = defineProps<{
  scheduleId: string
  selectedCellIds: string[]
  hasChildren: boolean
  // Выбор метода — только суперадминистратору (open-questions №46)
  canChooseMethod: boolean
}>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ preview: [run: Run] }>()

const kind = ref<'people' | 'units'>('people')
const mode = ref<'fill' | 'rebuild'>('fill')
const scope = ref<'month' | 'selected'>('month')
type Method = 'auto' | 'greedy' | 'hungarian' | 'local_search' | 'cpsat'
const method = ref<Method>('auto')
const METHODS: { value: Method; label: string }[] = (
  ['auto', 'greedy', 'hungarian', 'local_search', 'cpsat'] as const
).map((m) => ({ value: m, label: METHOD_LABELS[m] ?? m }))
const busy = ref(false)
const error = ref<string | null>(null)
const history = ref<RunBrief[]>([])

watch(visible, async (open) => {
  if (!open) return
  error.value = null
  scope.value = props.selectedCellIds.length ? 'selected' : 'month'
  try {
    history.value = await unwrap(
      scheduling.GET('/schedules/{schedule_id}/allocation-runs', {
        params: { path: { schedule_id: props.scheduleId } },
      }),
    )
  } catch {
    history.value = []
  }
})

const canRun = computed(() => kind.value === 'people' || props.hasChildren)

async function run() {
  busy.value = true
  error.value = null
  try {
    const result = await unwrap(
      scheduling.POST('/schedules/{schedule_id}/allocate', {
        params: { path: { schedule_id: props.scheduleId } },
        body: {
          kind: kind.value,
          mode: kind.value === 'people' ? mode.value : 'fill',
          cell_ids: scope.value === 'selected' ? props.selectedCellIds : null,
          seed: 1,
          method: kind.value === 'people' ? method.value : 'auto',
          config: {},
        },
      }),
    )
    visible.value = false
    emit('preview', result)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось рассчитать распределение'
  } finally {
    busy.value = false
  }
}

async function open(r: RunBrief) {
  try {
    const result = await unwrap(
      scheduling.GET('/allocation-runs/{run_id}', { params: { path: { run_id: r.id } } }),
    )
    visible.value = false
    emit('preview', result)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось открыть прогон'
  }
}
</script>

<template>
  <Dialog v-model:visible="visible" header="Автораспределение" modal :style="{ width: '38rem' }">
    <div class="form">
      <fieldset>
        <legend>Что распределить</legend>
        <label class="radio">
          <RadioButton v-model="kind" value="people" input-id="k-people" />
          <span>Людей по ячейкам, которые закрывает подразделение</span>
        </label>
        <label class="radio">
          <RadioButton v-model="kind" value="units" input-id="k-units" :disabled="!hasChildren" />
          <span>Ячейки по дочерним подразделениям (кому передать роль)</span>
        </label>
      </fieldset>
      <fieldset v-if="kind === 'people'">
        <legend>Режим</legend>
        <label class="radio">
          <RadioButton v-model="mode" value="fill" input-id="m-fill" />
          <span>Дозаполнить — только пустые места</span>
        </label>
        <label class="radio">
          <RadioButton v-model="mode" value="rebuild" input-id="m-rebuild" />
          <span>Пересобрать автоматические — ручные и закреплённые назначения не трогаются</span>
        </label>
      </fieldset>
      <fieldset>
        <legend>Область</legend>
        <label class="radio">
          <RadioButton v-model="scope" value="month" input-id="s-month" />
          <span>Весь месяц</span>
        </label>
        <label class="radio">
          <RadioButton v-model="scope" value="selected" input-id="s-selected" :disabled="!selectedCellIds.length" />
          <span>Выбранные ячейки ({{ selectedCellIds.length }})</span>
        </label>
      </fieldset>
      <fieldset v-if="canChooseMethod && kind === 'people'">
        <legend>Метод</legend>
        <Select v-model="method" :options="METHODS" option-label="label" option-value="value" input-id="method" />
        <small class="muted">
          «Автоматически» выбирает по размеру задачи. CP-SAT считается в фоне с большим пределом времени.
        </small>
      </fieldset>
      <p class="muted">
        Расчёт ничего не меняет: откроется предпросмотр с объяснением каждого решения, применить его
        можно отдельно.
      </p>
      <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

      <div v-if="history.length" class="history">
        <strong>Прошлые прогоны</strong>
        <div v-for="h in history.slice(0, 5)" :key="h.id" class="history-row">
          <Tag :value="RUN_STATUS[h.status]?.label" :severity="RUN_STATUS[h.status]?.severity" />
          <span>
            {{ h.kind === 'people' ? 'люди' : 'подразделения' }} · {{ h.filled }} из {{ h.places }}
            <template v-if="h.method"> · {{ METHOD_LABELS[h.method] ?? h.method }}</template>
          </span>
          <small class="muted">{{ formatDateTime(h.created_at) }}, {{ h.created_by_name }}</small>
          <Button label="Открыть" size="small" text @click="open(h)" />
        </div>
      </div>

      <div class="actions">
        <Button label="Отмена" severity="secondary" text @click="visible = false" />
        <Button label="Рассчитать" icon="pi pi-bolt" :disabled="!canRun" :loading="busy" @click="run" />
      </div>
    </div>
  </Dialog>
</template>

<style scoped>
.form {
  display: grid;
  gap: 0.75rem;
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
  margin: 0;
  font-size: 0.9rem;
}
.history {
  display: grid;
  gap: 0.35rem;
}
.history-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.history-row small {
  flex: 1;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
