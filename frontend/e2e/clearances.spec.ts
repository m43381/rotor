// Сценарии фазы 2b: типы нарядов с ролями, выдача допуска с предупреждением о требованиях,
// отчёт о несоответствиях. Данные — демо-seed (`just seed`, в том числе seed_duties).
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'

async function login(page: Page, username: string, path: string, heading: string) {
  await page.goto(path)
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: heading })).toBeVisible()
}

test('оператор курса видит вышестоящие наряды только для просмотра', async ({ page }) => {
  await login(page, 'course_operator', '/duty-types', 'Наряды')
  const academy = page.locator('.p-datatable-tbody > tr', { hasText: 'Дежурство по академии' })
  await expect(academy).toContainText('Вышестоящий')
  await expect(academy.getByRole('button', { name: 'Изменить наряд' })).toHaveCount(0)
  const own = page.locator('.p-datatable-tbody > tr', { hasText: 'Суточный наряд по курсу' })
  await expect(own).toContainText('Дневальный ×2')
  await expect(own.getByRole('button', { name: 'Изменить наряд' })).toBeVisible()
  // Наряды соседнего факультета не видны
  await expect(page.locator('.p-datatable-tbody > tr', { hasText: 'Наряд по факультету' })).toHaveCount(1)
})

test('администратор создаёт наряд с ролями и задаёт требование роли', async ({ page }) => {
  await login(page, 'faculty_admin', '/duty-types', 'Наряды')
  const name = `E2E наряд ${Date.now()}`
  await page.getByRole('button', { name: 'Новый наряд' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Название').fill(name)
  await dialog.getByLabel('Роль 1', { exact: true }).fill('Старший')
  await dialog.getByRole('button', { name: 'Добавить роль' }).click()
  await dialog.getByLabel('Роль 2', { exact: true }).fill('Помощник')
  await dialog.getByRole('button', { name: 'Создать' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Наряд создан' })).toBeVisible()

  const row = page.locator('.p-datatable-tbody > tr', { hasText: name })
  await expect(row).toContainText('Старший ×1, Помощник ×1')
  // Строка развёрнута после создания: роли и их требования
  await page.getByRole('button', { name: 'Изменить роль Старший' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Добавить требование' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Роль изменена' })).toBeVisible()
  await expect(page.getByText('Категория: «Курсант»')).toBeVisible()

  // Уборка: наряд выводится из действия (не удаляется) и пропадает из списка
  await row.getByRole('button', { name: 'Изменить наряд' }).click()
  await page.getByRole('dialog').getByText('Наряд действует').click()
  await page.getByRole('dialog').getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Наряд изменён' })).toBeVisible()
  await expect(row).toHaveCount(0)
})

test('допуск вопреки требованиям: предупреждение, обоснование, отзыв', async ({ page }) => {
  await login(page, 'faculty_admin', '/people', 'Личный состав')
  // Курсант не проходит требование «Постоянный состав» роли дежурного по факультету
  await expect(page.locator('.p-datatable-tbody tr .fio').first()).toBeVisible()
  await page.locator('.p-datatable-tbody tr', { hasText: 'Курсант' }).nth(5).locator('.fio').click()
  await page.getByRole('tab', { name: /Допуски/ }).click()

  await page.getByRole('button', { name: 'Выдать допуск' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.locator('#cl-role').click()
  await page.getByRole('option', { name: /Дежурный по факультету/ }).click()
  await expect(dialog.getByText('Человек не проходит требования роли')).toBeVisible()
  await expect(dialog.getByText('«Категория»: требуется «Постоянный состав»')).toBeVisible()
  const grant = dialog.getByRole('button', { name: 'Выдать вопреки требованиям' })
  await expect(grant).toBeDisabled()
  await dialog.getByLabel('Обоснование (обязательно)').fill('E2E: приказ начальника факультета')
  await grant.click()
  await expect(page.locator('.p-toast-message', { hasText: 'Допуск выдан вопреки требованиям' })).toBeVisible()

  const row = page.locator('.p-tabpanel:visible .p-datatable-tbody tr', { hasText: 'Дежурный по факультету' })
  await expect(row).toContainText('Выдан вопреки требованиям')
  await expect(row).toContainText('E2E: приказ начальника факультета')

  // Отзыв — тест повторяем, а повторная выдача после отзыва разрешена
  await row.getByRole('button', { name: 'Отозвать допуск' }).click()
  await page.getByRole('button', { name: 'Отозвать' }).last().click()
  await expect(page.locator('.p-toast-message', { hasText: 'Допуск отозван' })).toBeVisible()
  await expect(row).toHaveCount(0)
})

test('отчёт о несоответствиях допусков', async ({ page }) => {
  await login(page, 'faculty_admin', '/reports/clearance-mismatches', 'Несоответствия допусков')
  const row = page.locator('.p-datatable-tbody tr', { hasText: 'Дежурный по курсу' }).first()
  await expect(row).toContainText('Выдан вопреки требованиям')
  await expect(row).toContainText('не входит в допустимые')
})
