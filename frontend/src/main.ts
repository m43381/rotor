import 'primeicons/primeicons.css'
import './styles.css'

import Aura from '@primeuix/themes/aura'
import { createPinia } from 'pinia'
import PrimeVue from 'primevue/config'
import ConfirmationService from 'primevue/confirmationservice'
import ToastService from 'primevue/toastservice'
import Tooltip from 'primevue/tooltip'
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { ensureSignedIn } from './auth'
import { ru } from './locale/ru'
import ClearanceMismatchesView from './views/ClearanceMismatchesView.vue'
import DutyTypesView from './views/DutyTypesView.vue'
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
      { path: '/', redirect: '/units' },
      { path: '/units', component: UnitsView },
      { path: '/people', component: PeopleView },
      { path: '/people/:id', component: PersonView },
      { path: '/schedules', component: SchedulesView },
      { path: '/duty-types', component: DutyTypesView },
      { path: '/reports/clearance-mismatches', component: ClearanceMismatchesView },
      { path: '/references', component: ReferencesView },
      { path: '/:pathMatch(.*)*', redirect: '/units' },
    ],
  })

  createApp(App)
    .use(createPinia())
    .use(router)
    .use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: '.app-dark' } }, locale: ru })
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
