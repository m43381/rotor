// Подписи для объяснений движка распределения (фаза 4): признаки, причины отсева, статусы.

export const FEATURE_LABELS: Record<string, string> = {
  load: 'Нагрузка с затуханием',
  same_type: 'Нагрузка по этому наряду',
  holiday: 'Наряды в выходные',
  recency: 'Близость к другому наряду',
  quota: 'Выбранная доля квоты',
  same_day: 'Уже отдано в этот день',
  capacity: 'Запас людей',
}

export const REJECT_LABELS: Record<string, string> = {
  no_clearance: 'нет допуска',
  exempt: 'освобождены',
  busy: 'заняты в эти сутки',
  rest: 'не успевают отдохнуть',
  limit: 'исчерпан лимит',
}

export const RUN_STATUS: Record<string, { label: string; severity: string }> = {
  preview_ready: { label: 'Предпросмотр', severity: 'info' },
  applied: { label: 'Применён', severity: 'success' },
  discarded: { label: 'Отменён', severity: 'secondary' },
  stale: { label: 'Устарел', severity: 'warn' },
  failed: { label: 'Ошибка', severity: 'danger' },
}

/** Сводка отсева кандидатов: «нет допуска: 12, заняты в эти сутки: 3». Нули не показываются. */
export function rejectedText(rejected: Record<string, unknown> | null | undefined): string {
  if (!rejected) return ''
  return Object.entries(REJECT_LABELS)
    .map(([key, label]) => [label, Number(rejected[key] ?? 0)] as const)
    .filter(([, n]) => n > 0)
    .map(([label, n]) => `${label}: ${n}`)
    .join(', ')
}

export function featureRows(features: Record<string, unknown>): { label: string; value: string }[] {
  return Object.entries(features).map(([key, value]) => ({
    label: FEATURE_LABELS[key] ?? key,
    value: typeof value === 'number' ? value.toFixed(2) : String(value),
  }))
}
