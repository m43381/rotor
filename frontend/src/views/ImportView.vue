<script setup lang="ts">
// Импорт из xlsx/csv (фаза 6a, open-questions №16, №54–55): скачать шаблон → загрузить →
// предпросмотр по строкам → применить. Пока не нажато «Применить», данные не меняются.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import Message from 'primevue/message'
import SelectButton from 'primevue/selectbutton'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'

import {
  ApiError,
  documents,
  saveFile,
  unwrap,
  type ImportJob,
  type ImportKind,
  type ImportRow,
} from '@/api/client'
import { formatDateTime } from '@/utils/dates'

const toast = useToast()

const KINDS: { value: ImportKind; label: string }[] = [
  { value: 'people', label: 'Личный состав' },
  { value: 'clearances', label: 'Допуски' },
  { value: 'exemptions', label: 'Освобождения' },
]
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label])) as Record<string, string>
const ACTIONS: Record<string, { label: string; severity: string }> = {
  create: { label: 'Будет создано', severity: 'success' },
  update: { label: 'Будет изменено', severity: 'info' },
  unchanged: { label: 'Без изменений', severity: 'secondary' },
  error: { label: 'Ошибка', severity: 'danger' },
}
type Filter = 'all' | 'error' | 'create' | 'update' | 'unchanged' | 'warnings'

const kind = ref<ImportKind>('people')
const job = ref<ImportJob | null>(null)
const rows = ref<ImportRow[]>([])
const total = ref(0)
const first = ref(0)
const pageSize = ref(50)
const filter = ref<Filter>('all')
const skipInvalid = ref(false)
const busy = ref(false)
const loading = ref(false)
const history = ref<ImportJob[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const pending = computed(() => job.value?.status === 'preview')
const errors = computed(() => job.value?.summary.error ?? 0)
const changes = computed(() => (job.value?.summary.create ?? 0) + (job.value?.summary.update ?? 0))
const canApply = computed(() => pending.value && changes.value > 0 && (errors.value === 0 || skipInvalid.value))
const filters = computed(() => {
  const s = job.value?.summary ?? {}
  return [
    { value: 'all', label: `Все (${job.value?.total ?? 0})` },
    { value: 'error', label: `Ошибки (${s.error ?? 0})` },
    { value: 'create', label: `Создать (${s.create ?? 0})` },
    { value: 'update', label: `Изменить (${s.update ?? 0})` },
    { value: 'unchanged', label: `Без изменений (${s.unchanged ?? 0})` },
    { value: 'warnings', label: 'С предупреждениями' },
  ]
})

function showError(e: unknown, fallback: string) {
  const detail = e instanceof ApiError ? e.message : fallback
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 8000 })
}

async function loadHistory() {
  try {
    history.value = await unwrap(documents.GET('/imports'))
  } catch {
    history.value = []
  }
}

async function loadRows() {
  if (!job.value) return
  loading.value = true
  try {
    const f = filter.value
    const page = await unwrap(
      documents.GET('/imports/{job_id}/rows', {
        params: {
          path: { job_id: job.value.id },
          query: {
            action: f === 'all' || f === 'warnings' ? undefined : f,
            with_warnings: f === 'warnings',
            offset: first.value,
            limit: pageSize.value,
          },
        },
      }),
    )
    rows.value = page.items
    total.value = page.total
  } catch (e) {
    showError(e, 'Не удалось загрузить строки')
  } finally {
    loading.value = false
  }
}

function open(j: ImportJob) {
  job.value = j
  kind.value = j.kind
  skipInvalid.value = false
  first.value = 0
  filter.value = j.summary.error ? 'error' : 'all'
  void loadRows()
}

async function downloadTemplate() {
  busy.value = true
  try {
    await saveFile(
      documents.GET('/imports/templates/{kind}', {
        params: { path: { kind: kind.value } },
        parseAs: 'blob',
      }),
      'template.xlsx',
    )
  } catch (e) {
    showError(e, 'Не удалось скачать шаблон')
  } finally {
    busy.value = false
  }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  busy.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const created = await unwrap(
      documents.POST('/imports/{kind}', {
        params: { path: { kind: kind.value } },
        body: form as unknown as { file: string },
        bodySerializer: (b) => b as unknown as FormData,
      }),
    )
    open(created)
    void loadHistory()
  } catch (e) {
    showError(e, 'Не удалось загрузить файл')
  } finally {
    busy.value = false
  }
}

async function action(name: 'apply' | 'recheck' | 'discard') {
  if (!job.value) return
  busy.value = true
  try {
    const id = job.value.id
    const result =
      name === 'apply'
        ? await unwrap(
            documents.POST('/imports/{job_id}/apply', {
              params: { path: { job_id: id } },
              body: { skip_invalid: skipInvalid.value },
            }),
          )
        : name === 'recheck'
          ? await unwrap(documents.POST('/imports/{job_id}/recheck', { params: { path: { job_id: id } } }))
          : await unwrap(documents.POST('/imports/{job_id}/discard', { params: { path: { job_id: id } } }))
    open(result)
    if (name === 'apply') {
      toast.add({
        severity: 'success',
        summary: 'Импорт применён',
        detail: `Создано и изменено записей: ${result.applied_rows ?? 0}`,
        life: 5000,
      })
    }
    void loadHistory()
  } catch (e) {
    if (e instanceof ApiError && e.code === 'import_stale' && job.value) {
      // Сервис уже проверил файл заново — показываем свежий результат
      const fresh = await unwrap(
        documents.GET('/imports/{job_id}', { params: { path: { job_id: job.value.id } } }),
      ).catch(() => null)
      if (fresh) open(fresh)
    }
    showError(e, 'Не удалось выполнить действие')
  } finally {
    busy.value = false
  }
}

async function downloadReport() {
  if (!job.value) return
  try {
    await saveFile(
      documents.GET('/imports/{job_id}/report', {
        params: { path: { job_id: job.value.id } },
        parseAs: 'blob',
      }),
      'report.xlsx',
    )
  } catch (e) {
    showError(e, 'Не удалось скачать отчёт')
  }
}

function reset() {
  job.value = null
  rows.value = []
}

function onPage(event: DataTablePageEvent) {
  first.value = event.first
  pageSize.value = event.rows
  void loadRows()
}
watch(filter, () => {
  first.value = 0
  void loadRows()
})
watch(kind, (k) => {
  if (job.value && job.value.kind !== k) reset()
})
onMounted(loadHistory)

function cellText(value: unknown): string {
  if (value === null || value === undefined) return ''
  const s = String(value)
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s)
  return iso ? `${iso[3]}.${iso[2]}.${iso[1]}` : s
}
function change(v: unknown): string {
  return v === null || v === undefined || v === '' ? '—' : cellText(v)
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <h1>Импорт</h1>
      <p class="muted">
        Личный состав, допуски и освобождения из xlsx или csv по шаблону. После загрузки видно, что
        будет сделано с каждой строкой; данные меняются только по кнопке «Применить».
      </p>
    </header>

    <div class="toolbar">
      <SelectButton
        v-model="kind"
        :options="KINDS"
        option-label="label"
        option-value="value"
        :allow-empty="false"
        :disabled="busy"
      />
      <Button label="Скачать шаблон" icon="pi pi-download" severity="secondary" :loading="busy" @click="downloadTemplate" />
      <Button label="Загрузить файл" icon="pi pi-upload" :loading="busy" @click="fileInput?.click()" />
      <input
        ref="fileInput"
        type="file"
        accept=".xlsx,.csv"
        class="hidden"
        data-testid="import-file"
        @change="upload"
      />
    </div>

    <template v-if="job">
      <div class="summary">
        <div>
          <strong>{{ job.filename }}</strong>
          <span class="muted small"> · {{ KIND_LABEL[job.kind] }} · {{ formatDateTime(job.created_at) }}</span>
        </div>
        <Tag v-if="job.status === 'applied'" value="Применён" severity="success" />
        <Tag v-else-if="job.status === 'discarded'" value="Отменён" severity="secondary" />
        <Tag v-else value="Предпросмотр" severity="info" />
        <span class="counts">
          <Tag :value="`создать ${job.summary.create ?? 0}`" severity="success" />
          <Tag :value="`изменить ${job.summary.update ?? 0}`" severity="info" />
          <Tag :value="`без изменений ${job.summary.unchanged ?? 0}`" severity="secondary" />
          <Tag :value="`ошибок ${job.summary.error ?? 0}`" :severity="errors ? 'danger' : 'secondary'" />
        </span>
      </div>
      <Message v-for="n in job.notes" :key="n" severity="warn" :closable="false">{{ n }}</Message>
      <Message v-if="pending && errors" severity="error" :closable="false">
        В файле {{ errors }} строк с ошибками. Исправьте их в файле (отчёт с подсветкой ошибок — кнопка
        «Скачать отчёт») и загрузите снова — или примените только корректные строки.
      </Message>

      <div class="filters">
        <SelectButton v-model="filter" :options="filters" option-label="label" option-value="value" :allow-empty="false" size="small" />
      </div>

      <DataTable
        :value="rows"
        data-key="row"
        lazy
        paginator
        :first="first"
        :rows="pageSize"
        :rows-per-page-options="[50, 100, 200]"
        :total-records="total"
        :loading="loading"
        scrollable
        scroll-height="flex"
        class="table"
        @page="onPage"
      >
        <template #empty>Строк нет</template>
        <Column header="Строка" style="width: 5rem">
          <template #body="{ data }">{{ data.row }}</template>
        </Column>
        <Column header="Результат" style="width: 10rem">
          <template #body="{ data }">
            <Tag :value="ACTIONS[data.action]?.label" :severity="ACTIONS[data.action]?.severity" />
            <div v-if="data.label" class="sub">{{ data.label }}</div>
          </template>
        </Column>
        <Column header="Что будет и что не так" style="min-width: 18rem">
          <template #body="{ data }">
            <ul class="issues">
              <li v-for="(e, i) in data.errors" :key="`e${i}`" class="error">{{ e.message }}</li>
              <li v-for="(w, i) in data.warnings" :key="`w${i}`" class="warn">{{ w.message }}</li>
              <li v-for="(pair, field) in data.changes" :key="field">
                {{ field }}: {{ change(pair[0]) }} → {{ change(pair[1]) }}
              </li>
            </ul>
          </template>
        </Column>
        <Column v-for="c in job.columns" :key="c.key" :header="c.title" style="min-width: 9rem">
          <template #body="{ data }">
            <span
              :class="{ bad: data.errors.some((e: { column?: string | null }) => e.column === c.key) }"
            >{{ cellText(data.values[c.key]) }}</span>
          </template>
        </Column>
      </DataTable>

      <footer class="actions">
        <Button label="Скачать отчёт" icon="pi pi-file-excel" text @click="downloadReport" />
        <span class="spacer" />
        <template v-if="pending">
          <label v-if="errors" class="check">
            <Checkbox v-model="skipInvalid" binary input-id="skip-invalid" />
            <span>Применить только корректные строки</span>
          </label>
          <Button label="Проверить заново" icon="pi pi-refresh" severity="secondary" text :loading="busy" @click="action('recheck')" />
          <Button label="Отменить" severity="secondary" text :disabled="busy" @click="action('discard')" />
          <Button
            label="Применить"
            icon="pi pi-check"
            :disabled="!canApply"
            :loading="busy"
            @click="action('apply')"
          />
        </template>
        <Button v-else label="Новый импорт" icon="pi pi-plus" text @click="reset" />
      </footer>
    </template>

    <div v-else class="history">
      <h2>Последние импорты</h2>
      <p v-if="!history.length" class="muted">Вы ещё ничего не импортировали.</p>
      <div v-for="h in history" :key="h.id" class="history-row">
        <Tag
          :value="h.status === 'applied' ? 'Применён' : h.status === 'discarded' ? 'Отменён' : 'Предпросмотр'"
          :severity="h.status === 'applied' ? 'success' : h.status === 'discarded' ? 'secondary' : 'info'"
        />
        <span>{{ KIND_LABEL[h.kind] }} · {{ h.filename }} · строк {{ h.total }}</span>
        <small class="muted">{{ formatDateTime(h.created_at) }}</small>
        <Button label="Открыть" size="small" text @click="open(h)" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0.75rem;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
h2 {
  font-size: 1.1rem;
  margin: 0.5rem 0;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.small {
  font-size: 0.85rem;
}
.toolbar,
.summary,
.actions,
.history-row,
.check {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  flex-wrap: wrap;
}
.counts {
  display: flex;
  gap: 0.35rem;
}
.hidden {
  display: none;
}
.table {
  flex: 1;
  min-height: 0;
}
.sub {
  color: var(--p-text-muted-color);
  font-size: 0.85rem;
}
.issues {
  margin: 0;
  padding-left: 1rem;
  font-size: 0.9rem;
}
.issues .error {
  color: var(--p-red-600);
}
.issues .warn {
  color: var(--p-orange-600);
}
.bad {
  background: var(--p-red-100);
  color: var(--p-red-800);
  padding: 0 0.2rem;
  border-radius: 3px;
}
.spacer {
  flex: 1;
}
.history-row small {
  flex: 1;
}
</style>
