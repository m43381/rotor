// Клиент API сервисов. Типы запросов и ответов сгенерированы из OpenAPI (`npm run gen:api`).
import createClient, { type Middleware } from 'openapi-fetch'

import { accessToken, signIn } from '@/auth'
import type { components, paths as OrgPaths } from './generated/org'
import type { components as PC, paths as PersonnelPaths } from './generated/personnel'
import type { components as SC, paths as SchedulingPaths } from './generated/scheduling'

export type Unit = components['schemas']['UnitOut']
export type UnitType = components['schemas']['UnitTypeOut']
export type Me = components['schemas']['MeOut']
export type UnitCreate = components['schemas']['UnitCreate']
export type Rank = components['schemas']['RankOut']

export type PersonListItem = PC['schemas']['PersonListItem']
export type Person = PC['schemas']['PersonOut']
export type PersonCreate = PC['schemas']['PersonCreate']
export type PersonUpdate = PC['schemas']['PersonUpdate']
export type Exemption = PC['schemas']['ExemptionOut']
export type Position = PC['schemas']['PositionOut']
export type AttributeDefinition = PC['schemas']['AttributeDefinitionOut']
export type ExemptionReason = PC['schemas']['ExemptionReasonOut']
export type BulkResult = PC['schemas']['BulkResult']
export type AuditEntry = PC['schemas']['AuditEntryOut']
export type Clearance = PC['schemas']['ClearanceOut']
export type ClearanceOption = PC['schemas']['ClearanceOption']
export type ClearanceRole = PC['schemas']['ClearanceRoleOut']
export type Violation = PC['schemas']['ViolationOut']
export type BulkClearanceResult = PC['schemas']['BulkClearanceResult']
export type MismatchItem = PC['schemas']['MismatchItem']

export type DutyType = SC['schemas']['DutyTypeOut']
export type DutyRole = SC['schemas']['DutyRoleOut']
export type DutyRoleIn = SC['schemas']['DutyRoleIn']
export type DutyTypeCreate = SC['schemas']['DutyTypeCreate']
export type DutyTypeUpdate = SC['schemas']['DutyTypeUpdate']
export type AttributeRequirement = SC['schemas']['AttributeRequirement']
export type Schedule = SC['schemas']['ScheduleOut']
export type ScheduleTable = SC['schemas']['TableOut']
export type TableRow = SC['schemas']['TableRow']
export type Cell = SC['schemas']['CellOut']
export type PendingWarning = SC['schemas']['PendingWarning']
export type Candidates = SC['schemas']['CandidatesOut']
export type Candidate = SC['schemas']['CandidateOut']
export type Assigned = SC['schemas']['AssignedOut']
export type SchedViolation = SC['schemas']['ViolationOut']
export type DutyLimit = SC['schemas']['DutyLimitOut']
export type DutyLimitIn = SC['schemas']['DutyLimitIn']
export type Run = SC['schemas']['RunOut']
export type RunBrief = SC['schemas']['RunBrief']
export type Decision = SC['schemas']['DecisionOut']

/** Ошибка API в формате сервисов: `{code, message, details?}`. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

const auth: Middleware = {
  async onRequest({ request }) {
    const token = await accessToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
  async onResponse({ response }) {
    if (response.status === 401) await signIn()
    return response
  },
}

export const org = createClient<OrgPaths>({ baseUrl: '/api/org' })
org.use(auth)

export const personnel = createClient<PersonnelPaths>({ baseUrl: '/api/personnel' })
personnel.use(auth)

export const scheduling = createClient<SchedulingPaths>({ baseUrl: '/api/scheduling' })
scheduling.use(auth)

interface Result<T> {
  data?: T
  error?: unknown
  response: Response
}

/** Возвращает данные или бросает ApiError с сообщением сервиса на русском. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const { data, error, response } = await call
  if (!response.ok) {
    const body = (error ?? {}) as { code?: string; message?: string; details?: unknown }
    throw new ApiError(
      response.status,
      body.code ?? 'error',
      body.message ?? `Ошибка сервера (${response.status})`,
      body.details,
    )
  }
  return data as T
}
