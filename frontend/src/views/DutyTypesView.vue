<script setup lang="ts">
// Наряды и роли: свои и своего поддерева (можно менять), а также вышестоящих подразделений
// (только просмотр: их роли могут прийти по делегированию). Наряды сгруппированы по владельцу,
// роли видны сразу: кто заступает (закрепление, категория, ADR-0018) и требования (ADR-0009).
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Skeleton from 'primevue/skeleton'
import Tag from 'primevue/tag'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  ApiError,
  scheduling,
  unwrap,
  type DutyRole,
  type DutyRoleIn,
  type DutyType,
  type DutyTypeCreate,
  type DutyTypeUpdate,
} from '@/api/client'
import DutyRoleDialog from '@/components/DutyRoleDialog.vue'
import DutyTypeDialog from '@/components/DutyTypeDialog.vue'
import UnitTreeSelect from '@/components/UnitTreeSelect.vue'
import { useRefsStore } from '@/stores/refs'
import { useUnitsStore } from '@/stores/units'
import { formatDuration, formatInterval, roleChips } from '@/utils/duty'

const units = useUnitsStore()
const refs = useRefsStore()
const toast = useToast()
const router = useRouter()

const types = ref<DutyType[]>([])
const loading = ref(false)
const busy = ref(false)
const unitId = ref<string | null>(null)
const includeInactive = ref(false)
const search = ref('')
// Пустое состояние — только после первой загрузки, иначе оно мелькает до ответа сервиса
const loaded = ref(false)

const canCreate = computed(() => (units.me?.roles ?? []).some((r) => r !== 'viewer'))

async function load() {
  loading.value = true
  try {
    types.value = await unwrap(
      scheduling.GET('/duty-types', {
        params: { query: { unit_id: unitId.value ?? undefined, include_inactive: includeInactive.value } },
      }),
    )
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
    loaded.value = true
  }
}
watch([unitId, includeInactive], load)
onMounted(async () => {
  await Promise.all([units.me ? Promise.resolve() : units.load(), refs.ensure()]).catch(showError)
  await load()
})

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

function replace(updated: DutyType) {
  const i = types.value.findIndex((t) => t.id === updated.id)
  if (i >= 0) types.value[i] = updated
  else types.value.push(updated)
}

async function run(action: () => Promise<DutyType>, success: string): Promise<boolean> {
  busy.value = true
  try {
    const t = await action()
    replace(t)
    toast.add({ severity: 'success', summary: success, life: 3000 })
    return true
  } catch (e) {
    showError(e)
    if (e instanceof ApiError && e.status === 409) await load()
    return false
  } finally {
    busy.value = false
  }
}

const people = (t: DutyType) => t.roles.filter((r) => r.is_active).reduce((n, r) => n + r.headcount, 0)
const chips = (r: DutyRole) => roleChips(r, refs)
const sortedRoles = (t: DutyType) =>
  [...t.roles].sort((a, b) => Number(b.is_active) - Number(a.is_active) || a.sort_order - b.sort_order)

// Наряды группами по подразделению-владельцу: сначала вышестоящие, затем свои и нижестоящие
const groups = computed(() => {
  const q = search.value.trim().toLowerCase()
  const visible = types.value.filter(
    (t) =>
      !q ||
      t.name.toLowerCase().includes(q) ||
      t.roles.some((r) => r.name.toLowerCase().includes(q)) ||
      (t.owner_unit_name ?? '').toLowerCase().includes(q),
  )
  const byOwner = new Map<string, DutyType[]>()
  for (const t of visible) {
    const list = byOwner.get(t.owner_unit_id) ?? []
    list.push(t)
    byOwner.set(t.owner_unit_id, list)
  }
  const depth = (id: string) => (units.byId.get(id)?.path ?? '').split('.').length
  return [...byOwner.entries()]
    .map(([ownerId, list]) => ({
      ownerId,
      name: list[0]?.owner_unit_name ?? '—',
      upper: list.every((t) => !t.can_edit),
      types: [...list].sort((a, b) => a.name.localeCompare(b.name, 'ru')),
    }))
    .sort((a, b) => depth(a.ownerId) - depth(b.ownerId) || a.name.localeCompare(b.name, 'ru'))
})

// --- тип наряда -------------------------------------------------------------------------------
const typeVisible = ref(false)
const editingType = ref<DutyType | null>(null)

function openType(t: DutyType | null) {
  editingType.value = t
  typeVisible.value = true
}

async function onCreate(value: DutyTypeCreate) {
  const ok = await run(() => unwrap(scheduling.POST('/duty-types', { body: value })), 'Наряд создан')
  if (ok) typeVisible.value = false
}

async function onUpdate(value: DutyTypeUpdate) {
  const t = editingType.value
  if (!t) return
  const ok = await run(
    () => unwrap(scheduling.PUT('/duty-types/{type_id}', { params: { path: { type_id: t.id } }, body: value })),
    'Наряд изменён',
  )
  if (ok) {
    typeVisible.value = false
    if (!value.is_active && !includeInactive.value) types.value = types.value.filter((x) => x.id !== t.id)
  }
}

// --- роли -------------------------------------------------------------------------------------
const roleVisible = ref(false)
const roleType = ref<DutyType | null>(null)
const editingRole = ref<DutyRole | null>(null)

function openRole(t: DutyType, r: DutyRole | null) {
  roleType.value = t
  editingRole.value = r
  roleVisible.value = true
}

async function onRole(value: DutyRoleIn) {
  const t = roleType.value
  const r = editingRole.value
  if (!t) return
  const ok = await run(
    () =>
      r
        ? unwrap(
            scheduling.PUT('/duty-roles/{role_id}', {
              params: { path: { role_id: r.id } },
              body: { ...value, version: r.version },
            }),
          )
        : unwrap(
            scheduling.POST('/duty-types/{type_id}/roles', {
              params: { path: { type_id: t.id } },
              body: { ...value, sort_order: t.roles.length },
            }),
          ),
    r ? 'Роль изменена' : 'Роль добавлена',
  )
  if (ok) roleVisible.value = false
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Наряды и роли</h1>
        <p class="muted">
          Из каких ролей состоит наряд, сколько людей нужно и кто может заступать: закрепление за
          подразделением, категория личного состава, звание и другие требования.
        </p>
      </div>
      <div class="actions">
        <Button
          label="Лимиты нарядов"
          icon="pi pi-sliders-h"
          severity="secondary"
          text
          @click="router.push('/duty-limits')"
        />
        <Button v-if="canCreate" label="Новый наряд" icon="pi pi-plus" @click="openType(null)" />
      </div>
    </header>

    <div class="filters">
      <div class="unit-filter">
        <UnitTreeSelect v-model="unitId" placeholder="Касаются подразделения…" show-clear />
      </div>
      <IconField class="search">
        <InputIcon class="pi pi-search" />
        <InputText v-model="search" placeholder="Поиск по наряду или роли" aria-label="Поиск" />
      </IconField>
      <label class="check">
        <Checkbox v-model="includeInactive" binary input-id="inactive" />
        <span>Показывать выведенные из действия</span>
      </label>
    </div>

    <div class="legend" aria-label="Обозначения">
      <span class="chip chip--unit"><i class="pi pi-map-marker" /> закреплена за подразделением</span>
      <span class="chip chip--category"><i class="pi pi-users" /> категория личного состава</span>
      <span class="chip chip--rank"><i class="pi pi-star" /> звание не ниже</span>
      <span class="chip"><i class="pi pi-tag" /> другие требования</span>
    </div>

    <div v-if="!loaded || (loading && !types.length)" class="list">
      <Skeleton v-for="i in 3" :key="i" height="9rem" border-radius="10px" />
    </div>
    <div v-else-if="!groups.length" class="card empty-state">
      <i class="pi pi-shield" />
      <strong>{{ search ? 'Ничего не найдено' : 'Нарядов пока нет' }}</strong>
      <span v-if="!search">
        Создайте наряд, задайте время и состав по ролям — после этого он появится в графиках.
      </span>
      <Button v-if="canCreate && !search" label="Новый наряд" icon="pi pi-plus" @click="openType(null)" />
    </div>
    <div v-else class="list">
      <section v-for="g in groups" :key="g.ownerId" class="group">
        <h2 class="group-title">
          <i class="pi pi-sitemap" /> {{ g.name }}
          <Tag v-if="g.upper" value="вышестоящее — только просмотр" severity="info" />
        </h2>
        <article v-for="t in g.types" :key="t.id" class="card duty" :class="{ inactive: !t.is_active }">
          <header class="duty-head">
            <div class="duty-title">
              <span class="name">{{ t.name }}</span>
              <span v-if="t.short_name" class="short">{{ t.short_name }}</span>
              <Tag v-if="!t.is_active" value="Не действует" severity="secondary" />
            </div>
            <div class="duty-meta">
              <span v-tooltip.top="'Время наряда'">
                <i class="pi pi-clock" /> {{ formatInterval(t.start_time, t.duration_minutes) }}
              </span>
              <span v-tooltip.top="'Длительность и обязательный отдых после наряда'">
                <i class="pi pi-hourglass" /> {{ formatDuration(t.duration_minutes) }}, отдых {{ t.rest_hours }} ч
              </span>
              <span v-tooltip.top="'Человек в сутки по действующим ролям'">
                <i class="pi pi-user" /> {{ people(t) }} чел.
              </span>
            </div>
            <Button
              v-if="t.can_edit"
              icon="pi pi-pencil"
              text
              rounded
              severity="secondary"
              aria-label="Изменить наряд"
              @click="openType(t)"
            />
          </header>
          <ul class="roles">
            <li v-for="r in sortedRoles(t)" :key="r.id" class="role" :class="{ inactive: !r.is_active }">
              <span class="role-name">
                {{ r.name }} <span class="count">×{{ r.headcount }}</span>
                <span
                  v-tooltip.top="'Вес нагрузки роли: нарядо-сутки × вес'"
                  class="weight"
                  :class="{ heavy: r.load_weight > 1, light: r.load_weight < 1 }"
                >
                  вес {{ r.load_weight.toLocaleString('ru-RU') }}
                </span>
                <Tag v-if="!r.is_active" value="Не действует" severity="secondary" class="tag" />
              </span>
              <span class="chips">
                <span
                  v-for="(c, i) in chips(r)"
                  :key="i"
                  v-tooltip.top="c.hint"
                  class="chip"
                  :class="c.kind !== 'req' ? `chip--${c.kind}` : ''"
                >
                  <i :class="c.icon" /> {{ c.text }}
                </span>
                <span v-if="!chips(r).length" class="none">любой из личного состава с допуском</span>
              </span>
              <Button
                v-if="t.can_edit"
                icon="pi pi-pencil"
                text
                rounded
                size="small"
                severity="secondary"
                :aria-label="`Изменить роль ${r.name}`"
                @click="openRole(t, r)"
              />
            </li>
          </ul>
          <Button
            v-if="t.can_edit"
            label="Добавить роль"
            icon="pi pi-plus"
            text
            size="small"
            class="add-role"
            @click="openRole(t, null)"
          />
        </article>
      </section>
    </div>

    <DutyTypeDialog
      v-model:visible="typeVisible"
      :duty-type="editingType"
      :busy="busy"
      :default-owner-id="unitId ?? units.me?.unit.id ?? null"
      @create="onCreate"
      @update="onUpdate"
    />
    <DutyRoleDialog
      v-model:visible="roleVisible"
      :role="editingRole"
      :busy="busy"
      :owner-unit-id="roleType?.owner_unit_id ?? null"
      :title="editingRole ? `Роль: ${editingRole.name}` : `Новая роль — ${roleType?.name ?? ''}`"
      @submit="onRole"
    />
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 90rem;
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}
h1 {
  margin: 0;
  font-size: 1.4rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0.25rem 0 0;
  max-width: 52rem;
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
.search :deep(input) {
  width: 18rem;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  opacity: 0.85;
}
.list {
  display: grid;
  gap: 1.1rem;
}
.group {
  display: grid;
  gap: 0.6rem;
}
.group-title {
  margin: 0;
  font-size: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--p-text-muted-color);
}
.tag {
  margin-left: 0.25rem;
}
.duty {
  display: grid;
  gap: 0.5rem;
  padding: 0.8rem 1rem 0.6rem;
}
.duty.inactive {
  opacity: 0.6;
}
.duty-head {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.duty-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 14rem;
}
.name {
  font-weight: 700;
  font-size: 1.05rem;
}
.short {
  color: var(--p-text-muted-color);
  font-size: 0.85rem;
  border: 1px solid var(--app-border);
  border-radius: 6px;
  padding: 0 0.35rem;
}
.duty-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1rem;
  color: var(--p-text-muted-color);
  font-size: 0.9rem;
}
.duty-meta .pi {
  font-size: 0.8rem;
  margin-right: 0.15rem;
}
.roles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
}
.role {
  display: grid;
  grid-template-columns: minmax(14rem, 24rem) 1fr auto;
  align-items: center;
  gap: 0.75rem;
  padding: 0.45rem 0.25rem;
  border-top: 1px solid var(--app-border);
}
.role.inactive {
  opacity: 0.55;
}
.role-name {
  font-weight: 600;
}
.count {
  color: var(--p-text-muted-color);
  font-weight: 400;
}
.weight {
  margin-left: 0.4rem;
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--p-text-muted-color);
  font-variant-numeric: tabular-nums;
}
.weight.heavy {
  color: var(--chip-warn-fg);
}
.weight.light {
  color: var(--chip-unit-fg);
}
.none {
  color: var(--p-text-muted-color);
  font-size: 0.85rem;
}
.add-role {
  justify-self: start;
}
</style>
