<script setup lang="ts">
// Полоса ключевых показателей: одна поверхность, ячейки разделены линиями. Значение крупно,
// подпись и пояснение — мелко; состояние — точкой и словами, а не заливкой карточки.
export interface Stat {
  key: string
  label: string
  value: string
  sub?: string
  state?: 'good' | 'warn' | 'serious' | 'critical'
  stateText?: string
  action?: () => void
}
defineProps<{ items: Stat[]; loading?: boolean }>()
</script>

<template>
  <div class="strip" :class="{ loading }">
    <component
      :is="s.action ? 'button' : 'div'"
      v-for="s in items"
      :key="s.key"
      :type="s.action ? 'button' : undefined"
      class="stat"
      :class="{ link: !!s.action }"
      @click="s.action?.()"
    >
      <span class="label">{{ s.label }}</span>
      <span class="value">{{ loading ? '—' : s.value }}</span>
      <span v-if="s.stateText || s.sub" class="sub">
        <span v-if="s.state" class="dot" :class="`dot--${s.state}`" />
        {{ s.stateText ?? s.sub }}
      </span>
    </component>
  </div>
</template>

<style scoped>
.strip {
  /* Плитки растягиваются на всю строку, и при переносе (узкое окно, крупный шрифт) не остаётся
     пустого хвоста; разделители — зазором в 1px на фоне цвета границы */
  display: flex;
  flex-wrap: wrap;
  gap: 1px;
  background: var(--app-border);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius);
  overflow: hidden;
}
.stat {
  display: grid;
  align-content: start;
  gap: 0.3rem;
  flex: 1 1 11rem;
  padding: 0.85rem 1rem 0.9rem;
  border: none;
  background: var(--app-card-bg);
  font: inherit;
  color: inherit;
  text-align: left;
}
.stat.link {
  cursor: pointer;
}
.stat.link:hover {
  background: var(--app-hover);
}
.stat.link:hover .label {
  color: var(--app-accent);
}
.label {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--app-ink-3);
}
.value {
  font-size: 1.75rem;
  font-weight: 650;
  line-height: 1.1;
  color: var(--app-ink);
  letter-spacing: -0.01em;
}
.sub {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  color: var(--app-ink-2);
}
.loading .value {
  color: var(--app-ink-3);
}
</style>
