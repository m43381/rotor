<script setup lang="ts">
// Предпросмотр автораспределения (фаза 4b): сводка, дефициты с объяснением, объяснение решения
// по выбранной ячейке (признаки, альтернативы, отсев). Применить или отменить.
import Button from 'primevue/button'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import { computed } from 'vue'

import type { Decision, Run } from '@/api/client'
import { featureRows, rejectedText, RUN_STATUS } from '@/utils/allocation'
import { formatDate } from '@/utils/dates'

const props = defineProps<{ run: Run; decisions: Decision[]; busy: boolean; stale: boolean }>()
const emit = defineEmits<{ apply: []; discard: []; close: []; recalc: [] }>()

const m = computed(() => props.run.metrics as Record<string, unknown>)
const num = (key: string) => Number(m.value[key] ?? 0)
const fairness = computed(() => (m.value.fairness ?? {}) as Record<string, number>)
const deficits = computed(() => (m.value.deficits ?? []) as { message: string }[])
const unfilled = computed(() => (m.value.unfilled ?? []) as { message: string; missing: number }[])
const removed = computed(() => ((m.value.removed ?? []) as string[]).length)
const pending = computed(() => props.run.status === 'preview_ready')
</script>

<template>
  <aside class="panel">
    <header>
      <div>
        <strong>Предпросмотр: {{ run.kind === 'people' ? 'люди' : 'подразделения' }}</strong>
        <Tag :value="RUN_STATUS[run.status]?.label" :severity="RUN_STATUS[run.status]?.severity" />
      </div>
      <Button icon="pi pi-times" text rounded severity="secondary" aria-label="Закрыть предпросмотр" @click="emit('close')" />
    </header>

    <Message v-if="stale" severity="warn" :closable="false">
      После расчёта данные изменились. Применять этот предпросмотр нельзя — пересчитайте.
      <Button label="Пересчитать" size="small" class="inline" @click="emit('recalc')" />
    </Message>

    <div class="summary">
      <div>
        <span class="big">{{ num('filled') }}</span> из {{ num('places') }}
        <small>{{ run.kind === 'people' ? 'мест закрыто' : 'ячеек передано' }}</small>
      </div>
      <div v-if="num('shortage')">
        <span class="big warn">{{ num('shortage') }}</span>
        <small>не закрыто</small>
      </div>
      <div v-if="m.upper_bound !== null && m.upper_bound !== undefined">
        <span class="big">{{ num('upper_bound') }}</span>
        <small>можно закрыть максимум</small>
      </div>
      <div v-if="removed">
        <span class="big">{{ removed }}</span>
        <small>автоматических назначений будет заменено</small>
      </div>
    </div>
    <p class="muted small">
      Справедливость нагрузки: Джини {{ fairness.gini ?? '—' }}, Джайн {{ fairness.jain ?? '—' }},
      размах {{ fairness.range ?? '—' }} (по {{ fairness.people ?? 0 }} допущенным).
    </p>

    <details v-if="deficits.length" open>
      <summary>Нехватка людей ({{ deficits.length }})</summary>
      <ul>
        <li v-for="d in deficits.slice(0, 8)" :key="d.message">{{ d.message }}</li>
        <li v-if="deficits.length > 8" class="muted">и ещё {{ deficits.length - 8 }}</li>
      </ul>
    </details>
    <details v-if="unfilled.length">
      <summary>Не закрыто ({{ unfilled.length }})</summary>
      <ul>
        <li v-for="u in unfilled.slice(0, 8)" :key="u.message">
          {{ u.message }}<template v-if="u.missing > 1"> (×{{ u.missing }})</template>
        </li>
      </ul>
    </details>

    <section class="explain">
      <strong>Почему так</strong>
      <p v-if="!decisions.length" class="muted small">Щёлкните по подсвеченной ячейке в таблице.</p>
      <div v-for="d in decisions" :key="d.chosen_id" class="decision">
        <div>
          {{ d.date ? formatDate(d.date) : '' }} · {{ d.role_name }}:
          <strong>{{ d.chosen_name }}</strong>
          <small class="muted"> — лучший из {{ d.candidates }} допустимых, стоимость {{ d.cost.toFixed(2) }}</small>
        </div>
        <table class="features">
          <tr v-for="f in featureRows(d.features)" :key="f.label">
            <td>{{ f.label }}</td>
            <td>{{ f.value }}</td>
          </tr>
        </table>
        <div v-if="d.alternatives.length" class="small">
          Следующие:
          <span v-for="(a, i) in d.alternatives" :key="i">
            {{ a.name }} ({{ Number(a.cost).toFixed(2) }})<template v-if="i < d.alternatives.length - 1">, </template>
          </span>
        </div>
        <div v-if="run.kind === 'people' && rejectedText(d.rejected)" class="small muted">
          Отсеяны: {{ rejectedText(d.rejected) }}
        </div>
      </div>
    </section>

    <footer v-if="pending && !stale">
      <Button label="Отменить" severity="secondary" text @click="emit('discard')" />
      <Button label="Применить" icon="pi pi-check" :loading="busy" @click="emit('apply')" />
    </footer>
  </aside>
</template>

<style scoped>
.panel {
  width: 26rem;
  flex-shrink: 0;
  border: 1px solid var(--p-content-border-color);
  border-radius: 6px;
  padding: 0.75rem;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  background: var(--p-content-background);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
header > div {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.25rem;
}
.summary small {
  display: block;
  color: var(--p-text-muted-color);
}
.big {
  font-size: 1.4rem;
  font-weight: 700;
}
.big.warn {
  color: var(--p-orange-600);
}
.muted {
  color: var(--p-text-muted-color);
}
.small {
  font-size: 0.85rem;
  margin: 0;
}
details ul {
  margin: 0.25rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
}
summary {
  cursor: pointer;
  font-weight: 600;
}
.explain {
  display: grid;
  gap: 0.5rem;
}
.decision {
  border-top: 1px solid var(--p-content-border-color);
  padding-top: 0.4rem;
  display: grid;
  gap: 0.25rem;
}
.features {
  font-size: 0.85rem;
  border-collapse: collapse;
}
.features td {
  padding: 0 0.75rem 0 0;
}
.features td:last-child {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.inline {
  margin-left: 0.5rem;
}
footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: auto;
}
</style>
