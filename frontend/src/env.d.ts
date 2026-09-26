/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Адрес realm Keycloak; по умолчанию — `${origin}/auth/realms/dutyflow` через шлюз. */
  readonly VITE_OIDC_AUTHORITY?: string
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}
