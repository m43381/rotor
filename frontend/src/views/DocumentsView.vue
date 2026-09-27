<script setup lang="ts">
// Документы (фаза 6b): реквизиты печатных форм подразделения (open-questions №52) и шаблоны
// PDF-форм — их заменяет только суперадминистратор (№51).
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { ApiError, documents, saveFile, unwrap } from '@/api/client'
import type { components } from '@/api/generated/documents'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'
import { formatDateTime } from '@/utils/dates'

type Settings = components['schemas']['SettingsOut']
type TemplateBrief = components['schemas']['TemplateBrief']
type FormCode = TemplateBrief['form']

const units = useUnitsStore()
const toast = useToast()
const confirm = useConfirm()

const FIELDS = [
  { key: 'approver_position', label: 'Должность утверждающего', hint: 'Начальник факультета' },
  { key: 'approver_rank', label: 'Звание утверждающего', hint: 'полковник' },
  { key: 'approver_name', label: 'Утверждающий (инициалы, фамилия)', hint: 'И. И. Иванов' },
  { key: 'compiler_position', label: 'Должность составителя', hint: 'Заместитель начальника факультета' },
  { key: 'compiler_rank', label: 'Звание составителя', hint: 'подполковник' },
  { key: 'compiler_name', label: 'Составитель (инициалы, фамилия)', hint: 'П. П. Петров' },
] as const
type Field = (typeof FIELDS)[number]['key']

const unitId = ref<string | null>(null)
const settings = ref<Settings | null>(null)
const form = reactive<Record<Field, string>>({
  approver_position: '',
  approver_rank: '',
  approver_name: '',
  compiler_position: '',
  compiler_rank: '',
  compiler_name: '',
})
const busy = ref(false)
const templates = ref<TemplateBrief[]>([])
const isSuperadmin = computed(() => units.me?.roles.includes('superadmin') === true)
const uploadFor = ref<FormCode | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

function showError(e: unknown, fallback: string) {
  const detail = e instanceof ApiError ? e.message : fallback
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 8000 })
}

function fill(s: Settings) {
  settings.value = s
  const source = s.own ?? s.effective
  for (const f of FIELDS) form[f.key] = source?.[f.key] ?? ''
}

async function load() {
  if (!unitId.value) return
  try {
    fill(
      await unwrap(
        documents.GET('/document-settings/{unit_id}', { params: { path: { unit_id: unitId.value } } }),
      ),
    )
  } catch (e) {
    showError(e, 'Не удалось загрузить реквизиты')
  }
}

async function save() {
  if (!unitId.value) return
  busy.value = true
  try {
    fill(
      await unwrap(
        documents.PUT('/document-settings/{unit_id}', {
          params: { path: { unit_id: unitId.value } },
          body: { ...form, version: settings.value?.version ?? null },
        }),
      ),
    )
    toast.add({ severity: 'success', summary: 'Реквизиты сохранены', life: 3000 })
  } catch (e) {
    showError(e, 'Не удалось сохранить реквизиты')
  } finally {
    busy.value = false
  }
}

function inherit() {
  confirm.require({
    header: 'Использовать реквизиты вышестоящего?',
    message: 'Свои реквизиты подразделения будут удалены.',
    acceptLabel: 'Удалить свои',
    rejectLabel: 'Отмена',
    accept: async () => {
      if (!unitId.value) return
      try {
        fill(
          await unwrap(
            documents.DELETE('/document-settings/{unit_id}', { params: { path: { unit_id: unitId.value } } }),
          ),
        )
      } catch (e) {
        showError(e, 'Не удалось удалить реквизиты')
      }
    },
  })
}

// --- шаблоны -----------------------------------------------------------------------------------

async function loadTemplates() {
  try {
    templates.value = await unwrap(documents.GET('/templates'))
  } catch {
    templates.value = []
  }
}

async function downloadTemplate(t: TemplateBrief) {
  try {
    const data = await unwrap(documents.GET('/templates/{form}', { params: { path: { form: t.form } } }))
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([data.body], { type: 'text/html' }))
    link.download = `${t.form}.html`
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e) {
    showError(e, 'Не удалось скачать шаблон')
  }
}

function chooseUpload(t: TemplateBrief) {
  uploadFor.value = t.form
  fileInput.value?.click()
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const target = uploadFor.value
  if (!file || !target) return
  try {
    const body = await file.text()
    await unwrap(
      documents.PUT('/templates/{form}', {
        params: { path: { form: target } },
        body: { body, comment: file.name },
      }),
    )
    toast.add({ severity: 'success', summary: 'Шаблон загружен', detail: 'Формы печатаются по новому шаблону', life: 4000 })
    await loadTemplates()
  } catch (e) {
    showError(e, 'Не удалось загрузить шаблон')
  }
}

async function preview(t: TemplateBrief) {
  try {
    await saveFile(
      documents.POST('/templates/{form}/preview', {
        params: { path: { form: t.form } },
        body: {},
        parseAs: 'blob',
      }),
      `${t.form}.pdf`,
    )
  } catch (e) {
    showError(e, 'Не удалось построить предпросмотр')
  }
}

function reset(t: TemplateBrief) {
  confirm.require({
    header: 'Вернуть встроенный шаблон?',
    message: `«${t.title}» снова будет печататься по встроенному шаблону. Загруженная версия сохранится в истории.`,
    acceptLabel: 'Вернуть',
    rejectLabel: 'Отмена',
    accept: async () => {
      try {
        await unwrap(documents.POST('/templates/{form}/reset', { params: { path: { form: t.form } } }))
        await loadTemplates()
      } catch (e) {
        showError(e, 'Не удалось вернуть шаблон')
      }
    },
  })
}

watch(unitId, load)
onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  unitId.value = units.me?.unit.id ?? null
  await loadTemplates()
})
</script>

<template>
  <section class="page">
    <header>
      <h1>Документы</h1>
      <p class="muted">
        Реквизиты печатных форм подразделения: кто утверждает графики и суточный наряд и кто их составляет.
        Если своих реквизитов нет, используются реквизиты ближайшего вышестоящего подразделения.
      </p>
    </header>

    <div class="card">
      <div class="unit">
        <UnitTreeSelect v-model="unitId" placeholder="Подразделение" input-id="doc-unit" />
      </div>
      <template v-if="settings">
        <Message v-if="settings.inherited_from" severity="info" :closable="false">
          Своих реквизитов нет — действуют реквизиты подразделения «{{ settings.inherited_from }}».
          <template v-if="settings.can_edit">Сохраните форму, чтобы задать свои.</template>
        </Message>
        <Message v-else-if="!settings.own" severity="warn" :closable="false">
          Реквизиты не заданы ни здесь, ни выше — в документах строки подписей будут пустыми.
        </Message>
        <div class="grid">
          <label v-for="f in FIELDS" :key="f.key" class="field">
            <span>{{ f.label }}</span>
            <InputText :id="`req-${f.key}`" v-model="form[f.key]" :placeholder="f.hint" :disabled="!settings.can_edit" />
          </label>
        </div>
        <div v-if="settings.can_edit" class="actions">
          <Button v-if="settings.own" label="Использовать реквизиты вышестоящего" severity="secondary" text @click="inherit" />
          <Button label="Сохранить" icon="pi pi-check" :loading="busy" @click="save" />
        </div>
        <p v-else class="muted small">Реквизиты подразделения задаёт его администратор.</p>
      </template>
    </div>

    <div v-if="isSuperadmin" class="card">
      <h2>Шаблоны печатных форм</h2>
      <p class="muted small">
        PDF-формы строятся из HTML-шаблонов. Скачайте текущий шаблон, измените его и загрузите — он проверяется на
        демо-данных, ошибки показываются с номером строки. Предыдущие версии сохраняются. Excel и Word формируются
        программой, в них меняются только реквизиты.
      </p>
      <input ref="fileInput" type="file" accept=".html,.htm" class="hidden" @change="upload" />
      <div v-for="t in templates" :key="t.form" class="template">
        <div class="t-title">
          <strong>{{ t.title }}</strong>
          <Tag v-if="t.custom" value="свой шаблон" severity="warn" />
          <Tag v-else value="встроенный" severity="secondary" />
          <small v-if="t.custom" class="muted">{{ t.updated_by_name }}, {{ formatDateTime(t.updated_at ?? '') }}</small>
          <small class="muted">форматы: {{ t.formats.join(', ').toUpperCase() }}</small>
        </div>
        <div class="t-actions">
          <Button label="Скачать" icon="pi pi-download" size="small" text @click="downloadTemplate(t)" />
          <Button label="Загрузить свой…" icon="pi pi-upload" size="small" text @click="chooseUpload(t)" />
          <Button label="Предпросмотр PDF" icon="pi pi-eye" size="small" text @click="preview(t)" />
          <Button v-if="t.custom" label="Вернуть встроенный" icon="pi pi-undo" size="small" severity="secondary" text @click="reset(t)" />
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 64rem;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
h2 {
  margin: 0;
  font-size: 1.1rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.small {
  font-size: 0.9rem;
}
.card {
  border: 1px solid var(--p-content-border-color);
  border-radius: 6px;
  padding: 1rem;
  display: grid;
  gap: 0.8rem;
  background: var(--p-content-background);
}
.unit {
  width: 24rem;
  max-width: 100%;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: 0.75rem 1rem;
}
.field {
  display: grid;
  gap: 0.25rem;
}
.field span {
  font-size: 0.9rem;
  color: var(--p-text-muted-color);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.hidden {
  display: none;
}
.template {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  border-top: 1px solid var(--p-content-border-color);
  padding-top: 0.6rem;
}
.t-title {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
}
.t-actions {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}
</style>
