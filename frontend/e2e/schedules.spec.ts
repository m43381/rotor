// Сценарии фазы 3a: таблица месяца, делегирование роли курсу, принятие, возврат себе,
// публикация. Данные — демо-seed (`just seed`, в том числе seed_schedules на следующий месяц).
// Тесты возвращают данные в исходное состояние, кроме публикации (она идемпотентна).
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'

function month(offset: number): string {
  const d = new Date()
  const m = new Date(d.getFullYear(), d.getMonth() + offset, 1)
  return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}-01`
}

async function login(page: Page, username: string, path: string) {
  await page.goto(path)
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Графики' })).toBeVisible()
}

const roleCells = (page: Page, role: string) =>
  page.locator('.grid tbody tr', { has: page.locator('td.role', { hasText: role }) }).first().locator('td.cell')

test('факультет делегирует роль курсу, курс принимает, факультет возвращает себе', async ({ page }) => {
  await login(page, 'faculty_admin', `/schedules?month=${month(1)}`)
  const duty = roleCells(page, 'Дежурный по факультету')
  await expect(duty.first()).toBeVisible()

  // Две ячейки дежурного (10-е и 11-е) — первому курсу
  await duty.nth(9).click()
  await duty.nth(10).click({ modifiers: ['Shift'] })
  await expect(page.getByText('Выбрано ячеек: 2')).toBeVisible()
  await page.locator('#executor').click()
  await page.getByRole('option', { name: '1 курс, факультет 1' }).click()
  await page.getByRole('button', { name: 'Делегировать' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Роль передана' })).toBeVisible()
  await expect(duty.nth(9)).toHaveClass(/delegated_pending/)
  await expect(duty.nth(9)).toHaveText('1КФ1')

  // Курс видит входящие и принимает их
  await page.goto(`/schedules?month=${month(1)}`)
  await page.locator('.unit-filter .p-treeselect').click()
  await page.locator('.p-tree-node-label', { hasText: '1 курс, факультет 1' }).click()
  const incoming = roleCells(page, 'Дежурный по факультету')
  await expect(incoming.nth(9)).toHaveClass(/incoming_pending/)
  await incoming.nth(9).click()
  await incoming.nth(10).click({ modifiers: ['Shift'] })
  await page.getByRole('button', { name: 'Принять (2)' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Входящие приняты' })).toBeVisible()
  await expect(incoming.nth(9)).toHaveClass(/incoming_active/)

  // Факультет забирает роль обратно — нужно подтверждение, т. к. курс уже принял
  await page.goto(`/schedules?month=${month(1)}`)
  const back = roleCells(page, 'Дежурный по факультету')
  await expect(back.nth(9)).toHaveClass(/delegated_accepted/)
  await back.nth(9).click()
  await back.nth(10).click({ modifiers: ['Shift'] })
  await page.getByRole('button', { name: 'Вернуть себе' }).click()
  await page.getByRole('button', { name: 'Изменить' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Роль возвращена' })).toBeVisible()
  await expect(back.nth(9)).toHaveClass(/\bown\b/)
})

test('курс создаёт и публикует график', async ({ page }) => {
  await login(page, 'course_operator', `/schedules?month=${month(2)}`)
  const create = page.getByRole('button', { name: 'Создать график' })
  if (await create.isVisible()) {
    await create.click()
    await expect(page.locator('.p-toast-message', { hasText: 'График создан' })).toBeVisible()
  }
  await expect(roleCells(page, 'Дневальный').first()).toBeVisible()
  const publish = page.getByRole('button', { name: 'Опубликовать' })
  if (await publish.isVisible()) {
    await publish.click()
    await page.getByRole('button', { name: 'Опубликовать' }).last().click()
  }
  await expect(page.locator('.title .p-tag', { hasText: 'Опубликован' })).toBeVisible()
})

test('наблюдатель видит график без действий', async ({ page }) => {
  await login(page, 'faculty_viewer', `/schedules?month=${month(1)}`)
  await expect(page.locator('.grid')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Опубликовать' })).toHaveCount(0)
  await expect(page.locator('.selection-bar')).toHaveCount(0)
})
