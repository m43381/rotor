// Клиент API сервисов. Типы запросов и ответов сгенерированы из OpenAPI (`npm run gen:api`).
import createClient, { type Middleware } from 'openapi-fetch'

import { accessToken, signIn } from '@/auth'
import type { components, paths as OrgPaths } from './generated/org'

export type Unit = components['schemas']['UnitOut']
export type UnitType = components['schemas']['UnitTypeOut']
export type Me = components['schemas']['MeOut']
export type UnitCreate = components['schemas']['UnitCreate']

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
