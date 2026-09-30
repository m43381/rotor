// Справочники для форм личного состава: звания (org), должности, категории личного состава,
// характеристики, причины освобождений (personnel). Грузятся один раз, перечитываются после изменения.
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  org,
  personnel,
  unwrap,
  type AttributeDefinition,
  type ExemptionReason,
  type PersonCategory,
  type Position,
  type Rank,
} from '@/api/client'

export const useRefsStore = defineStore('refs', () => {
  const ranks = ref<Rank[]>([])
  const positions = ref<Position[]>([])
  const categories = ref<PersonCategory[]>([])
  const attributes = ref<AttributeDefinition[]>([])
  const reasons = ref<ExemptionReason[]>([])
  let loaded: Promise<void> | null = null

  async function reload(): Promise<void> {
    const [r, p, c, a, e] = await Promise.all([
      unwrap(org.GET('/ranks')),
      unwrap(personnel.GET('/positions')),
      unwrap(personnel.GET('/person-categories')),
      unwrap(personnel.GET('/attribute-definitions')),
      unwrap(personnel.GET('/exemption-reasons')),
    ])
    ranks.value = r
    positions.value = p
    categories.value = c
    attributes.value = a
    reasons.value = e
  }

  function ensure(): Promise<void> {
    loaded ??= reload().catch((e: unknown) => {
      loaded = null
      throw e
    })
    return loaded
  }

  const activeRanks = computed(() => ranks.value.filter((r) => r.is_active))
  const activePositions = computed(() => positions.value.filter((p) => p.is_active))
  const activeCategories = computed(() => categories.value.filter((c) => c.is_active))
  const categoryName = (id: string | null | undefined) =>
    (id && categories.value.find((c) => c.id === id)?.name) || '—'
  const activeAttributes = computed(() => attributes.value.filter((a) => a.is_active))
  const activeReasons = computed(() => reasons.value.filter((r) => r.is_active))
  const reasonName = (id: string) => reasons.value.find((r) => r.id === id)?.name ?? '—'

  return {
    ranks,
    positions,
    categories,
    attributes,
    reasons,
    activeRanks,
    activePositions,
    activeCategories,
    categoryName,
    activeAttributes,
    activeReasons,
    reasonName,
    ensure,
    reload,
  }
})
