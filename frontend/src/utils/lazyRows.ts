// Ленивая загрузка строк для виртуального скролла: массив длины total, заполняемый
// блоками по мере прокрутки. Уже загруженные блоки повторно не запрашиваются.

export interface PageResult<T> {
  items: T[]
  total: number
}

export type Loader<T> = (offset: number, limit: number) => Promise<PageResult<T>>

export class LazyRows<T> {
  rows: (T | undefined)[] = []
  total = 0
  private readonly loaded = new Set<number>()
  private readonly pending = new Map<number, Promise<void>>()
  private generation = 0

  constructor(
    private readonly loader: Loader<T>,
    readonly blockSize = 100,
  ) {}

  /** Сброс (новый фильтр): загружает первый блок и узнаёт total. */
  async reset(): Promise<void> {
    this.generation++
    this.loaded.clear()
    this.pending.clear()
    const gen = this.generation
    const page = await this.loader(0, this.blockSize)
    if (gen !== this.generation) return
    this.total = page.total
    this.rows = Array.from({ length: page.total })
    this.put(0, page.items)
  }

  /** Гарантирует загрузку строк [first, last). */
  async ensure(first: number, last: number): Promise<void> {
    const from = Math.floor(Math.max(first, 0) / this.blockSize)
    const to = Math.floor(Math.max(Math.min(last, this.total) - 1, 0) / this.blockSize)
    const tasks: Promise<void>[] = []
    for (let block = from; block <= to; block++) tasks.push(this.loadBlock(block))
    await Promise.all(tasks)
  }

  private loadBlock(block: number): Promise<void> {
    if (this.loaded.has(block)) return Promise.resolve()
    const existing = this.pending.get(block)
    if (existing) return existing
    const gen = this.generation
    const task = this.loader(block * this.blockSize, this.blockSize)
      .then((page) => {
        if (gen === this.generation) this.put(block, page.items)
      })
      .finally(() => this.pending.delete(block))
    this.pending.set(block, task)
    return task
  }

  private put(block: number, items: T[]): void {
    const start = block * this.blockSize
    const next = this.rows.slice()
    items.forEach((item, i) => {
      if (start + i < next.length) next[start + i] = item
    })
    this.rows = next
    this.loaded.add(block)
  }
}
