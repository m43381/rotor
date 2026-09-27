import { describe, expect, it } from 'vitest'

import type { AttributeDefinition, Position, Rank } from '@/api/client'
import { describeRequirements, formatDuration, formatInterval, opsFor } from './duty'

describe('шаблон времени наряда', () => {
  it('длительность', () => {
    expect(formatDuration(1440)).toBe('24 ч')
    expect(formatDuration(360)).toBe('6 ч')
    expect(formatDuration(3 * 1440)).toBe('3 сут')
    expect(formatDuration(1440 + 360)).toBe('1 сут 6 ч')
    expect(formatDuration(390)).toBe('6 ч 30 мин')
  })

  it('интервал с переходом через полночь', () => {
    expect(formatInterval('18:00:00', 1440)).toBe('18:00 → 18:00 след. суток')
    expect(formatInterval('08:00:00', 360)).toBe('08:00 → 14:00')
    expect(formatInterval('08:00:00', 72 * 60)).toBe('08:00 → 08:00 через 3 сут')
  })
})

describe('требования роли', () => {
  const ranks = [{ id: 'r1', name: 'Капитан', order: 90 }] as Rank[]
  const positions = [{ id: 'p1', name: 'Старшина курса' }] as Position[]
  const attributes = [
    { code: 'category', name: 'Категория', value_type: 'enum' },
    { code: 'since', name: 'Допущен с', value_type: 'date' },
  ] as AttributeDefinition[]

  it('описание по-русски', () => {
    expect(
      describeRequirements(
        {
          min_rank_order: 90,
          allowed_position_ids: ['p1'],
          attribute_requirements: [
            { code: 'category', op: 'in', value: ['Курсант', 'Слушатель'] },
            { code: 'since', op: 'lte', value: '2026-01-31' },
          ],
        },
        ranks,
        positions,
        attributes,
      ),
    ).toEqual([
      'звание не ниже «Капитан»',
      'должность: Старшина курса',
      'Категория: одно из «Курсант», «Слушатель»',
      'Допущен с: не больше 31.01.2026',
    ])
  })

  it('без требований — пусто', () => {
    expect(describeRequirements({ attribute_requirements: [] }, ranks, positions, attributes)).toEqual([])
  })

  it('сравнения — только для чисел и дат', () => {
    expect(opsFor('enum')).toEqual(['eq', 'in'])
    expect(opsFor('bool')).toEqual(['eq'])
    expect(opsFor('date')).toContain('gte')
  })
})
