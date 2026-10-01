// Вход через Keycloak (OIDC Authorization Code + PKCE). Пароли приложение не видит.
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'

import { ensureDigest } from './sha256'

// По HTTP не с localhost у браузера нет crypto.subtle, а он нужен PKCE (ADR-0021)
ensureDigest()

const authority =
  import.meta.env.VITE_OIDC_AUTHORITY ?? `${window.location.origin}/auth/realms/dutyflow`

export const userManager = new UserManager({
  authority,
  client_id: 'dutyflow-spa',
  redirect_uri: `${window.location.origin}/callback`,
  post_logout_redirect_uri: `${window.location.origin}/`,
  response_type: 'code',
  scope: 'openid',
  // Токен живёт 5 минут и обновляется refresh-токеном в фоне.
  automaticSilentRenew: true,
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
})

const CALLBACK_PATH = '/callback'

/** Гарантирует, что пользователь вошёл: обрабатывает возврат из Keycloak или уводит на вход.
 *  Возвращает null, если начат редирект на страницу входа. */
export async function ensureSignedIn(): Promise<User | null> {
  if (window.location.pathname === CALLBACK_PATH) {
    const user = await userManager.signinRedirectCallback()
    const target = typeof user.state === 'string' ? user.state : '/'
    window.history.replaceState({}, '', target)
    return user
  }
  const user = await userManager.getUser()
  if (user && !user.expired) return user
  await signIn()
  return null
}

export async function signIn(): Promise<void> {
  await userManager.signinRedirect({
    state: window.location.pathname + window.location.search,
  })
}

export async function signOut(): Promise<void> {
  await userManager.signoutRedirect()
}

export async function accessToken(): Promise<string | null> {
  const user = await userManager.getUser()
  return user && !user.expired ? user.access_token : null
}
