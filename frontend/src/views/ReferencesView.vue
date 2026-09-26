<script setup lang="ts">
// Справочники личного состава (суперадминистратор): должности, характеристики, причины
// освобождений. Записи не удаляются, а выключаются — на них ссылаются люди и история.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import TabPanel from 'primevue/tabpanel'
import TabPanels from 'primevue/tabpanels'
import Tabs from 'primevue/tabs'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref } from 'vue'

import { ApiError, personnel, unwrap } from '@/api/client'
import { useRefsStore } from '@/stores/refs'

type Kind = 'positions' | 'attributes' | 'reasons'

const refs = useRefsStore()
const toast = useToast()
const tab = ref<Kind>('positions')
const busy = ref(false)

const TYPES = [
  { value: 'string', label: 'Строка' },
  { value: 'int', label: 'Целое число' },
  { value: 'bool', label: 'Да/нет' },
  { value: 'enum', label: 'Перечисление' },
  { value: 'date', label: 'Дата' },
]
const typeLabel = (v: string) => TYPES.find((t) => t.value === v)?.label ?? v

onMounted(() => refs.reload().catch(showError))

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

// --- универсальный диалог ------------------------------------------------------------------------
const visible = ref(false)
const kind = ref<Kind>('positions')
const editId = ref<string | null>(null)
const form = ref({
  name: '',
  code: '',
  sort_order: 0,
  is_active: true,
  value_type: 'string',
  enum_text: '',
  is_required: false,
})

function open(k: Kind, item?: Record<string, unknown>) {
  kind.value = k
  editId.value = (item?.id as string | undefined) ?? null
  form.value = {
    name: (item?.name as string) ?? '',
    code: (item?.code as string) ?? '',
    sort_order: (item?.sort_order as number) ?? 0,
    is_active: (item?.is_active as boolean) ?? true,
    value_type: (item?.value_type as string) ?? 'string',
    enum_text: ((item?.enum_options as string[] | null) ?? []).join('\n'),
    is_required: (item?.is_required as boolean) ?? false,
  }
  visible.value = true
}

const dialogTitle = computed(() => {
  const what = { positions: 'должность', attributes: 'характеристику', reasons: 'причину освобождения' }[kind.value]
  return `${editId.value ? 'Изменить' : 'Добавить'} ${what}`
})
const needsCode = computed(() => kind.value !== 'positions')
const codeValid = computed(() => !needsCode.value || /^[a-z][a-z0-9_]*$/.test(form.value.code))
const valid = computed(() => form.value.name.trim().length > 0 && codeValid.value)

async function submit() {
  const f = form.value
  busy.value = true
  try {
    if (kind.value === 'positions') {
      const body = { name: f.name.trim(), sort_order: f.sort_order, is_active: f.is_active }
      await unwrap(
        editId.value
          ? personnel.PUT('/positions/{item_id}', { params: { path: { item_id: editId.value } }, body })
          : personnel.POST('/positions', { body }),
      )
    } else if (kind.value === 'attributes') {
      const body = {
        code: f.code,
        name: f.name.trim(),
        value_type: f.value_type as 'string' | 'int' | 'bool' | 'enum' | 'date',
        enum_options:
          f.value_type === 'enum'
            ? f.enum_text.split('\n').map((s) => s.trim()).filter(Boolean)
            : null,
        is_required: f.is_required,
        sort_order: f.sort_order,
        is_active: f.is_active,
      }
      await unwrap(
        editId.value
          ? personnel.PUT('/attribute-definitions/{item_id}', { params: { path: { item_id: editId.value } }, body })
          : personnel.POST('/attribute-definitions', { body }),
      )
    } else {
      const body = { code: f.code, name: f.name.trim(), is_active: f.is_active }
      await unwrap(
        editId.value
          ? personnel.PUT('/exemption-reasons/{item_id}', { params: { path: { item_id: editId.value } }, body })
          : personnel.POST('/exemption-reasons', { body }),
      )
    }
    visible.value = false
    await refs.reload()
    toast.add({ severity: 'success', summary: 'Сохранено', life: 3000 })
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="page">
    <h1>Справочники личного состава</h1>
    <Tabs v-model:value="tab">
      <TabList>
        <Tab value="positions">Должности</Tab>
        <Tab value="attributes">Характеристики</Tab>
        <Tab value="reasons">Причины освобождений</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="positions">
          <Button label="Добавить" icon="pi pi-plus" class="add" @click="open('positions')" />
          <DataTable :value="refs.positions" data-key="id">
            <Column field="name" header="Должность" />
            <Column field="sort_order" header="Порядок" style="width: 8rem" />
            <Column header="Статус" style="width: 9rem">
              <template #body="{ data }"><Tag v-if="!data.is_active" value="Выключена" severity="secondary" /></template>
            </Column>
            <Column style="width: 4rem">
              <template #body="{ data }">
                <Button icon="pi pi-pencil" text rounded aria-label="Изменить" @click="open('positions', data)" />
              </template>
            </Column>
          </DataTable>
        </TabPanel>
        <TabPanel value="attributes">
          <Button label="Добавить" icon="pi pi-plus" class="add" @click="open('attributes')" />
          <DataTable :value="refs.attributes" data-key="id">
            <Column field="name" header="Характеристика" />
            <Column field="code" header="Код" style="width: 10rem" />
            <Column header="Тип" style="width: 10rem">
              <template #body="{ data }">{{ typeLabel(data.value_type) }}</template>
            </Column>
            <Column header="Варианты">
              <template #body="{ data }">{{ (data.enum_options ?? []).join(', ') }}</template>
            </Column>
            <Column header="" style="width: 12rem">
              <template #body="{ data }">
                <Tag v-if="data.is_required" value="Обязательная" />
                <Tag v-if="!data.is_active" value="Выключена" severity="secondary" />
              </template>
            </Column>
            <Column style="width: 4rem">
              <template #body="{ data }">
                <Button icon="pi pi-pencil" text rounded aria-label="Изменить" @click="open('attributes', data)" />
              </template>
            </Column>
          </DataTable>
        </TabPanel>
        <TabPanel value="reasons">
          <Button label="Добавить" icon="pi pi-plus" class="add" @click="open('reasons')" />
          <DataTable :value="refs.reasons" data-key="id">
            <Column field="name" header="Причина" />
            <Column field="code" header="Код" style="width: 10rem" />
            <Column header="Статус" style="width: 9rem">
              <template #body="{ data }"><Tag v-if="!data.is_active" value="Выключена" severity="secondary" /></template>
            </Column>
            <Column style="width: 4rem">
              <template #body="{ data }">
                <Button icon="pi pi-pencil" text rounded aria-label="Изменить" @click="open('reasons', data)" />
              </template>
            </Column>
          </DataTable>
        </TabPanel>
      </TabPanels>
    </Tabs>

    <Dialog v-model:visible="visible" :header="dialogTitle" modal :style="{ width: '32rem' }">
      <form class="form" @submit.prevent="submit">
        <label for="r-name">Название</label>
        <InputText id="r-name" v-model="form.name" maxlength="200" autofocus />
        <template v-if="needsCode">
          <label for="r-code">Код (латиница, для интеграций)</label>
          <InputText id="r-code" v-model="form.code" maxlength="50" :disabled="!!editId" :invalid="!codeValid" />
        </template>
        <template v-if="kind === 'attributes'">
          <label for="r-type">Тип значения</label>
          <Select
            id="r-type"
            v-model="form.value_type"
            :options="TYPES"
            option-label="label"
            option-value="value"
            :disabled="!!editId"
          />
          <template v-if="form.value_type === 'enum'">
            <label for="r-enum">Варианты (по одному в строке)</label>
            <Textarea id="r-enum" v-model="form.enum_text" rows="4" auto-resize />
          </template>
          <label class="inline"><Checkbox v-model="form.is_required" binary /> Обязательная</label>
        </template>
        <template v-if="kind !== 'reasons'">
          <label for="r-order">Порядок</label>
          <InputNumber id="r-order" v-model="form.sort_order" :min="0" :max="10000" />
        </template>
        <label class="inline"><Checkbox v-model="form.is_active" binary /> Используется</label>
        <div class="actions">
          <Button label="Отмена" severity="secondary" text @click="visible = false" />
          <Button type="submit" label="Сохранить" :disabled="!valid" :loading="busy" />
        </div>
      </form>
    </Dialog>
  </section>
</template>

<style scoped>
.page {
  max-width: 64rem;
}
h1 {
  margin: 0 0 1rem;
  font-size: 1.4rem;
}
.add {
  margin-bottom: 0.75rem;
}
.form {
  display: grid;
  gap: 0.5rem;
}
.form label {
  font-weight: 600;
  margin-top: 0.4rem;
}
.form .inline {
  display: inline-flex;
  gap: 0.5rem;
  align-items: center;
  font-weight: normal;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}
</style>
