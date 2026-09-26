import { describe, expect, it } from 'vitest'

import { buildTree, expandedKeys, subtreeIds } from './tree'

const units = [
  { id: 'c2', parent_id: 'f1', name: 'Курс 2', sort_order: 0 },
  { id: 'root', parent_id: null, name: 'Академия', sort_order: 0 },
  { id: 'f2', parent_id: 'root', name: 'Факультет Б', sort_order: 0 },
  { id: 'f1', parent_id: 'root', name: 'Факультет А', sort_order: 0 },
  { id: 'c1', parent_id: 'f1', name: 'Курс 1', sort_order: 0 },
  { id: 'g1', parent_id: 'c1', name: 'Группа', sort_order: 0 },
]

describe('buildTree', () => {
  it('собирает дерево независимо от порядка и сортирует по имени', () => {
    const [root] = buildTree(units)
    expect(root?.key).toBe('root')
    expect(root?.children.map((n) => n.data.name)).toEqual(['Факультет А', 'Факультет Б'])
    expect(root?.children[0]?.children.map((n) => n.key)).toEqual(['c1', 'c2'])
  })

  it('делает корнем узел, чей родитель не виден оператору', () => {
    const visible = units.filter((u) => ['f1', 'c1', 'c2'].includes(u.id))
    expect(buildTree(visible).map((n) => n.key)).toEqual(['f1'])
  })

  it('sort_order важнее имени', () => {
    const tree = buildTree([
      { id: 'a', parent_id: null, name: 'А', sort_order: 2 },
      { id: 'b', parent_id: null, name: 'Б', sort_order: 1 },
    ])
    expect(tree.map((n) => n.key)).toEqual(['b', 'a'])
  })
})

describe('expandedKeys', () => {
  it('раскрывает только узлы с детьми до заданной глубины', () => {
    expect(expandedKeys(buildTree(units), 2)).toEqual({ root: true, f1: true })
  })
})

describe('subtreeIds', () => {
  it('возвращает узел и всех потомков', () => {
    expect([...subtreeIds(units, 'f1')].sort()).toEqual(['c1', 'c2', 'f1', 'g1'])
  })
})
