<script setup lang="ts">
// Карточка человека: данные, характеристики, освобождения, история изменений.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import TabPanel from 'primevue/tabpanel'
import TabPanels from 'primevue/tabpanels'
import Tabs from 'primevue/tabs'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  ApiError,
  personnel,
  unwrap,
  type AuditEntry,
  type Exemption,
  type Person,
} from '@/api/client'
import AttributeFields from '@/components/AttributeFields.vue'
import ExemptionDialog from '@/components/ExemptionDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'
import { formatDate, formatDateTime } from '@/utils/dates'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const confirm = useConfirm()
const refs = useRefsStore()
const units = useUnitsStore()
// Восстановить в списках может тот, кто вообще может менять данные (не наблюдатель);
// окончательно права проверяет сервер.
const canWrite = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))

const person = ref<Person | null>(null)
const history = ref<AuditEntry[]>([])
const busy = ref(false)
const tab = ref('main')

// Форма редактирования — копия полей карточки
const form = ref({
  last_name: '',
  first_name: '',
  middle_name: '',
  rank_id: null as string | null,
  position_id: null as string | null,
  personal_no: '',
  note: '',
})
const attributes = ref<Record<string, unknown>>({})

const personId = computed(() => String(route.params.id))
const editable = computed(() => person.value?.can_edit === true)
const title = computed(() =>
  person.value
    ? [person.value.last_name, person.value.first_name, person.value.middle_name].filter(Boolean).join(' ')
    : '',
)
const dirty = computed(() => {
  const p = person.value
  if (!p) return false
  const f = form.value
  return (
    f.last_name !== p.last_name ||
    f.first_name !== p.first_name ||
    (f.middle_name || null) !== (p.middle_name ?? null) ||
    f.rank_id !== (p.rank_id ?? null) ||
    f.position_id !== (p.position_id ?? null) ||
    (f.personal_no || null) !== (p.personal_no ?? null) ||
    (f.note || null) !== (p.note ?? null) ||
    JSON.stringify(normalizedAttrs(attributes.value)) !== JSON.stringify(normalizedAttrs(p.attributes))
  )
})

function normalizedAttrs(values: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(values)
      .filter(([, v]) => v !== null && v !== undefined)
      .sort(([a], [b]) => a.localeCompare(b)),
  )
}

function fill(p: Person) {
  person.value = p
  form.value = {
    last_name: p.last_name,
    first_name: p.first_name,
    middle_name: p.middle_name ?? '',
    rank_id: p.rank_id ?? null,
    position_id: p.position_id ?? null,
    personal_no: p.personal_no ?? '',
    note: p.note ?? '',
  }
  attributes.value = { ...p.attributes }
}

async function load() {
  try {
    await refs.ensure()
    fill(await unwrap(personnel.GET('/people/{person_id}', { params: { path: { person_id: personId.value } } })))
  } catch (e) {
    showError(e)
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) await router.replace('/people')
  }
}

async function loadHistory() {
  // История — вспомогательная вкладка: её недоступность не мешает работать с карточкой.
  try {
    const page = await unwrap(
      personnel.GET('/audit', { params: { query: { entity_id: personId.value, limit: 100 } } }),
    )
    history.value = page.items
  } catch {
    history.value = []
  }
}

onMounted(async () => {
  await load()
  await loadHistory()
})
watch(personId, async () => {
  await load()
  await loadHistory()
})

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

async function run(action: () => Promise<Person | void>, success: string) {
  busy.value = true
  try {
    const result = await action()
    if (result) fill(result)
    toast.add({ severity: 'success', summary: success, life: 3000 })
    await loadHistory()
  } catch (e) {
    showError(e)
    if (e instanceof ApiError && e.status === 409) await load()
  } finally {
    busy.value = false
  }
}

function save() {
  const p = person.value
  if (!p) return
  // Характеристики: передаём изменённые, удалённые — как null.
  const changed: Record<string, unknown> = {}
  const keys = new Set([...Object.keys(p.attributes), ...Object.keys(attributes.value)])
  for (const k of keys) {
    const next = attributes.value[k] ?? null
    if (JSON.stringify(next) !== JSON.stringify(p.attributes[k] ?? null)) changed[k] = next
  }
  const f = form.value
  return run(
    () =>
      unwrap(
        personnel.PATCH('/people/{person_id}', {
          params: { path: { person_id: p.id } },
          body: {
            version: p.version,
            last_name: f.last_name.trim(),
            first_name: f.first_name.trim(),
            middle_name: f.middle_name.trim() || null,
            rank_id: f.rank_id,
            position_id: f.position_id,
            personal_no: f.personal_no.trim() || null,
            note: f.note.trim() || null,
            attributes: Object.keys(changed).length ? changed : undefined,
          },
        }),
      ),
    'Изменения сохранены',
  )
}

// --- исключение из списков / восстановление (open-questions №34) -------------------------------
// «Исключить из списков» — человек выбыл (уволен, выпущен, переведён в другую организацию):
// пропадает из списков и нарядов, но остаётся в прошлых графиках и истории.
const EXCLUDE_REASONS = [
  'Увольнение',
  'Выпуск',
  'Перевод в другую организацию',
  'Внесён ошибочно',
  'Прочее',
]
const excludeVisible = ref(false)
const excludeReason = ref(EXCLUDE_REASONS[0] ?? '')
const excludeComment = ref('')

function openExclude() {
  excludeReason.value = EXCLUDE_REASONS[0] ?? ''
  excludeComment.value = ''
  excludeVisible.value = true
}

async function exclude() {
  const p = person.value
  if (!p) return
  const comment = [excludeReason.value, excludeComment.value.trim()].filter(Boolean).join(': ')
  await run(
    () =>
      unwrap(
        personnel.POST('/people/{person_id}/archive', {
          params: { path: { person_id: p.id } },
          body: { version: p.version, comment },
        }),
      ),
    'Исключён из списков личного состава',
  )
  excludeVisible.value = false
}

function restore() {
  const p = person.value
  if (!p) return
  confirm.require({
    header: 'Восстановить в списках?',
    message: 'Человек снова появится в списках личного состава и сможет назначаться в наряды.',
    icon: 'pi pi-replay',
    acceptProps: { label: 'Восстановить' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: () =>
      run(
        () =>
          unwrap(
            personnel.POST('/people/{person_id}/restore', {
              params: { path: { person_id: p.id } },
              body: { version: p.version },
            }),
          ),
        'Восстановлен в списках',
      ),
  })
}

/** Причина исключения — из последней записи истории об исключении. */
const exclusion = computed(() => {
  const entry = history.value.find((h) => h.action === 'person.archive')
  return entry ? { at: entry.occurred_at, reason: entry.comment } : null
})

// --- перевод в другое подразделение (редкая операция, поэтому здесь, а не в списке) -------------
const transferVisible = ref(false)
const transferTarget = ref<string | null>(null)

async function transfer() {
  const p = person.value
  const target = transferTarget.value
  if (!p || !target) return
  await run(async () => {
    await unwrap(personnel.POST('/people/transfer', { body: { person_ids: [p.id], unit_id: target } }))
    return unwrap(personnel.GET('/people/{person_id}', { params: { path: { person_id: p.id } } }))
  }, 'Переведён в другое подразделение')
  transferVisible.value = false
}

// --- освобождения ------------------------------------------------------------------------------
const exemptionVisible = ref(false)
const editingExemption = ref<Exemption | null>(null)

function openExemption(e: Exemption | null) {
  editingExemption.value = e
  exemptionVisible.value = true
}

async function onExemption(value: { reason_id: string; date_from: string; date_to: string; comment: string | null }) {
  const p = person.value
  if (!p) return
  const e = editingExemption.value
  await run(async () => {
    if (e) {
      await unwrap(
        personnel.PUT('/exemptions/{exemption_id}', {
          params: { path: { exemption_id: e.id } },
          body: { ...value, version: e.version },
        }),
      )
    } else {
      await unwrap(
        personnel.POST('/people/{person_id}/exemptions', {
          params: { path: { person_id: p.id } },
          body: value,
        }),
      )
    }
    exemptionVisible.value = false
    return unwrap(personnel.GET('/people/{person_id}', { params: { path: { person_id: p.id } } }))
  }, e ? 'Освобождение изменено' : 'Освобождение добавлено')
}

function deleteExemption(e: Exemption) {
  const p = person.value
  if (!p) return
  confirm.require({
    header: 'Удалить освобождение?',
    message: `${refs.reasonName(e.reason_id)}: ${formatDate(e.date_from)} — ${formatDate(e.date_to)}`,
    icon: 'pi pi-trash',
    acceptProps: { label: 'Удалить', severity: 'danger' },
    rejectProps: { label: 'Отмена', severity: 'secondary', text: true },
    accept: () =>
      run(async () => {
        await unwrap(personnel.DELETE('/exemptions/{exemption_id}', { params: { path: { exemption_id: e.id } } }))
        return unwrap(personnel.GET('/people/{person_id}', { params: { path: { person_id: p.id } } }))
      }, 'Освобождение удалено'),
  })
}

const ACTIONS: Record<string, string> = {
  'person.create': 'Добавлен',
  'person.update': 'Изменён',
  'person.archive': 'Исключён из списков',
  'person.restore': 'Восстановлен в списках',
  'person.transfer': 'Перевод',
  'exemption.create': 'Освобождение',
}
function describe(entry: AuditEntry): string {
  const fields = Object.keys(entry.after ?? entry.before ?? {})
  return fields.length ? fields.join(', ') : ''
}
</script>

<template>
  <section v-if="person" class="page">
    <header class="page-header">
      <div>
        <Button icon="pi pi-arrow-left" text rounded aria-label="Назад" @click="router.push('/people')" />
        <h1>{{ title }}</h1>
        <Tag v-if="!person.is_active" value="Исключён из списков" severity="secondary" />
        <p class="muted">{{ person.rank_name ?? 'Звание не указано' }} · {{ person.unit_name }}</p>
      </div>
      <div class="actions">
        <template v-if="person.is_active && editable">
          <Button
            label="Перевести"
            icon="pi pi-arrow-right-arrow-left"
            severity="secondary"
            text
            @click="((transferTarget = null), (transferVisible = true))"
          />
          <Button
            label="Исключить из списков"
            icon="pi pi-user-minus"
            severity="secondary"
            text
            @click="openExclude"
          />
        </template>
        <Button
          v-if="!person.is_active && canWrite"
          label="Восстановить в списках"
          icon="pi pi-replay"
          severity="secondary"
          :loading="busy"
          @click="restore"
        />
        <Button
          v-if="editable"
          label="Сохранить"
          icon="pi pi-check"
          :disabled="!dirty || !form.last_name.trim() || !form.first_name.trim()"
          :loading="busy"
          @click="save"
        />
      </div>
    </header>

    <Message v-if="!person.is_active" severity="warn" :closable="false">
      Исключён из списков личного состава
      <template v-if="exclusion">
        {{ formatDateTime(exclusion.at) }}<template v-if="exclusion.reason"> — {{ exclusion.reason }}</template>
      </template>.
      В списки и наряды не попадает; в прошлых графиках и истории сохраняется.
    </Message>
    <Message v-else-if="!editable" severity="secondary" :closable="false">
      Только просмотр: изменение недоступно для вашей роли.
    </Message>

    <Tabs v-model:value="tab">
      <TabList>
        <Tab value="main">Данные</Tab>
        <Tab value="exemptions">Освобождения ({{ person.exemptions.length }})</Tab>
        <Tab value="history">История</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="main">
          <div class="grid">
            <div class="field">
              <label for="f-last">Фамилия</label>
              <InputText id="f-last" v-model="form.last_name" :disabled="!editable" maxlength="100" />
            </div>
            <div class="field">
              <label for="f-first">Имя</label>
              <InputText id="f-first" v-model="form.first_name" :disabled="!editable" maxlength="100" />
            </div>
            <div class="field">
              <label for="f-middle">Отчество</label>
              <InputText id="f-middle" v-model="form.middle_name" :disabled="!editable" maxlength="100" />
            </div>
            <div class="field">
              <label for="f-rank">Звание</label>
              <Select
                id="f-rank"
                v-model="form.rank_id"
                :options="refs.ranks"
                option-label="name"
                option-value="id"
                :disabled="!editable"
                show-clear
                filter
                placeholder="Не указано"
              />
            </div>
            <div class="field">
              <label for="f-position">Должность</label>
              <Select
                id="f-position"
                v-model="form.position_id"
                :options="refs.positions"
                option-label="name"
                option-value="id"
                :disabled="!editable"
                show-clear
                filter
                placeholder="Не указано"
              />
            </div>
            <div class="field">
              <label for="f-no">Личный номер</label>
              <InputText id="f-no" v-model="form.personal_no" :disabled="!editable" maxlength="50" />
            </div>
          </div>
          <h3>Характеристики</h3>
          <AttributeFields v-model="attributes" :definitions="refs.activeAttributes" :disabled="!editable" />
          <div class="field note">
            <label for="f-note">Примечание</label>
            <Textarea id="f-note" v-model="form.note" :disabled="!editable" rows="3" maxlength="2000" auto-resize />
          </div>
        </TabPanel>

        <TabPanel value="exemptions">
          <div class="toolbar">
            <Button v-if="editable" label="Добавить освобождение" icon="pi pi-plus" @click="openExemption(null)" />
          </div>
          <DataTable :value="person.exemptions" data-key="id">
            <template #empty>Освобождений нет</template>
            <Column header="Причина">
              <template #body="{ data }">{{ refs.reasonName(data.reason_id) }}</template>
            </Column>
            <Column header="Период">
              <template #body="{ data }">{{ formatDate(data.date_from) }} — {{ formatDate(data.date_to) }}</template>
            </Column>
            <Column field="comment" header="Комментарий" />
            <Column v-if="editable" style="width: 7rem">
              <template #body="{ data }">
                <Button icon="pi pi-pencil" text rounded aria-label="Изменить" @click="openExemption(data)" />
                <Button
                  icon="pi pi-trash"
                  text
                  rounded
                  severity="danger"
                  aria-label="Удалить"
                  @click="deleteExemption(data)"
                />
              </template>
            </Column>
          </DataTable>
        </TabPanel>

        <TabPanel value="history">
          <DataTable :value="history" data-key="id">
            <template #empty>Изменений нет</template>
            <Column header="Когда" style="width: 10rem">
              <template #body="{ data }">{{ formatDateTime(data.occurred_at) }}</template>
            </Column>
            <Column header="Кто" field="actor_name" style="width: 14rem" />
            <Column header="Действие" style="width: 10rem">
              <template #body="{ data }">{{ ACTIONS[data.action] ?? data.action }}</template>
            </Column>
            <Column header="Поля">
              <template #body="{ data }">
                <span class="muted">{{ describe(data) }}</span>
                <span v-if="data.comment"> — {{ data.comment }}</span>
              </template>
            </Column>
          </DataTable>
        </TabPanel>
      </TabPanels>
    </Tabs>

    <Dialog
      v-model:visible="excludeVisible"
      header="Исключить из списков личного состава"
      modal
      :style="{ width: '32rem' }"
    >
      <div class="dialog">
        <p class="muted-block">
          Человек пропадёт из списков и не будет назначаться в наряды. Данные не удаляются: он
          останется в прошлых графиках и истории, его можно восстановить.
        </p>
        <label for="ex-why">Причина</label>
        <Select id="ex-why" v-model="excludeReason" :options="EXCLUDE_REASONS" />
        <label for="ex-note">Комментарий (приказ, дата)</label>
        <Textarea id="ex-note" v-model="excludeComment" rows="2" maxlength="500" auto-resize />
        <div class="dialog-actions">
          <Button label="Отмена" severity="secondary" text @click="excludeVisible = false" />
          <Button label="Исключить" severity="warn" :loading="busy" @click="exclude" />
        </div>
      </div>
    </Dialog>
    <Dialog
      v-model:visible="transferVisible"
      header="Перевод в другое подразделение"
      modal
      :style="{ width: '30rem' }"
    >
      <div class="dialog">
        <UnitTreeSelect v-model="transferTarget" placeholder="Куда перевести" />
        <div class="dialog-actions">
          <Button label="Отмена" severity="secondary" text @click="transferVisible = false" />
          <Button label="Перевести" :disabled="!transferTarget" :loading="busy" @click="transfer" />
        </div>
      </div>
    </Dialog>
    <ExemptionDialog
      v-model:visible="exemptionVisible"
      :title="editingExemption ? 'Изменить освобождение' : 'Новое освобождение'"
      :exemption="editingExemption"
      :busy="busy"
      @submit="onExemption"
    />
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
  flex-wrap: wrap;
}
.page-header > div:first-child {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
h3 {
  margin: 1.25rem 0 0.75rem;
  font-size: 1rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0;
  flex-basis: 100%;
  padding-left: 2.75rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem 1rem;
}
.field {
  display: grid;
  gap: 0.35rem;
}
.field label {
  font-weight: 600;
}
.note {
  margin-top: 1rem;
}
.toolbar {
  margin-bottom: 0.75rem;
}
.dialog {
  display: grid;
  gap: 0.5rem;
}
.dialog label {
  font-weight: 600;
  margin-top: 0.4rem;
}
.muted-block {
  color: var(--p-text-muted-color);
  margin: 0;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
</style>
