<script setup lang="ts">
import Button from 'primevue/button'
import ConfirmDialog from 'primevue/confirmdialog'
import Toast from 'primevue/toast'
import { computed, onMounted } from 'vue'

import { useRoute } from 'vue-router'

import { signOut } from '@/auth'
import { useUnitsStore } from '@/stores/units'

const store = useUnitsStore()
const route = useRoute()
// Оператор и дерево нужны всем экранам (шапка, фильтры по подразделению).
onMounted(() => {
  if (!store.me) store.load().catch(() => undefined)
})

const ROLE_NAMES: Record<string, string> = {
  superadmin: 'Суперадминистратор',
  unit_admin: 'Администратор подразделения',
  operator: 'Оператор',
  viewer: 'Просмотр',
}
const isSuperadmin = computed(() => store.me?.roles.includes('superadmin') === true)
// Операторами управляют администраторы (open-questions №59)
const canManageOperators = computed(() => isSuperadmin.value || store.me?.roles.includes('unit_admin') === true)
// Смена своего пароля — страница аккаунта Keycloak
const accountUrl = `${window.location.origin}/auth/realms/dutyflow/account/#/account-security/signing-in`
// Импорт меняет данные — наблюдателю не показывается (права проверяет сервис по строкам)
const canImport = computed(() => (store.me?.roles ?? []).some((r) => r !== 'viewer'))
const roleLabel = computed(() =>
  (store.me?.roles ?? []).map((r) => ROLE_NAMES[r] ?? r).join(', '),
)
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand">
        <img src="/favicon.svg" alt="" width="28" height="28" />
        <span>DutyFlow</span>
      </div>
      <nav class="nav">
        <RouterLink to="/units">Подразделения</RouterLink>
        <RouterLink to="/people" :class="{ 'router-link-active': route.path.startsWith('/people') }">
          Личный состав
        </RouterLink>
        <RouterLink to="/schedules">Графики</RouterLink>
        <RouterLink to="/duty-types" :class="{ 'router-link-active': route.path === '/duty-limits' }">
          Наряды
        </RouterLink>
        <RouterLink to="/dashboard">Нагрузка</RouterLink>
        <RouterLink to="/documents">Документы</RouterLink>
        <RouterLink v-if="canImport" to="/import">Импорт</RouterLink>
        <RouterLink v-if="canImport" to="/audit">Журнал</RouterLink>
        <RouterLink v-if="canManageOperators" to="/operators">Операторы</RouterLink>
        <RouterLink v-if="isSuperadmin" to="/references">Справочники</RouterLink>
      </nav>
      <div v-if="store.me" class="user">
        <div class="user-text">
          <strong>{{ store.me.full_name || store.me.username }}</strong>
          <small>{{ roleLabel }} · {{ store.me.unit.name }}</small>
        </div>
        <Button
          v-tooltip.bottom="'Сменить пароль'"
          as="a"
          :href="accountUrl"
          target="_blank"
          icon="pi pi-key"
          text
          rounded
          aria-label="Сменить пароль"
        />
        <Button icon="pi pi-sign-out" text rounded aria-label="Выйти" @click="signOut" />
      </div>
    </header>
    <main class="content">
      <RouterView />
    </main>
    <Toast />
    <ConfirmDialog />
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.topbar {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid var(--p-content-border-color);
  background: var(--p-content-background);
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 700;
  font-size: 1.1rem;
}
.nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.9rem;
  flex: 1;
  min-width: 0;
}
.nav a {
  color: var(--p-text-muted-color);
  text-decoration: none;
  padding: 0.25rem 0;
  white-space: nowrap;
}
.nav a.router-link-active {
  color: var(--p-primary-color);
  border-bottom: 2px solid var(--p-primary-color);
}
.user {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.user-text {
  display: flex;
  flex-direction: column;
  text-align: right;
  line-height: 1.2;
}
.user-text small {
  color: var(--p-text-muted-color);
  max-width: 22rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.content {
  flex: 1;
  min-height: 0;
  padding: 1.25rem;
}
</style>
