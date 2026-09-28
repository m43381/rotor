import { defineConfig } from '@playwright/test'

// E2E против поднятого стенда (`just up && just seed`). Браузер — установленный в системе
// (PW_CHANNEL=msedge|chrome), потому что на закрытом контуре скачать Chromium нельзя.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  // Один браузер: тесты входят под одними и теми же демо-учётками, а параллельные входы
  // срабатывают на защиту Keycloak от перебора паролей (brute force detection).
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'https://localhost:8443',
    // Стенд — на сертификате внутреннего УЦ (фаза 7c); браузер тестов ему не доверяет
    ignoreHTTPSErrors: true,
    channel: process.env.PW_CHANNEL || undefined,
    headless: true,
    locale: 'ru-RU',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  outputDir: 'e2e-results',
})
