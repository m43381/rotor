// Сценарии фазы 6a: импорт по шаблону — шаблон, предпросмотр с ошибками, применение.
// Данные — демо-seed (`just seed`). Оператор курса видит подписи подразделений от своего курса.
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'
const COURSE = '1 курс, факультет 1'

async function login(page: Page, username: string) {
  await page.goto('/import')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Импорт', exact: true })).toBeVisible()
}

test('шаблон скачивается с именем формы', async ({ page }) => {
  await login(page, 'course_operator')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Скачать шаблон' }).click()
  expect((await download).suggestedFilename()).toBe('Шаблон — личный состав.xlsx')
})

test('импорт с ошибкой: предпросмотр, применение только корректных строк', async ({ page }) => {
  await login(page, 'course_operator')
  const surname = `Импортов${Date.now() % 1_000_000}`
  const csv = [
    'Фамилия;Имя;Подразделение;Категория',
    `${surname};Иван;${COURSE} / Группа 111;Курсант`,
    `Безымянный;;${COURSE} / Группа 111;Курсант`,
  ].join('\n')
  await page.getByTestId('import-file').setInputFiles({
    name: 'люди.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv, 'utf-8'),
  })
  await expect(page.getByText('создать 1')).toBeVisible()
  await expect(page.getByText('ошибок 1')).toBeVisible()
  await expect(page.getByText('Имя обязательно')).toBeVisible()

  const apply = page.getByRole('button', { name: 'Применить', exact: true })
  await expect(apply).toBeDisabled()
  await page.getByText('Применить только корректные строки').click()
  await apply.click()
  await expect(page.getByText('Импорт применён')).toBeVisible()
  await expect(page.getByText('Применён', { exact: true }).first()).toBeVisible()

  await page.goto('/people')
  await page.getByLabel('Поиск').fill(surname)
  await expect(page.getByText('Найдено: 1', { exact: true })).toBeVisible()
})

test('наблюдатель не видит раздел импорта', async ({ page }) => {
  await page.goto('/people')
  await page.locator('#username').fill('faculty_viewer')
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Личный состав' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Импорт' })).toHaveCount(0)
})
