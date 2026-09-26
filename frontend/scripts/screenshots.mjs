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

await browser.close()
console.log(`Скриншоты: ${out.pathname}`)
