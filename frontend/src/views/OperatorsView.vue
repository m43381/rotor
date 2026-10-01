<script setup lang="ts">
// Операторы (фаза 7a, open-questions №59): учётные записи в зоне ответственности, создание с
// временным паролем, смена роли и подразделения, блокировка, сброс пароля, завершение сессий.
// Права проверяет auth-admin; интерфейс только не предлагает недоступное.
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable, { type DataTablePageEvent } from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { ApiError, authAdmin, unwrap, type OperatorAccount, type OperatorRole } from '@/api/client'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useUnitsStore } from '@/stores/units'

const units = useUnitsStore()
const toast = useToast()
const confirm = useConfirm()

const ROLE_LABELS: Record<OperatorRole, string> = {
  superadmin: 'Суперадминистратор',
  unit_admin: 'Администратор подразделения',
  operator: 'Оператор',
  viewer: 'Наблюдатель',
}

const rows = ref<OperatorAccount[]>([])
const total = ref(0)
const first = ref(0)
const pageSize = ref(50)
const q = ref('')
const unitFilter = ref<string | null>(null)
const loading = ref(false)

const dialog = ref(false)
const editing = ref<OperatorAccount | null>(null)
const form = reactive({ username: '', last_name: '', first_name: '', role: 'operator' as OperatorRole, unit_id: null as string | null })
const roleOptions = ref<{ value: OperatorRole; label: string }[]>([])
const busy = ref(false)
const error = ref<string | null>(null)
const issued = ref<{ username: string; password: string } | null>(null)

function showError(e: unknown, fallback: string) {
  const detail = e instanceof ApiError ? e.message : fallback
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 7000 })
}

async function load() {
  loading.value = true
  try {
    const page = await unwrap(
      authAdmin.GET('/operators', {
        params: {
          query: { q: q.value || undefined, unit_id: unitFilter.value ?? undefined, limit: pageSize.value, offset: first.value },
        },
      }),
    )
    rows.value = page.items
    total.value = page.total
  } catch (e) {
    showError(e, 'Не удалось загрузить операторов')
  } finally {
    loading.value = false
  }
}

async function loadRoles(unitId: string | null) {
  roleOptions.value = []
  if (!unitId) return
  try {
    const roles = await unwrap(authAdmin.GET('/operators/roles', { params: { query: { unit_id: unitId } } }))
    roleOptions.value = roles.map((r) => ({ value: r, label: ROLE_LABELS[r] }))
    if (!roles.includes(form.role) && roles.length) form.role = roles.includes('operator') ? 'operator' : roles[0]!
  } catch {
    roleOptions.value = []
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { username: '', last_name: '', first_name: '', role: 'operator', unit_id: unitFilter.value ?? units.me?.unit.id ?? null })
  error.value = null
  dialog.value = true
  void loadRoles(form.unit_id)
}

function openEdit(o: OperatorAccount) {
  editing.value = o
  Object.assign(form, { username: o.username, last_name: o.last_name, first_name: o.first_name, role: o.role ?? 'viewer', unit_id: o.unit_id })
  error.value = null
  dialog.value = true
  void loadRoles(form.unit_id)
}

async function save() {
  if (!form.unit_id) {
    error.value = 'Выберите подразделение'
    return
  }
  busy.value = true
  error.value = null
  try {
    if (editing.value) {
      await unwrap(
        authAdmin.PATCH('/operators/{user_id}', {
          params: { path: { user_id: editing.value.id } },
          body: { last_name: form.last_name, first_name: form.first_name, role: form.role, unit_id: form.unit_id },
        }),
      )
      toast.add({ severity: 'success', summary: 'Сохранено', life: 3000 })
    } else {
      const created = await unwrap(
        authAdmin.POST('/operators', {
          body: { username: form.username, last_name: form.last_name, first_name: form.first_name, role: form.role, unit_id: form.unit_id },
        }),
      )
      issued.value = { username: created.username, password: created.temporary_password }
    }
    dialog.value = false
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : 'Не удалось сохранить'
  } finally {
    busy.value = false
  }
}

// Удалить учётную запись — только суперадминистратор (ADR-0023); в журнале изменений
// логин и ФИО остаются
const isSuperadmin = computed(() => units.me?.roles.includes('superadmin') === true)

function action(o: OperatorAccount, kind: 'block' | 'unblock' | 'reset' | 'logout' | 'delete') {
  const texts = {
    block: { header: 'Заблокировать оператора?', message: `${o.full_name} не сможет войти, открытые сессии завершатся.`, accept: 'Заблокировать' },
    unblock: { header: 'Разблокировать оператора?', message: `${o.full_name} снова сможет входить.`, accept: 'Разблокировать' },
    reset: { header: 'Сбросить пароль?', message: `Будет выдан временный пароль, при входе ${o.full_name} должен его сменить. Сессии завершатся.`, accept: 'Сбросить' },
    logout: { header: 'Завершить сессии?', message: `${o.full_name} будет выведен из системы на всех устройствах.`, accept: 'Завершить' },
    delete: {
      header: 'Удалить учётную запись?',
      message: `Учётная запись ${o.username} (${o.full_name}) будет удалена без возможности восстановления. Если нужно лишь закрыть доступ, лучше заблокировать.`,
      accept: 'Удалить',
    },
  }[kind]
  confirm.require({
    header: texts.header,
    message: texts.message,
    acceptLabel: texts.accept,
    rejectLabel: 'Отмена',
    accept: async () => {
      const path = { params: { path: { user_id: o.id } } }
      try {
        if (kind === 'reset') {
          const r = await unwrap(authAdmin.POST('/operators/{user_id}/reset-password', path))
          issued.value = { username: r.username, password: r.temporary_password }
        } else if (kind === 'block') await unwrap(authAdmin.POST('/operators/{user_id}/block', path))
        else if (kind === 'unblock') await unwrap(authAdmin.POST('/operators/{user_id}/unblock', path))
        else if (kind === 'delete') await unwrap(authAdmin.DELETE('/operators/{user_id}', path))
        else await unwrap(authAdmin.POST('/operators/{user_id}/logout', path))
        await load()
      } catch (e) {
        showError(e, 'Не удалось выполнить действие')
      }
    },
  })
}

async function copyPassword() {
  if (!issued.value) return
  await navigator.clipboard?.writeText(issued.value.password).catch(() => undefined)
  toast.add({ severity: 'info', summary: 'Пароль скопирован', life: 2000 })
}

function onPage(e: DataTablePageEvent) {
  first.value = e.first
  pageSize.value = e.rows
  void load()
}

let timer: ReturnType<typeof setTimeout> | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = setTimeout(() => {
    first.value = 0
    void load()
  }, 300)
})
watch(unitFilter, () => {
  first.value = 0
  void load()
})
watch(
  () => form.unit_id,
  (u) => {
    if (dialog.value) void loadRoles(u)
  },
)
onMounted(async () => {
  if (!units.me) await units.load().catch(() => undefined)
  await load()
})
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Операторы</h1>
        <p class="muted">
          Учётные записи операторов в вашей зоне ответственности. Новый оператор получает временный пароль и меняет его
          при первом входе. Удаления нет — только блокировка: в журналах остаётся, кто что делал.
        </p>
      </div>
      <Button label="Добавить оператора" icon="pi pi-user-plus" @click="openCreate" />
    </header>

    <div class="filters">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="q" placeholder="Логин или ФИО" aria-label="Поиск" />
      </IconField>
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitFilter" placeholder="Все подразделения" show-clear />
      </div>
      <span class="muted">Найдено: {{ total }}</span>
    </div>

    <DataTable
      :value="rows"
      data-key="id"
      lazy
      paginator
      :first="first"
      :rows="pageSize"
      :rows-per-page-options="[25, 50, 100]"
      :total-records="total"
      :loading="loading"
      scrollable
      scroll-height="flex"
      class="table"
      @page="onPage"
    >
      <template #empty>Операторов нет</template>
      <Column header="Оператор">
        <template #body="{ data }">
          <div class="name">{{ data.full_name }} <Tag v-if="data.self" value="вы" severity="secondary" /></div>
          <small class="muted">{{ data.username }}</small>
        </template>
      </Column>
      <Column header="Роль" style="width: 14rem">
        <template #body="{ data }">{{ data.role_name }}</template>
      </Column>
      <Column header="Подразделение" style="width: 16rem">
        <template #body="{ data }">{{ data.unit_name ?? '—' }}</template>
      </Column>
      <Column header="Состояние" style="width: 9rem">
        <template #body="{ data }">
          <Tag v-if="data.enabled" value="активен" severity="success" />
          <Tag v-else value="заблокирован" severity="danger" />
        </template>
      </Column>
      <Column style="width: 15rem">
        <template #body="{ data }">
          <div v-if="data.can_edit" class="row-actions">
            <Button icon="pi pi-pencil" text rounded size="small" :aria-label="`Изменить ${data.username}`" @click="openEdit(data)" />
            <Button icon="pi pi-key" text rounded size="small" :aria-label="`Сбросить пароль ${data.username}`" @click="action(data, 'reset')" />
            <Button icon="pi pi-sign-out" text rounded size="small" :aria-label="`Завершить сессии ${data.username}`" @click="action(data, 'logout')" />
            <Button
              v-if="data.enabled"
              icon="pi pi-lock"
              text
              rounded
              size="small"
              severity="danger"
              :aria-label="`Заблокировать ${data.username}`"
              @click="action(data, 'block')"
            />
            <Button
              v-else
              icon="pi pi-lock-open"
              text
              rounded
              size="small"
              :aria-label="`Разблокировать ${data.username}`"
              @click="action(data, 'unblock')"
            />
            <Button
              v-if="isSuperadmin"
              v-tooltip.left="'Удалить учётную запись'"
              icon="pi pi-trash"
              text
              rounded
              size="small"
              severity="danger"
              :aria-label="`Удалить ${data.username}`"
              @click="action(data, 'delete')"
            />
          </div>
        </template>
      </Column>
    </DataTable>

    <Dialog v-model:visible="dialog" :header="editing ? 'Изменить оператора' : 'Новый оператор'" modal :style="{ width: '32rem' }">
      <div class="form">
        <label class="field">
          <span>Логин</span>
          <InputText id="op-username" v-model="form.username" :disabled="!!editing" placeholder="ivanov.p" />
          <small v-if="!editing" class="muted">Латинские буквы, цифры, точка, дефис, подчёркивание</small>
        </label>
        <label class="field">
          <span>Фамилия</span>
          <InputText id="op-last" v-model="form.last_name" />
        </label>
        <label class="field">
          <span>Имя</span>
          <InputText id="op-first" v-model="form.first_name" />
        </label>
        <label class="field">
          <span>Подразделение</span>
          <UnitTreeSelect v-model="form.unit_id" input-id="op-unit" />
        </label>
        <label class="field">
          <span>Роль</span>
          <Select v-model="form.role" :options="roleOptions" option-label="label" option-value="value" input-id="op-role" />
          <small class="muted">Список ограничен ролями, которые вы можете выдать в этом подразделении</small>
        </label>
        <Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
        <div class="actions">
          <Button label="Отмена" severity="secondary" text @click="dialog = false" />
          <Button :label="editing ? 'Сохранить' : 'Создать'" icon="pi pi-check" :loading="busy" @click="save" />
        </div>
      </div>
    </Dialog>

    <Dialog :visible="!!issued" header="Временный пароль" modal :closable="false" :style="{ width: '30rem' }">
      <template v-if="issued">
        <p>
          Передайте оператору <strong>{{ issued.username }}</strong> временный пароль. Он показывается один раз; при
          первом входе система попросит задать свой.
        </p>
        <div class="password">
          <code data-testid="temporary-password">{{ issued.password }}</code>
          <Button icon="pi pi-copy" text rounded aria-label="Скопировать пароль" @click="copyPassword" />
        </div>
        <div class="actions">
          <Button label="Готово" @click="issued = null" />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 0.75rem;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.page-header > :deep(.p-button) {
  flex-shrink: 0;
  white-space: nowrap;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
}
.filters {
  display: flex;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
}
.unit-filter {
  width: 22rem;
  max-width: 100%;
}
.table {
  flex: 1;
  min-height: 0;
}
.name {
  font-weight: 600;
  display: flex;
  gap: 0.4rem;
  align-items: center;
}
.row-actions {
  display: flex;
  gap: 0.1rem;
}
.form {
  display: grid;
  gap: 0.75rem;
}
.field {
  display: grid;
  gap: 0.25rem;
}
.field span {
  font-weight: 600;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.password {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.password code {
  font-size: 1.3rem;
  padding: 0.3rem 0.6rem;
  background: var(--p-content-hover-background);
  border-radius: 4px;
  letter-spacing: 1px;
}
</style>
