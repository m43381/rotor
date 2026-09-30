// Отображение нарядов: шаблон времени (ADR-0008) и требования ролей (ADR-0009).
import type { AttributeDefinition, AttributeRequirement, DutyRoleIn, Position, Rank } from '@/api/client'
import { formatDate } from './dates'

export const OPS: Record<string, string> = { eq: 'равно', in: 'одно из', gte: 'не меньше', lte: 'не больше' }

/** Операторы сравнения, допустимые для типа характеристики (как проверяет сервис). */
export function opsFor(valueType: string): string[] {
  switch (valueType) {
    case 'int':
      return ['eq', 'in', 'gte', 'lte']
    case 'date':
      return ['eq', 'gte', 'lte']
    case 'bool':
      return ['eq']
    default:
      return ['eq', 'in']
  }
}

/** '18:00:00' → '18:00' */
export function formatTime(value: string): string {
  return value.slice(0, 5)
}

/** Длительность в минутах: «24 ч», «3 сут», «1 сут 6 ч», «6 ч 30 мин». */
export function formatDuration(minutes: number): string {
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  const mins = minutes % 60
  if (minutes === 1440) return '24 ч'
  const parts: string[] = []
  if (days) parts.push(`${days} сут`)
  if (hours) parts.push(`${hours} ч`)
  if (mins) parts.push(`${mins} мин`)
  return parts.join(' ') || '0 мин'
}

/** Интервал наряда от даты начала: «18:00 → 18:00 следующих суток». */
export function formatInterval(start: string, minutes: number): string {
  const [h = 0, m = 0] = start.split(':').map(Number)
  const endTotal = h * 60 + m + minutes
  const dayOffset = Math.floor(endTotal / 1440)
  const end = endTotal % 1440
  const endText = `${String(Math.floor(end / 60)).padStart(2, '0')}:${String(end % 60).padStart(2, '0')}`
  const suffix = dayOffset === 0 ? '' : dayOffset === 1 ? ' след. суток' : ` через ${dayOffset} сут`
  return `${formatTime(start)} → ${endText}${suffix}`
}

function valueText(value: unknown, def?: AttributeDefinition): string {
  if (Array.isArray(value)) return value.map((v) => valueText(v, def)).join(', ')
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  if (def?.value_type === 'date' && typeof value === 'string') return formatDate(value)
  return `«${String(value)}»`
}

/** Требования роли человеческим языком — для таблиц и подсказок. */
export function describeRequirements(
  role: Pick<DutyRoleIn, 'min_rank_order' | 'allowed_position_ids' | 'attribute_requirements'>,
  ranks: Rank[],
  positions: Position[],
  attributes: AttributeDefinition[],
): string[] {
  const result: string[] = []
  if (role.min_rank_order !== null && role.min_rank_order !== undefined) {
    const rank = ranks.find((r) => r.order === role.min_rank_order)
    result.push(`звание не ниже ${rank ? `«${rank.name}»` : role.min_rank_order}`)
  }
  if (role.allowed_position_ids?.length) {
    const names = role.allowed_position_ids.map((id) => positions.find((p) => p.id === id)?.name ?? '?')
    result.push(`должность: ${names.join(', ')}`)
  }
  for (const r of role.attribute_requirements ?? []) {
    const def = attributes.find((a) => a.code === r.code)
    const op = r.op === 'eq' ? '' : `${OPS[r.op] ?? r.op} `
    result.push(`${def?.name ?? r.code}: ${op}${valueText(r.value, def)}`)
  }
  return result
}

/** Пустое значение требования для выбранной характеристики и оператора. */
export function defaultRequirement(def: AttributeDefinition): AttributeRequirement {
  switch (def.value_type) {
    case 'bool':
      return { code: def.code, op: 'eq', value: true }
    case 'enum':
      return { code: def.code, op: 'eq', value: def.enum_options?.[0] ?? null }
    case 'int':
      return { code: def.code, op: 'gte', value: 1 }
    default:
      return { code: def.code, op: 'eq', value: null }
  }
}

export interface RoleChip {
  kind: 'unit' | 'category' | 'rank' | 'req'
  icon: string
  text: string
  hint: string
}

/** Кто заступает на роль и требования к нему — метками для списков нарядов (ADR-0018). */
export function roleChips(
  role: Pick<
    DutyRoleIn,
    'min_rank_order' | 'allowed_position_ids' | 'attribute_requirements' | 'allowed_category_ids'
  > & { assigned_unit_name?: string | null; assigned_unit_id?: string | null },
  refs: { ranks: Rank[]; positions: Position[]; attributes: AttributeDefinition[]; categories: { id: string; name: string }[] },
): RoleChip[] {
  const chips: RoleChip[] = []
  if (role.assigned_unit_id) {
    chips.push({
      kind: 'unit',
      icon: 'pi pi-map-marker',
      text: role.assigned_unit_name ?? 'подразделение',
      hint: 'Роль закреплена за подразделением: ячейки уходят ему автоматически',
    })
  }
  if (role.allowed_category_ids?.length) {
    const names = role.allowed_category_ids.map((id) => refs.categories.find((c) => c.id === id)?.name ?? '?')
    chips.push({
      kind: 'category',
      icon: 'pi pi-users',
      text: names.join(', '),
      hint: 'Допустимые категории личного состава (строгое условие)',
    })
  }
  if (role.min_rank_order !== null && role.min_rank_order !== undefined) {
    const rank = refs.ranks.find((r) => r.order === role.min_rank_order)
    chips.push({
      kind: 'rank',
      icon: 'pi pi-star',
      text: `от ${rank?.name ?? role.min_rank_order}`,
      hint: 'Звание не ниже',
    })
  }
  if (role.allowed_position_ids?.length) {
    const names = role.allowed_position_ids.map((id) => refs.positions.find((p) => p.id === id)?.name ?? '?')
    chips.push({ kind: 'req', icon: 'pi pi-briefcase', text: names.join(', '), hint: 'Допустимые должности' })
  }
  for (const r of role.attribute_requirements ?? []) {
    const def = refs.attributes.find((a) => a.code === r.code)
    const op = r.op === 'eq' ? '' : `${OPS[r.op] ?? r.op} `
    chips.push({
      kind: 'req',
      icon: 'pi pi-tag',
      text: `${def?.name ?? r.code}: ${op}${valueText(r.value, def)}`,
      hint: 'Требование к характеристике',
    })
  }
  return chips
}
