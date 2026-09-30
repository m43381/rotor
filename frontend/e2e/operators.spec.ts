// Сценарии фазы 7a: администратор факультета создаёт оператора курса, тот входит с временным
// паролем и задаёт свой, администратор блокирует учётную запись.
import { expect, test } from '@playwright/test'

const PASSWORD = 'demo-password-1'

test('создание оператора, первый вход со сменой пароля, блокировка', async ({ page, browser }) => {
  const username = `e2e.op${Date.now() % 1_000_000}`
  await page.goto('/operators')
  await page.locator('#username').fill('faculty_admin')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Операторы' })).toBeVisible()
  await expect(page.getByText('faculty_admin', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Добавить оператора' }).click()
  await page.locator('#op-username').fill(username)
  await page.locator('#op-last').fill('Проверкин')
  await page.locator('#op-first').fill('Тест')
  await page.locator('.p-dialog .p-treeselect').click()
  await page
    .locator('.p-treeselect-overlay .p-tree-node-content', { hasText: '1 курс, факультет 1' })
    .first()
    .click()
  await expect(page.locator('#op-role')).toContainText('Оператор')
  await page.getByRole('button', { name: 'Создать' }).click()
  const temporary = (await page.getByTestId('temporary-password').innerText()).trim()
  expect(temporary).toHaveLength(12)
  await page.getByRole('button', { name: 'Готово' }).click()

  // Первый вход: Keycloak требует сменить временный пароль
  const other = await (await browser.newContext()).newPage()
  await other.goto('/people')
  await other.locator('#username').fill(username)
  await other.locator('#password').fill(temporary)
  await other.locator('#kc-login').click()
  await other.locator('#password-new').fill('NewPassword123')
  await other.locator('#password-confirm').fill('NewPassword123')
  await other.locator('[type=submit]').click()
  await expect(other.getByRole('heading', { name: 'Личный состав' })).toBeVisible()
  // В шапке: подразделение оператора рядом с названием системы, роль — под именем
  await expect(other.locator('.brand-sub')).toHaveText('1 курс, факультет 1')
  await expect(other.locator('.user-text small')).toHaveText('Оператор')
  await other.context().close()

  // Блокировка
  await page.getByPlaceholder('Логин или ФИО').fill(username)
  await expect(page.getByText('Найдено: 1', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: `Заблокировать ${username}` }).click()
  await page.getByRole('button', { name: 'Заблокировать', exact: true }).click()
  await expect(page.getByText('заблокирован', { exact: true })).toBeVisible()
})

test('оператор курса не видит раздел операторов', async ({ page }) => {
  await page.goto('/people')
  await page.locator('#username').fill('course_operator')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Личный состав' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Операторы' })).toHaveCount(0)
})
