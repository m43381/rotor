import { describe, expect, it } from 'vitest'

import { changes, fieldLabel, valueText } from './audit'

describe('журнал аудита', () => {
  const units = (id: string) => (id === 'u1' ? 'Факультет 1' : undefined)

  it('подписывает поля и значения', () => {
    expect(fieldLabel('rank_id')).toBe('Звание')
    expect(fieldLabel('unknown_field')).toBe('unknown_field')
    expect(valueText('u1', units)).toBe('Факультет 1')
    expect(valueText('2026-11-05', units)).toBe('05.11.2026')
    expect(valueText(true, units)).toBe('да')
    expect(valueText('discarded', units)).toBe('отменён')
    expect(valueText(null, units)).toBe('—')
    expect(valueText({ category: 'Курсант' }, units)).toBe('category: Курсант')
  })

  it('собирает изменения из было/стало', () => {
    expect(changes({ a: 1 }, { a: 2, b: 3 })).toEqual([
      { field: 'a', before: 1, after: 2 },
      { field: 'b', before: undefined, after: 3 },
    ])
    expect(changes(null, { a: 1 })).toEqual([{ field: 'a', before: undefined, after: 1 }])
  })
})
