// Сценарии фазы 3b: назначение людей в ячейку, нарушение отдыха с обоснованием, лимиты.
// Данные — демо-seed (график факультета 1 на следующий месяц, люди назначены на 1–10 число).
// Тесты убирают за собой назначения и лимиты.
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'

function nextMonth(): string {
  const d = new Date()
  const m = new Date(d.getFullYear(), d.getMonth() + 1, 1)
  return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}-01`
}

async function login(page: Page, path: string, heading: string) {
  await page.goto(path)
  await page.locator('#username').fill('faculty_admin')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: heading })).toBeVisible()
}

const dutyCells = (page: Page) =>
  page
    .locator('.grid tbody tr', { has: page.locator('td.role', { hasText: 'Дежурный по факультету' }) })
    .first()
    .locator('td.cell')

async function openCell(page: Page, day: number) {
  await dutyCells(page).nth(day - 1).dblclick()
  await expect(page.locator('.cell-panel')).toBeVisible()
  await expect(page.locator('.cell-panel').getByText(/Назначены \(/)).toBeVisible()
}

async function removeAll(page: Page) {
  const buttons = page.locator('.cell-panel').getByRole('button', { name: /^Снять / })
  // Ждём, пока список обновится после каждого снятия, иначе кнопка «уезжает» из-под клика
  for (let n = await buttons.count(); n > 0; n--) {
    await buttons.first().click()
    await expect(buttons).toHaveCount(n - 1)
  }
}

test('назначение человека в ячейку и снятие', async ({ page }) => {
  await login(page, `/schedules?month=${nextMonth()}`, 'Графики')
  await openCell(page, 20)
  const panel = page.locator('.cell-panel')
  await removeAll(page)
  await panel.getByRole('button', { name: /^Назначить / }).first().click()
  await expect(page.locator('.p-toast-message', { hasText: 'Назначен' })).toBeVisible()
  await expect(panel.getByText('Назначены (1 из 1)')).toBeVisible()
  await expect(panel.getByText('Роль укомплектована.')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dutyCells(page).nth(19)).toHaveText('1/1')

  await openCell(page, 20)
  await removeAll(page)
  await page.keyboard.press('Escape')
  await expect(dutyCells(page).nth(19)).toHaveText('')
})

test('нарушение отдыха — только с обоснованием', async ({ page }) => {
  await login(page, `/schedules?month=${nextMonth()}`, 'Графики')
  const panel = page.locator('.cell-panel')
  await openCell(page, 20)
  await removeAll(page)
  const first = panel.locator('.p-datatable-tbody tr').first()
  const name = (await first.locator('.name').innerText()).trim()
  await first.getByRole('button', { name: /^Назначить / }).click()
  await expect(panel.getByText('Назначены (1 из 1)')).toBeVisible()
  await page.keyboard.press('Escape')

  // 22-го тот же человек отдохнул бы только 24 ч из 48
  await openCell(page, 22)
  await removeAll(page)
  await panel.getByPlaceholder('Поиск по ФИО').fill(name)
  const row = panel.locator('.p-datatable-tbody tr', { hasText: name })
  await expect(row).toContainText('нужно 48 ч')
  await row.getByRole('button', { name: /^Назначить / }).click()
  const dialog = page.getByRole('dialog', { name: 'Назначить с нарушением?' })
  await expect(dialog).toBeVisible()
  const confirm = dialog.getByRole('button', { name: 'Назначить с нарушением' })
  await expect(confirm).toBeDisabled()
  await dialog.getByLabel('Обоснование (обязательно)').fill('E2E: некем заменить')
  await confirm.click()
  await expect(panel.getByText('Отдых нарушен')).toBeVisible()
  await expect(panel.getByText('Обоснование: E2E: некем заменить')).toBeVisible()

  await removeAll(page)
  await page.keyboard.press('Escape')
  await openCell(page, 20)
  await removeAll(page)
})

test('лимит нарядов: создание и удаление', async ({ page }) => {
  await login(page, '/duty-limits', 'Лимиты нарядов')
  await page.getByRole('button', { name: 'Новый лимит' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.locator('#lim-max input, input#lim-max').first().fill('7')
  await dialog.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Лимит сохранён' })).toBeVisible()
  const row = page.locator('.p-datatable-tbody tr', { hasText: 'Факультет управления' }).filter({ hasText: '7' })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: 'Удалить лимит' }).click()
  await page.getByRole('button', { name: 'Удалить' }).last().click()
  await expect(row).toHaveCount(0)
})
