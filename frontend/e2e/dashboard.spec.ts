// Сценарии фазы 6c: дашборд нагрузки по read-model analytics и отчёт по нагрузке.
// Данные — демо-seed: графики на следующий месяц (черновики и опубликованные e2e графиков).
import { expect, test } from '@playwright/test'

const PASSWORD = 'demo-password-1'

function nextMonth(): { from: string; to: string } {
  const d = new Date()
  const first = new Date(d.getFullYear(), d.getMonth() + 1, 1)
  const last = new Date(d.getFullYear(), d.getMonth() + 2, 0)
  const iso = (x: Date) =>
    `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
  return { from: iso(first), to: iso(last) }
}

test('дашборд показывает нагрузку поддерева и выгружает отчёт', async ({ page }) => {
  const { from, to } = nextMonth()
  await page.goto(`/dashboard?from=${from}&to=${to}&drafts=1`)
  await page.locator('#username').fill('faculty_admin')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Аналитика', exact: true })).toBeVisible()

  const duties = page.locator('.stat', { has: page.getByText('Нарядов', { exact: true }) }).locator('.value')
  await expect(duties).not.toHaveText('0')
  await expect(page.getByRole('heading', { name: 'По дням недели' })).toBeVisible()
  await expect(page.locator('canvas').first()).toBeVisible()

  // Справедливость: кривая Лоренца, гистограмма и самые загруженные
  await page.getByRole('tab', { name: /Справедливость/ }).click()
  await expect(page.getByRole('heading', { name: 'Сколько нарядов у людей' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Больше всех' })).toBeVisible()

  // Конструктор: разрез по категориям с разбивкой по дням недели — график и таблица
  await page.getByRole('tab', { name: /Конструктор/ }).click()
  await expect(page.locator('.table-card .p-datatable-tbody tr').first()).toBeVisible()

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Отчёт XLSX' }).click()
  expect((await download).suggestedFilename()).toMatch(/^Нагрузка — .+\.xlsx$/)
})
