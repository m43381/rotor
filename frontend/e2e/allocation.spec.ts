// Сценарии фазы 4b: автораспределение с предпросмотром, объяснением и применением.
// Данные — демо-seed; применение идёт в режиме «пересобрать автоматические», поэтому тест
// повторяем: каждый прогон заменяет автоматические назначения предыдущего.
import { expect, test, type Page } from '@playwright/test'

function month(offset: number): string {
  const d = new Date()
  const m = new Date(d.getFullYear(), d.getMonth() + offset, 1)
  return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}-01`
}

async function login(page: Page, username: string, path: string) {
  await page.goto(path)
  await page.locator('#username').fill(username)
  await page.locator('#password').fill('demo-password-1')
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Графики' })).toBeVisible()
}

async function calculate(page: Page, mode?: 'rebuild') {
  await page.getByRole('button', { name: 'Распределить…' }).click()
  const dialog = page.getByRole('dialog', { name: 'Автораспределение' })
  if (mode) await dialog.getByText('Пересобрать автоматические').click()
  await dialog.getByRole('button', { name: 'Рассчитать' }).click()
  await expect(page.locator('.panel')).toBeVisible()
}

test('предпросмотр с объяснением и отмена', async ({ page }) => {
  await login(page, 'course_operator', `/schedules?month=${month(1)}`)
  await calculate(page)
  const panel = page.locator('.panel')
  await expect(panel.getByText('Предпросмотр: люди')).toBeVisible()
  const proposed = page.locator('td.cell.proposed')
  if ((await proposed.count()) > 0) {
    await proposed.first().click()
    await expect(panel.getByText(/лучший из \d+ допустимых/)).toBeVisible()
    await expect(panel.getByText('Нагрузка с затуханием')).toBeVisible()
  }
  await panel.getByRole('button', { name: 'Отменить' }).click()
  await expect(panel).toHaveCount(0)
  await expect(page.locator('td.cell.proposed')).toHaveCount(0)
})

test('применение распределения людей', async ({ page }) => {
  await login(page, 'course_operator', `/schedules?month=${month(3)}`)
  const create = page.getByRole('button', { name: 'Создать график' })
  await expect(page.locator('.grid').or(create)).toBeVisible()
  if (await create.isVisible()) {
    await create.click()
    await expect(page.locator('.p-toast-message', { hasText: 'График создан' })).toBeVisible()
  }
  await calculate(page, 'rebuild')
  const panel = page.locator('.panel')
  await expect(panel.getByText(/мест закрыто/)).toBeVisible()
  await panel.getByRole('button', { name: 'Применить' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Распределение применено' })).toBeVisible()
  await expect(panel).toHaveCount(0)
  // Роли курса заполнены: у дежурного по курсу — «1/1»
  const duty = page
    .locator('.grid tbody tr', { has: page.locator('td.role', { hasText: 'Дежурный по курсу' }) })
    .locator('td.cell')
  await expect(duty.first()).toHaveText('1/1')

  // История: последний прогон — применён
  await page.getByRole('button', { name: 'Распределить…' }).click()
  const dialog = page.getByRole('dialog', { name: 'Автораспределение' })
  await expect(dialog.locator('.history-row').first()).toContainText('Применён')
  await dialog.getByRole('button', { name: 'Отмена' }).click()
})

test('распределение ролей по курсам', async ({ page }) => {
  await login(page, 'faculty_admin', `/schedules?month=${month(1)}`)
  await page.getByRole('button', { name: 'Распределить…' }).click()
  const dialog = page.getByRole('dialog', { name: 'Автораспределение' })
  await dialog.getByText('Ячейки по дочерним подразделениям').click()
  await dialog.getByRole('button', { name: 'Рассчитать' }).click()
  const panel = page.locator('.panel')
  await expect(panel.getByText('Предпросмотр: подразделения')).toBeVisible()
  await expect(panel.getByText(/ячеек передано/)).toBeVisible()
  // Не применяем: демо-график факультета остаётся для других сценариев
  await panel.getByRole('button', { name: 'Отменить' }).click()
  await expect(panel).toHaveCount(0)
})
