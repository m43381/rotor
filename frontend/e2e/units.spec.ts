// Сценарий фазы 1 (docs/roadmap.md): оператор входит через Keycloak, видит только своё
// поддерево и редактирует структуру. Учётки создаёт `just seed` (tools/gen/seed_org.py).
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'

async function login(page: Page, username: string) {
  await page.goto('/units')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Структура подразделений' })).toBeVisible()
  await expect(page.locator('.p-treetable-tbody tr').first()).toBeVisible()
}

function row(page: Page, name: string) {
  return page.locator('.p-treetable-tbody tr', { hasText: name })
}

test('оператор курса видит только своё поддерево', async ({ page }) => {
  await login(page, 'course_operator')

  await expect(row(page, '1 курс, факультет 1')).toBeVisible()
  await expect(row(page, 'Группа 111')).toBeVisible()
  await expect(page.getByText('Инженерный факультет')).toHaveCount(0)
  await expect(page.getByText('Факультет управления')).toHaveCount(0)

  // Своё подразделение: можно добавить дочернее, но нельзя перенести или расформировать.
  const own = row(page, '1 курс, факультет 1')
  await expect(own.getByRole('button', { name: 'Добавить дочернее' })).toBeEnabled()
  await expect(own.getByRole('button', { name: 'Перенести' })).toBeDisabled()
  await expect(own.getByRole('button', { name: 'Расформировать' })).toBeDisabled()
  await expect(row(page, 'Группа 111').getByRole('button', { name: 'Изменить' })).toBeEnabled()
})

test('наблюдатель не может менять структуру', async ({ page }) => {
  await login(page, 'faculty_viewer')
  await expect(row(page, 'Инженерный факультет')).toBeVisible()
  // Изменяющие действия; переход к графику подразделения — только навигация
  const actions = page.locator('.p-treetable-tbody button[aria-label]:not([aria-label="График нарядов"])')
  const count = await actions.count()
  expect(count).toBeGreaterThan(0)
  for (let i = 0; i < count; i++) await expect(actions.nth(i)).toBeDisabled()
})

test('администратор факультета создаёт, переименовывает и расформировывает группу', async ({
  page,
}) => {
  const name = `E2E группа ${Date.now()}`
  await login(page, 'faculty_admin')

  await row(page, '2 курс, факультет 1').getByRole('button', { name: 'Добавить дочернее' }).click()
  await page.getByLabel('Название', { exact: true }).fill(name)
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Подразделение создано')).toBeVisible()
  await expect(row(page, name)).toBeVisible()

  await row(page, name).getByRole('button', { name: 'Изменить' }).click()
  await page.getByLabel('Название', { exact: true }).fill(`${name} (изм.)`)
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Изменения сохранены')).toBeVisible()
  await expect(row(page, `${name} (изм.)`)).toBeVisible()

  await row(page, `${name} (изм.)`).getByRole('button', { name: 'Расформировать' }).click()
  await page.getByRole('button', { name: 'Расформировать' }).last().click()
  await expect(page.getByText('Подразделение расформировано')).toBeVisible()
  await expect(row(page, `${name} (изм.)`)).toHaveCount(0)
})

async function moveTo(page: Page, unitName: string, targetName: string) {
  await row(page, unitName).getByRole('button', { name: 'Перенести' }).click()
  await page.locator('.p-treeselect').click()
  await page.locator('.p-treeselect-overlay .p-tree-node-content', { hasText: targetName }).click()
  await page.getByRole('button', { name: 'Перенести', exact: true }).last().click()
  await expect(page.getByText('Подразделение перенесено').last()).toBeVisible()
}

test('администратор факультета переносит группу на другой курс', async ({ page }) => {
  await login(page, 'faculty_admin')
  await moveTo(page, 'Группа 113', '2 курс, факультет 1')

  // Группа стоит сразу после групп второго курса (порядок строк дерева)
  const names = await page.locator('.p-treetable-tbody tr td:first-child').allInnerTexts()
  const idx = (n: string) => names.findIndex((t) => t.includes(n))
  expect(idx('Группа 113')).toBeGreaterThan(idx('2 курс, факультет 1'))
  expect(idx('Группа 113')).toBeLessThan(idx('3 курс, факультет 1'))

  await moveTo(page, 'Группа 113', '1 курс, факультет 1')
})
