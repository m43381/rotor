import { describe, expect, it } from 'vitest'

import { abbr, monthTitle, rect, shiftMonth, weekday } from './schedule'

describe('таблица месяца', () => {
  it('месяцы', () => {
    expect(shiftMonth('2026-12-01', 1)).toBe('2027-01-01')
    expect(shiftMonth('2026-01-01', -1)).toBe('2025-12-01')
    expect(monthTitle('2026-11-01')).toBe('ноябрь 2026')
    expect(weekday('2026-11-01')).toBe('вс')
  })

  it('сокращения подразделений', () => {
    expect(abbr('Курс A1')).toBe('КA1')
    expect(abbr('1 курс, факультет 1')).toBe('1КФ1')
    expect(abbr('Группа 111')).toBe('Г111')
    expect(abbr('Что угодно', 'ТУ')).toBe('ТУ')
  })

  it('прямоугольное выделение в любую сторону', () => {
    expect(rect({ row: 1, col: 3 }, { row: 0, col: 2 })).toEqual([
      { row: 0, col: 2 },
      { row: 0, col: 3 },
      { row: 1, col: 2 },
      { row: 1, col: 3 },
    ])
  })
})

describe('объяснения движка', async () => {
  const { rejectedText, featureRows } = await import('./allocation')
  it('сводка отсева без нулей', () => {
    expect(rejectedText({ no_clearance: 12, exempt: 0, busy: 3 })).toBe('нет допуска: 12, заняты в эти сутки: 3')
    expect(rejectedText(null)).toBe('')
  })
  it('признаки с подписями', () => {
    expect(featureRows({ load: 1.5, recency: 0 })).toEqual([
      { label: 'Нагрузка с затуханием', value: '1.50' },
      { label: 'Близость к другому наряду', value: '0.00' },
    ])
  })
})
