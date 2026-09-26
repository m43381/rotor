// Сборка дерева для TreeTable из плоского списка подразделений (сервер отдаёт список,
// отсортированный по глубине, но функция от порядка не зависит).

export interface FlatNode {
  id: string
  parent_id?: string | null
  name: string
  sort_order: number
}

export interface TreeNode<T> {
  key: string
  data: T
  children: TreeNode<T>[]
}

export function buildTree<T extends FlatNode>(items: readonly T[]): TreeNode<T>[] {
  const nodes = new Map<string, TreeNode<T>>()
  for (const item of items) nodes.set(item.id, { key: item.id, data: item, children: [] })

  const roots: TreeNode<T>[] = []
  for (const node of nodes.values()) {
    const parentId = node.data.parent_id
    const parent = parentId ? nodes.get(parentId) : undefined
    // Узел, чей родитель вне видимости оператора, становится корнем его дерева.
    if (parent) parent.children.push(node)
    else roots.push(node)
  }

  const byOrder = (a: TreeNode<T>, b: TreeNode<T>) =>
    a.data.sort_order - b.data.sort_order || a.data.name.localeCompare(b.data.name, 'ru')
  const sortDeep = (list: TreeNode<T>[]) => {
    list.sort(byOrder)
    for (const n of list) sortDeep(n.children)
  }
  sortDeep(roots)
  return roots
}

/** Ключи узлов до заданной глубины — чтобы дерево открывалось не свёрнутым целиком. */
export function expandedKeys<T>(roots: TreeNode<T>[], depth: number): Record<string, boolean> {
  const keys: Record<string, boolean> = {}
  const walk = (list: TreeNode<T>[], level: number) => {
    if (level >= depth) return
    for (const n of list) {
      if (n.children.length) keys[n.key] = true
      walk(n.children, level + 1)
    }
  }
  walk(roots, 0)
  return keys
}

/** id узла и всех его потомков — чтобы не предлагать перенос внутрь самого себя. */
export function subtreeIds<T extends FlatNode>(items: readonly T[], rootId: string): Set<string> {
  const children = new Map<string, string[]>()
  for (const i of items) {
    if (!i.parent_id) continue
    const list = children.get(i.parent_id) ?? []
    list.push(i.id)
    children.set(i.parent_id, list)
  }
  const result = new Set<string>([rootId])
  const stack = [rootId]
  while (stack.length) {
    const id = stack.pop() as string
    for (const c of children.get(id) ?? []) {
      result.add(c)
      stack.push(c)
    }
  }
  return result
}
