<script setup lang="ts">
import Button from 'primevue/button'
import ConfirmDialog from 'primevue/confirmdialog'
import Toast from 'primevue/toast'
import { computed, onMounted, ref, watch } from 'vue'

import { useRoute } from 'vue-router'

import { signOut } from '@/auth'
import { useUnitsStore } from '@/stores/units'
import { useTheme } from '@/theme'

const store = useUnitsStore()
const route = useRoute()
const theme = useTheme()
const today = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
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
const roles = computed(() => store.me?.roles ?? [])
const isSuperadmin = computed(() => roles.value.includes('superadmin'))
// Операторами управляют администраторы (open-questions №59)
const canManageOperators = computed(() => isSuperadmin.value || roles.value.includes('unit_admin'))
// Импорт и журнал — для тех, кто меняет данные (права проверяет сервис по строкам)
const canImport = computed(() => roles.value.some((r) => r !== 'viewer'))
// Смена своего пароля — страница аккаунта Keycloak
const accountUrl = `${window.location.origin}/auth/realms/dutyflow/account/#/account-security/signing-in`
const roleLabel = computed(() => roles.value.map((r) => ROLE_NAMES[r] ?? r).join(', '))
const initials = computed(() => {
  const name = store.me?.full_name || store.me?.username || ''
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
})

interface NavItem {
  to: string
  label: string
  icon: string
  /** Другие пути, на которых пункт тоже подсвечивается */
  also?: string[]
  show?: boolean
}
interface NavGroup {
  title: string
  items: NavItem[]
}

// Меню по группам: сначала ежедневная работа, затем анализ, затем настройка системы
const groups = computed<NavGroup[]>(() =>
  (
    [
      {
      title: 'Работа',
      items: [
        { to: '/home', label: 'Рабочий стол', icon: 'pi pi-home' },
        { to: '/schedules', label: 'Графики нарядов', icon: 'pi pi-calendar' },
        {
          to: '/people',
          label: 'Личный состав',
          icon: 'pi pi-users',
          also: ['/people/', '/reports/clearance-mismatches'],
        },
        { to: '/duty-types', label: 'Наряды и роли', icon: 'pi pi-shield', also: ['/duty-limits'] },
      ],
    },
    {
      title: 'Анализ и документы',
      items: [
        { to: '/dashboard', label: 'Аналитика', icon: 'pi pi-chart-bar' },
        { to: '/documents', label: 'Документы', icon: 'pi pi-print' },
      ],
    },
    {
      title: 'Администрирование',
      items: [
        { to: '/units', label: 'Подразделения', icon: 'pi pi-sitemap' },
        { to: '/import', label: 'Импорт', icon: 'pi pi-upload', show: canImport.value },
        { to: '/audit', label: 'Журнал изменений', icon: 'pi pi-history', show: canImport.value },
        { to: '/operators', label: 'Операторы', icon: 'pi pi-id-card', show: canManageOperators.value },
        { to: '/references', label: 'Справочники', icon: 'pi pi-book', show: isSuperadmin.value },
      ],
    },
    ] as NavGroup[]
  )
    .map((g) => ({ ...g, items: g.items.filter((i) => i.show !== false) }))
    .filter((g) => g.items.length),
)

const isActive = (item: NavItem) =>
  route.path === item.to || (item.also ?? []).some((p) => route.path === p || route.path.startsWith(p))

// Свёрнутое меню — удобство конкретного рабочего места, помним его в браузере
const COLLAPSE_KEY = 'dutyflow.sidebar.collapsed'
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}
const collapsed = ref(readCollapsed())
watch(collapsed, (value) => {
  try {
    localStorage.setItem(COLLAPSE_KEY, value ? '1' : '0')
  } catch {
    /* хранилище недоступно — просто не запоминаем */
  }
})
</script>

<template>
  <div class="layout" :class="{ collapsed }">
    <header class="topbar">
      <Button
        :icon="collapsed ? 'pi pi-bars' : 'pi pi-align-left'"
        text
        rounded
        severity="secondary"
        :aria-label="collapsed ? 'Развернуть меню' : 'Свернуть меню'"
        @click="collapsed = !collapsed"
      />
      <RouterLink to="/home" class="brand">
        <img src="/favicon.svg" alt="" width="24" height="24" />
        <span>DutyFlow</span>
      </RouterLink>
      <span class="brand-sub">{{ store.me?.unit.name ?? 'Распределение нарядов' }}</span>
      <div class="spacer" />
      <span class="today">{{ today }}</span>
      <Button
        v-tooltip.bottom="theme.isDark.value ? 'Светлая тема' : 'Тёмная тема'"
        :icon="theme.isDark.value ? 'pi pi-sun' : 'pi pi-moon'"
        text
        rounded
        severity="secondary"
        :aria-label="theme.isDark.value ? 'Включить светлую тему' : 'Включить тёмную тему'"
        @click="theme.toggle"
      />
      <span class="divider" />
      <div v-if="store.me" class="user">
        <div class="user-text">
          <strong>{{ store.me.full_name || store.me.username }}</strong>
          <small>{{ roleLabel }}</small>
        </div>
        <span class="avatar" aria-hidden="true">{{ initials }}</span>
        <Button
          v-tooltip.bottom="'Сменить пароль'"
          as="a"
          :href="accountUrl"
          target="_blank"
          icon="pi pi-key"
          text
          rounded
          severity="secondary"
          aria-label="Сменить пароль"
        />
        <Button
          v-tooltip.bottom="'Выйти'"
          icon="pi pi-sign-out"
          text
          rounded
          severity="secondary"
          aria-label="Выйти"
          @click="signOut"
        />
      </div>
    </header>
    <nav class="sidebar" aria-label="Разделы">
      <div v-for="g in groups" :key="g.title" class="nav-group">
        <div class="nav-title">{{ g.title }}</div>
        <RouterLink
          v-for="item in g.items"
          :key="item.to"
          v-tooltip.right="collapsed ? item.label : undefined"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item) }"
          :aria-label="item.label"
        >
          <i :class="item.icon" aria-hidden="true" />
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </div>
    </nav>
    <main class="content">
      <RouterView />
    </main>
    <Toast />
    <ConfirmDialog />
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: var(--app-sidebar-width) 1fr;
  grid-template-rows: 3.25rem 1fr;
  grid-template-areas:
    'top top'
    'side main';
  height: 100vh;
  background: var(--app-bg);
}
.layout.collapsed {
  grid-template-columns: var(--app-sidebar-collapsed) 1fr;
}
.topbar {
  grid-area: top;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0 1rem 0 0.6rem;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-card-bg);
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 700;
  font-size: 1rem;
  letter-spacing: 0.01em;
  color: var(--app-ink);
  text-decoration: none;
}
.brand-sub {
  color: var(--app-ink-3);
  font-size: 0.85rem;
  padding-left: 0.75rem;
  margin-left: 0.25rem;
  border-left: 1px solid var(--app-border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.spacer {
  flex: 1;
}
.today {
  color: var(--app-ink-3);
  font-size: 0.85rem;
  margin-right: 0.25rem;
}
.divider {
  width: 1px;
  height: 1.5rem;
  background: var(--app-border);
  margin: 0 0.25rem;
}
.user {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}
.user-text {
  display: flex;
  flex-direction: column;
  text-align: right;
  line-height: 1.2;
}
.user-text strong {
  font-size: 0.88rem;
  font-weight: 600;
}
.user-text small {
  color: var(--app-ink-3);
  font-size: 0.75rem;
}
.avatar {
  display: inline-grid;
  place-items: center;
  width: 1.9rem;
  height: 1.9rem;
  border-radius: 6px;
  background: var(--app-accent-soft);
  color: var(--app-accent);
  font-weight: 700;
  font-size: 0.75rem;
  margin-left: 0.3rem;
}
.sidebar {
  grid-area: side;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0.9rem 0.5rem;
  background: var(--app-sidebar-bg);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}
.nav-group {
  display: grid;
  gap: 1px;
}
.nav-title {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--app-ink-3);
  padding: 0 0.75rem 0.35rem;
  white-space: nowrap;
}
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.45rem 0.75rem;
  border-radius: 6px;
  color: var(--app-ink-2);
  text-decoration: none;
  white-space: nowrap;
  font-size: 0.92rem;
}
.nav-item i {
  width: 1rem;
  text-align: center;
  font-size: 0.9rem;
  color: var(--app-ink-3);
}
.nav-item:hover {
  background: var(--app-hover);
  color: var(--app-ink);
}
.nav-item.active {
  background: var(--app-hover);
  color: var(--app-ink);
  font-weight: 600;
}
.nav-item.active::before {
  content: '';
  position: absolute;
  left: -0.5rem;
  top: 0.35rem;
  bottom: 0.35rem;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: var(--app-accent);
}
.nav-item.active i {
  color: var(--app-accent);
}
.collapsed .nav-title,
.collapsed .nav-label {
  display: none;
}
.collapsed .nav-group + .nav-group {
  border-top: 1px solid var(--app-border);
  padding-top: 0.6rem;
}
.collapsed .nav-item {
  justify-content: center;
  padding: 0.55rem 0;
}
.content {
  grid-area: main;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 1.25rem 1.5rem;
}
@media (max-width: 1100px) {
  .today {
    display: none;
  }
}
@media (max-width: 960px) {
  .brand-sub,
  .user-text {
    display: none;
  }
}
</style>
