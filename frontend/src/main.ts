import 'primeicons/primeicons.css'
import './styles.css'

import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { DutyFlowPreset } from './theme'
import { ensureSignedIn } from './auth'
import { ru } from './locale/ru'
import AuditView from './views/AuditView.vue'
import ClearanceMismatchesView from './views/ClearanceMismatchesView.vue'
import DashboardView from './views/DashboardView.vue'
import DocumentsView from './views/DocumentsView.vue'
import DutyLimitsView from './views/DutyLimitsView.vue'
import DutyTypesView from './views/DutyTypesView.vue'
import HomeView from './views/HomeView.vue'
import ImportView from './views/ImportView.vue'
import OperatorsView from './views/OperatorsView.vue'
import PeopleView from './views/PeopleView.vue'
import PersonView from './views/PersonView.vue'
import ReferencesView from './views/ReferencesView.vue'
import SchedulesView from './views/SchedulesView.vue'
import UnitsView from './views/UnitsView.vue'

async function bootstrap() {
  // Приложение открывается только после входа: без токена показывать нечего.
  const user = await ensureSignedIn()
  if (!user) return

  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', redirect: '/home' },
      { path: '/home', component: HomeView },
      { path: '/units', component: UnitsView },
      { path: '/people', component: PeopleView },
      { path: '/people/:id', component: PersonView },
      { path: '/schedules', component: SchedulesView },
      { path: '/duty-types', component: DutyTypesView },
      { path: '/duty-limits', component: DutyLimitsView },
      { path: '/reports/clearance-mismatches', component: ClearanceMismatchesView },
      { path: '/references', component: ReferencesView },
      { path: '/import', component: ImportView },
      { path: '/documents', component: DocumentsView },
      { path: '/dashboard', component: DashboardView },
      { path: '/operators', component: OperatorsView },
      { path: '/audit', component: AuditView },
      { path: '/:pathMatch(.*)*', redirect: '/home' },
    ],
  })

  createApp(App)
    .use(createPinia())
    .use(router)
    .use(PrimeVue, { theme: { preset: DutyFlowPreset, options: { darkModeSelector: '.app-dark' } }, locale: ru })
    .use(ToastService)
    .use(ConfirmationService)
    .directive('tooltip', Tooltip)
    .mount('#app')
}

bootstrap().catch((error: unknown) => {
  console.error(error)
  const app = document.getElementById('app')
  if (app) {
    app.textContent = 'Не удалось подключиться к сервису входа. Обновите страницу или обратитесь к администратору.'
  }
})
