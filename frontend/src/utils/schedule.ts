// Таблица месяца: даты, сокращения подразделений, выделение ячеек прямоугольником.

const MONTHS = [
  'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб']

/** Первое число месяца в ISO: '2026-11-01'. */
export function monthIso(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-01`
}

export function shiftMonth(iso: string, delta: number): string {
  const [y = 1970, m = 1] = iso.split('-').map(Number)
  return monthIso(new Date(y, m - 1 + delta, 1))
}

/** '2026-11-01' → 'ноябрь 2026' */
export function monthTitle(iso: string): string {
  const [y, m = 1] = iso.split('-').map(Number)
  return `${MONTHS[m - 1]} ${y}`
}

export function weekday(iso: string): string {
  const [y = 1970, m = 1, d = 1] = iso.split('-').map(Number)
  return WEEKDAYS[new Date(y, m - 1, d).getDay()] ?? ''
}

/** Короткое имя для узкой ячейки: сокращение подразделения или первые буквы и цифры. */
export function abbr(name: string, shortName?: string | null): string {
  if (shortName) return shortName
  const parts = name.split(/[\s,]+/).filter(Boolean)
  const result = parts
    .map((p) => (/\d/.test(p) ? p : (p[0] ?? '').toUpperCase()))
    .join('')
  return result.slice(0, 5)
}

export interface CellPos {
  row: number
  col: number
}

/** Все позиции прямоугольника между двумя углами (выделение Shift+клик). */
export function rect(a: CellPos, b: CellPos): CellPos[] {
  const result: CellPos[] = []
  for (let row = Math.min(a.row, b.row); row <= Math.max(a.row, b.row); row++) {
    for (let col = Math.min(a.col, b.col); col <= Math.max(a.col, b.col); col++) {
      result.push({ row, col })
    }
  }
  return result
}
