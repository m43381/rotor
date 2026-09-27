// Скриншоты интерфейса для пояснительной записки: `npm run screenshots` (стенд поднят, seed выполнен).
// Файлы складываются в frontend/screenshots/ (в git не попадают).
import { chromium } from '@playwright/test'
import { mkdirSync } from 'node:fs'

const base = process.env.E2E_BASE_URL ?? 'http://localhost:8088'
const out = new URL('../screenshots/', import.meta.url)
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || 'msedge' })
const page = await browser.newPage({ viewport: { width: 1360, height: 820 }, locale: 'ru-RU' })
const shot = (name) => page.screenshot({ path: new URL(`${name}.png`, out).pathname.replace(/^\/(\w:)/, '$1') })

await page.goto(base)
await page.waitForSelector('#username')
await shot('01-login')
await page.fill('#username', 'faculty_admin')
await page.fill('#password', 'demo-password-1')
await page.click('#kc-login')
await page.waitForSelector('.p-treetable-tbody tr')
await page.waitForTimeout(500)
await shot('02-units')

await page
  .locator('.p-treetable-tbody tr', { hasText: '3 курс, факультет 1' })
  .getByRole('button', { name: 'Перенести' })
  .click()
await page.locator('.p-treeselect').click()
await page.waitForTimeout(400)
await shot('03-move')

await page.keyboard.press('Escape')
await page.goto(`${base}/people`)
await page.waitForSelector('.p-datatable-tbody tr .fio')
await page.waitForTimeout(500)
await shot('04-people')
await page.locator('.p-datatable-tbody tr .fio').first().click()
await page.waitForSelector('h1')
await page.waitForTimeout(600)
await shot('05-person')
await page.getByRole('tab', { name: /Освобождения/ }).click()
await page.waitForTimeout(300)
await shot('06-person-exemptions')

// Фаза 2b: наряды с ролями и требованиями, допуски, отчёт о несоответствиях
await page.goto(`${base}/duty-types`)
await page.waitForSelector('.p-datatable-tbody tr')
await page.locator('.p-datatable-tbody > tr', { hasText: 'Наряд по факультету' }).locator('.p-datatable-row-toggle-button').click()
await page.locator('.p-datatable-tbody > tr', { hasText: 'Дежурство по академии' }).locator('.p-datatable-row-toggle-button').click()
await page.waitForTimeout(400)
await shot('07-duty-types')
await page.getByRole('button', { name: 'Изменить роль Помощник дежурного по факультету' }).click()
await page.waitForTimeout(400)
await shot('08-duty-role')
await page.keyboard.press('Escape')

await page.goto(`${base}/people`)
await page.waitForSelector('.p-datatable-tbody tr .fio')
await page.locator('.p-datatable-tbody tr', { hasText: 'Курсант' }).nth(2).locator('.fio').click()
await page.getByRole('tab', { name: /Допуски/ }).click()
await page.waitForTimeout(400)
await shot('09-person-clearances')
await page.getByRole('button', { name: 'Выдать допуск' }).click()
await page.locator('#cl-role').click()
await page.getByRole('option', { name: /Дежурный по факультету/ }).click()
await page.waitForTimeout(400)
await shot('10-clearance-warning')
await page.keyboard.press('Escape')

await page.goto(`${base}/reports/clearance-mismatches`)
await page.waitForSelector('.p-datatable-tbody tr')
await page.waitForTimeout(400)
await shot('11-clearance-mismatches')

await browser.close()
console.log(`Скриншоты: ${out.pathname}`)
