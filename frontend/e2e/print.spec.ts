// Сценарии фазы 6b: реквизиты подразделения, печать графика и суточного наряда.
// Данные — демо-seed (`just seed`, в том числе графики на следующий месяц).
import { readFileSync } from 'node:fs'

import { expect, test, type Download, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'

function month(offset: number): string {
  const d = new Date()
  const m = new Date(d.getFullYear(), d.getMonth() + offset, 1)
  return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, '0')}-01`
}

async function login(page: Page, username: string, path: string, heading: string) {
  await page.goto(path)
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
}

async function bytes(download: Download): Promise<Buffer> {
  // PRINT_SAVE_DIR — сохранить скачанные документы (посмотреть глазами, скриншоты для записки)
  const dir = process.env.PRINT_SAVE_DIR
  if (dir) await download.saveAs(`${dir}/${download.suggestedFilename()}`)
  const path = await download.path()
  expect(path).toBeTruthy()
  return readFileSync(path!)
}

test('реквизиты факультета наследуются курсом', async ({ page, browser }) => {
  await login(page, 'faculty_admin', '/documents', 'Документы')
  await page.locator('#req-approver_position').fill('Начальник факультета')
  await page.locator('#req-approver_rank').fill('полковник')
  await page.locator('#req-approver_name').fill('И. И. Иванов')
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Реквизиты сохранены')).toBeVisible()

  // Другой оператор — в отдельном контексте браузера (токен хранится в приложении)
  const other = await (await browser.newContext()).newPage()
  await login(other, 'course_operator', '/documents', 'Документы')
  await expect(other.getByText('Своих реквизитов нет')).toBeVisible()
  await expect(other.locator('#req-approver_name')).toHaveValue('И. И. Иванов')
  await expect(other.locator('#req-approver_name')).toBeDisabled()
  await other.context().close()
})

test('печать графика в PDF и XLSX и суточного наряда в DOCX', async ({ page }) => {
  await login(page, 'faculty_admin', `/schedules?month=${month(1)}`, 'Графики')
  await expect(page.locator('.grid tbody tr').first()).toBeVisible()

  await page.getByRole('button', { name: 'Печать…' }).click()
  let download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать' }).click()
  let file = await download
  expect(file.suggestedFilename()).toMatch(/^График нарядов — .+\.pdf$/)
  expect((await bytes(file)).subarray(0, 4).toString()).toBe('%PDF')

  await page.getByRole('button', { name: 'Печать…' }).click()
  await page.getByText('Excel (XLSX)').click()
  download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать' }).click()
  file = await download
  expect(file.suggestedFilename()).toMatch(/\.xlsx$/)
  expect((await bytes(file)).subarray(0, 2).toString()).toBe('PK')

  await page.getByRole('button', { name: 'Печать…' }).click()
  await page.getByText('Ведомость суточного наряда на дату').click()
  await page.getByText('Word (DOCX)').click()
  download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать' }).click()
  file = await download
  expect(file.suggestedFilename()).toMatch(/^Суточный наряд — .+\.docx$/)
  expect((await bytes(file)).subarray(0, 2).toString()).toBe('PK')
})
