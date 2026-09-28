// Сценарии фазы 7b: изменение попадает в сводный журнал с «было → стало»; наблюдатель журнал не видит.
import { expect, test } from '@playwright/test'

const PASSWORD = 'demo-password-1'

test('изменение реквизитов видно в сводном журнале', async ({ page }) => {
  await page.goto('/documents')
  await page.locator('#username').fill('faculty_admin')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  const compiler = `П. П. Журналов${Date.now() % 10_000}`
  await page.locator('#req-compiler_name').fill(compiler)
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Реквизиты сохранены')).toBeVisible()

  await page.getByRole('link', { name: 'Журнал' }).click()
  await expect(page.getByRole('heading', { name: 'Журнал изменений' })).toBeVisible()
  const row = page.locator('.p-datatable-tbody > tr', { hasText: 'Изменены реквизиты документов' }).first()
  // Событие доходит до журнала асинхронно — список обновляется повторным запросом, пока
  // самой свежей записью не станет наше изменение (в журнале могут быть более ранние)
  await expect(async () => {
    await page.getByPlaceholder('Кто изменил').fill('')
    await page.getByPlaceholder('Кто изменил').fill('Иванов')
    await expect(row).toBeVisible({ timeout: 2_000 })
    await row.locator('.p-datatable-row-toggle-button').click()
    await expect(page.getByText(compiler)).toBeVisible({ timeout: 2_000 })
  }).toPass({ timeout: 20_000 })
  await expect(page.getByText('Составитель', { exact: true }).first()).toBeVisible()
})

test('наблюдатель не видит журнал', async ({ page }) => {
  await page.goto('/people')
  await page.locator('#username').fill('faculty_viewer')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Личный состав' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Журнал' })).toHaveCount(0)
})
