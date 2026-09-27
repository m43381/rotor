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
  await expect(page.getByRole('heading', { name: 'Нагрузка', exact: true })).toBeVisible()

  const duties = page.locator('.kpi', { hasText: 'нарядов' }).first().locator('span')
  await expect(duties).not.toHaveText('0')
  await expect(page.getByText('Сколько нарядов у людей')).toBeVisible()
  await expect(page.locator('canvas').first()).toBeVisible()
  await expect(page.getByText('Больше всех')).toBeVisible()

  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Отчёт XLSX' }).click()
  expect((await download).suggestedFilename()).toMatch(/^Нагрузка — .+\.xlsx$/)
})
