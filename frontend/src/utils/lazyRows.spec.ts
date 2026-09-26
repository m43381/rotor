import { describe, expect, it } from 'vitest'

import { LazyRows } from './lazyRows'

function source(total: number) {
  const calls: [number, number][] = []
  const loader = async (offset: number, limit: number) => {
    calls.push([offset, limit])
    const items = Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) => offset + i)
    return { items, total }
  }
  return { loader, calls }
}

describe('LazyRows', () => {
  it('reset загружает первый блок и выделяет массив длины total', async () => {
    const { loader, calls } = source(250)
    const rows = new LazyRows(loader, 100)
    await rows.reset()
    expect(rows.total).toBe(250)
    expect(rows.rows).toHaveLength(250)
    expect(rows.rows[99]).toBe(99)
    expect(rows.rows[100]).toBeUndefined()
    expect(calls).toEqual([[0, 100]])
  })

  it('ensure грузит только недостающие блоки и не дублирует запросы', async () => {
    const { loader, calls } = source(1000)
    const rows = new LazyRows(loader, 100)
    await rows.reset()
    await Promise.all([rows.ensure(150, 260), rows.ensure(180, 220)])
    expect(calls).toEqual([
      [0, 100],
      [100, 100],
      [200, 100],
    ])
    expect(rows.rows[255]).toBe(255)
    await rows.ensure(0, 50)
    expect(calls).toHaveLength(3)
  })

  it('ответ устаревшего запроса после нового reset игнорируется', async () => {
    let total = 500
    let release: () => void = () => {}
    const gate = new Promise<void>((r) => (release = r))
    const rows = new LazyRows(async (offset: number, limit: number) => {
      if (offset === 300) await gate
      return { items: Array.from({ length: limit }, (_, i) => `${total}:${offset + i}`), total }
    }, 100)
    await rows.reset()
    const stale = rows.ensure(300, 350)
    total = 10
    await rows.reset()
    release()
    await stale
    expect(rows.rows).toHaveLength(10)
    expect(rows.rows[0]).toBe('10:0')
  })
})
