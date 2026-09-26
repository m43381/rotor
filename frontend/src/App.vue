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
        <RouterLink v-if="isSuperadmin" to="/references">Справочники</RouterLink>
      </nav>
      <div v-if="store.me" class="user">
        <div class="user-text">
          <strong>{{ store.me.full_name || store.me.username }}</strong>
          <small>{{ roleLabel }} · {{ store.me.unit.name }}</small>
        </div>
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
  gap: 2rem;
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
  gap: 1rem;
  flex: 1;
}
.nav a {
  color: var(--p-text-muted-color);
  text-decoration: none;
  padding: 0.25rem 0;
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
}
.content {
  flex: 1;
  min-height: 0;
  padding: 1.25rem;
}
</style>
