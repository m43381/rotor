<script setup lang="ts">
// Панель ячейки (фаза 3b): кто назначен и кандидаты — люди поддерева исполнителя с допуском
// к роли (фаза 7d), с причинами непригодности и нагрузкой за месяц. Нарушение отдыха или лимита — с подтверждением
// и комментарием (ADR-0008, open-questions №38); остальное назначить нельзя.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Dialog from 'primevue/dialog'
import Drawer from 'primevue/drawer'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'

import { ApiError, scheduling, unwrap, type Candidate, type Candidates, type SchedViolation } from '@/api/client'
import { formatDate, formatDateTime } from '@/utils/dates'

const props = defineProps<{ cellId: string | null }>()
const visible = defineModel<boolean>('visible', { required: true })
const emit = defineEmits<{ changed: [] }>()
const toast = useToast()

const data = ref<Candidates | null>(null)
const loading = ref(false)
const busy = ref(false)
const onlyEligible = ref(true)
const query = ref('')

watch([visible, () => props.cellId], async ([open, id]) => {
  if (!open || !id) return
  query.value = ''
  // Не показывать данные предыдущей ячейки, пока грузится новая
  data.value = null
  loading.value = true
  try {
    data.value = await unwrap(
      scheduling.GET('/day-plans/{day_plan_id}/candidates', { params: { path: { day_plan_id: id } } }),
    )
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
})

function showError(e: unknown) {
  const detail = e instanceof ApiError ? e.message : 'Не удалось выполнить операцию'
  toast.add({ severity: 'error', summary: 'Ошибка', detail, life: 6000 })
}

const full = computed(() => !!data.value && data.value.assigned.length >= data.value.cell.headcount)
const visibleCandidates = computed(() => {
  const q = query.value.trim().toLowerCase()
  return (data.value?.candidates ?? []).filter(
    (c) => (!onlyEligible.value || c.eligible) && (!q || c.name.toLowerCase().includes(q)),
  )
})

async function call(action: () => Promise<Candidates>, success: string): Promise<boolean> {
  busy.value = true
  try {
    data.value = await action()
    toast.add({ severity: 'success', summary: success, life: 2500 })
    emit('changed')
    return true
  } catch (e) {
    if (e instanceof ApiError && e.code === 'override_required') {
      pending.value = { candidate: current.value, violations: violationsOf(e) }
      comment.value = ''
      return false
    }
    showError(e)
    return false
  } finally {
    busy.value = false
  }
}

function violationsOf(e: ApiError): SchedViolation[] {
  return ((e.details as { violations?: SchedViolation[] } | undefined)?.violations ?? [])
}

// Подтверждение нарушения отдыха или лимита
const current = ref<Candidate | null>(null)
const pending = ref<{ candidate: Candidate | null; violations: SchedViolation[] } | null>(null)
const comment = ref('')

function assign(c: Candidate, confirmOverride = false) {
  const id = props.cellId
  if (!id) return
  current.value = c
  return call(
    () =>
      unwrap(
        scheduling.POST('/day-plans/{day_plan_id}/assignments', {
          params: { path: { day_plan_id: id } },
          body: {
            person_id: c.person_id,
            confirm_override: confirmOverride,
            override_comment: confirmOverride ? comment.value.trim() : null,
          },
        }),
      ),
    'Назначен',
  )
}

async function confirmOverride() {
  const c = pending.value?.candidate
  if (!c) return
  if (await assign(c, true)) pending.value = null
}

function remove(id: string) {
  return call(
    () => unwrap(scheduling.DELETE('/assignments/{assignment_id}', { params: { path: { assignment_id: id } } })),
    'Снят с наряда',
  )
}

function pin(id: string, pinned: boolean) {
  return call(
    () =>
      unwrap(
        scheduling.POST('/assignments/{assignment_id}/pin', {
          params: { path: { assignment_id: id } },
          body: { pinned },
        }),
      ),
    pinned ? 'Закреплён' : 'Закрепление снято',
  )
}
</script>

<template>
  <Drawer
    v-model:visible="visible"
    position="right"
    class="cell-panel"
    :header="data ? data.cell.role_name : 'Ячейка'"
    :pt="{ root: { style: 'width: 44rem; max-width: 100vw' } }"
  >
    <template v-if="data">
      <p class="muted">
        {{ data.cell.duty_type_name }} · {{ formatDate(data.cell.date) }} ·
        {{ formatDateTime(data.cell.start_at) }} — {{ formatDateTime(data.cell.end_at) }}
      </p>

      <h3>Назначены ({{ data.assigned.length }} из {{ data.cell.headcount }})</h3>
      <p v-if="!data.assigned.length" class="muted">Никто не назначен</p>
      <div v-for="a in data.assigned" :key="a.id" class="assigned">
        <div class="who">
          <strong>{{ a.person_name }}</strong>
          <Tag v-if="a.rest_override" value="Отдых нарушен" severity="warn" />
          <Tag v-if="a.limit_override" value="Сверх лимита" severity="warn" />
          <Tag v-if="a.after_publish" value="После публикации" severity="info" />
          <Tag v-if="a.is_pinned" value="Закреплён" severity="secondary" />
          <div v-if="a.override_comment" class="muted small">Обоснование: {{ a.override_comment }}</div>
          <div v-if="a.conflict" class="conflict small"><i class="pi pi-exclamation-triangle" /> {{ a.conflict }}</div>
        </div>
        <template v-if="data.cell.can_assign">
          <Button
            :icon="a.is_pinned ? 'pi pi-lock-open' : 'pi pi-lock'"
            text
            rounded
            severity="secondary"
            :aria-label="a.is_pinned ? 'Открепить' : 'Закрепить'"
            @click="pin(a.id, !a.is_pinned)"
          />
          <Button icon="pi pi-times" text rounded severity="danger" :aria-label="`Снять ${a.person_name}`" @click="remove(a.id)" />
        </template>
      </div>

      <template v-if="data.cell.can_assign">
        <h3>Кандидаты</h3>
        <Message v-if="full" severity="success" :closable="false">Роль укомплектована.</Message>
        <div class="filters">
          <InputText v-model="query" placeholder="Поиск по ФИО" aria-label="Поиск кандидата" />
          <label class="check">
            <Checkbox v-model="onlyEligible" binary input-id="only-eligible" />
            <span>Только пригодные</span>
          </label>
        </div>
        <DataTable :value="visibleCandidates" data-key="person_id" size="small" :loading="loading" scrollable scroll-height="50vh">
          <template #empty>Подходящих людей нет: в списке только люди с допуском к этой роли</template>
          <Column header="Человек">
            <template #body="{ data: c }">
              <div class="name">{{ c.name }}</div>
              <small class="muted">{{ c.rank_name }} · {{ c.unit_name }}</small>
              <ul v-if="c.violations.length" class="violations">
                <li v-for="v in c.violations" :key="v.message" :class="{ soft: v.overridable }">{{ v.message }}</li>
              </ul>
            </template>
          </Column>
          <Column header="В месяце" style="width: 6rem">
            <template #body="{ data: c }">
              {{ c.month_total }}<small v-if="c.month_holiday" class="muted"> ({{ c.month_holiday }} вых.)</small>
              <div v-if="c.last_duty" class="muted small">посл. {{ formatDate(c.last_duty) }}</div>
            </template>
          </Column>
          <Column style="width: 7.5rem">
            <template #body="{ data: c }">
              <Button
                label="Назначить"
                size="small"
                :severity="c.violations.length ? 'warn' : undefined"
                :disabled="!c.eligible || full || busy"
                :aria-label="`Назначить ${c.name}`"
                @click="assign(c)"
              />
            </template>
          </Column>
        </DataTable>
      </template>
      <Message v-else severity="secondary" :closable="false">
        Назначать людей в эту ячейку может только её исполнитель.
      </Message>
    </template>

    <Dialog
      :visible="!!pending"
      header="Назначить с нарушением?"
      modal
      :style="{ width: '32rem' }"
      @update:visible="(v: boolean) => !v && (pending = null)"
    >
      <div class="dialog">
        <Message severity="warn" :closable="false">
          <ul class="plain">
            <li v-for="v in pending?.violations ?? []" :key="v.message">{{ v.message }}</li>
          </ul>
          Назначение возможно с обоснованием — оно попадёт в журнал.
        </Message>
        <label for="ov-comment">Обоснование (обязательно)</label>
        <Textarea id="ov-comment" v-model="comment" rows="2" maxlength="2000" auto-resize />
        <div class="dialog-actions">
          <Button label="Отмена" severity="secondary" text @click="pending = null" />
          <Button label="Назначить с нарушением" severity="warn" :disabled="!comment.trim()" :loading="busy" @click="confirmOverride" />
        </div>
      </div>
    </Dialog>
  </Drawer>
</template>

<style scoped>
h3 {
  margin: 1rem 0 0.5rem;
  font-size: 1rem;
}
.muted {
  color: var(--p-text-muted-color);
  margin: 0;
}
.small {
  font-size: 0.85rem;
}
.assigned {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--p-content-border-color);
}
.who {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}
.who > div {
  flex-basis: 100%;
}
.conflict {
  color: var(--p-orange-600);
}
.filters {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
.check {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
}
.name {
  font-weight: 600;
}
.violations {
  margin: 0.2rem 0 0;
  padding-left: 1rem;
  font-size: 0.8rem;
  color: var(--p-red-600);
}
.violations .soft {
  color: var(--p-orange-600);
}
.dialog {
  display: grid;
  gap: 0.5rem;
}
.dialog label {
  font-weight: 600;
}
.plain {
  margin: 0 0 0.5rem;
  padding-left: 1.1rem;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
