// Сценарии фазы 2a: личный состав в scope, карточка, освобождения, массовые операции.
// Данные — демо-seed (`just seed`): ~840 человек, личные номера вида «Д-…».
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'demo-password-1'

async function login(page: Page, username: string) {
  await page.goto('/people')
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(PASSWORD)
  await page.locator('#kc-login').click()
  await expect(page.getByRole('heading', { name: 'Личный состав' })).toBeVisible()
  await expect(page.locator('.p-datatable-tbody tr .fio').first()).toBeVisible()
}

async function total(page: Page): Promise<number> {
  const text = await page.getByText(/Найдено: \d+/).innerText()
  return Number(/Найдено: (\d+)/.exec(text)?.[1])
}

test('оператор курса видит только людей своего курса', async ({ page }) => {
  await login(page, 'course_operator')
  const own = await total(page)
  expect(own).toBeGreaterThan(50)
  expect(own).toBeLessThan(120)
  const units = await page.locator('.p-datatable-tbody tr td:nth-child(5)').allInnerTexts()
  // Курс 1 факультета 1 состоит из групп 111–113 (и самого курса)
  for (const u of units.filter(Boolean)) expect(u).toMatch(/Группа 11\d|1 курс, факультет 1/)
})

test('поиск по фамилии и по личному номеру', async ({ page }) => {
  await login(page, 'faculty_admin')
  const firstNo = (await page.locator('.p-datatable-tbody tr td:nth-child(6)').first().innerText()).trim()
  await page.getByLabel('Поиск').fill(firstNo)
  await expect(page.getByText('Найдено: 1', { exact: true })).toBeVisible()
  await page.getByLabel('Поиск').fill('несуществующаяфамилия')
  await expect(page.getByText('Никого не найдено')).toBeVisible()
})

test('администратор меняет карточку и видит запись в истории', async ({ page }) => {
  await login(page, 'faculty_admin')
  await page.locator('.p-datatable-tbody tr .fio').first().click()
  await expect(page.getByRole('tab', { name: 'Данные' })).toBeVisible()

  const note = `E2E примечание ${Date.now()}`
  await page.getByLabel('Примечание').fill(note)
  await page.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText('Изменения сохранены')).toBeVisible()

  await page.getByRole('tab', { name: 'История' }).click()
  await expect(page.locator('.p-datatable-tbody tr', { hasText: 'Изменён' }).first()).toContainText('note')
})

test('освобождение: добавление, запрет пересечения, удаление', async ({ page }) => {
  await login(page, 'faculty_admin')
  await page.locator('.p-datatable-tbody tr .fio').nth(3).click()
  await page.getByRole('tab', { name: /Освобождения/ }).click()
  const rowsBefore = await page.locator('.p-tabpanel:visible .p-datatable-tbody tr').count()

  const addExemption = async (from: string, to: string) => {
    await page.getByRole('button', { name: 'Добавить освобождение' }).click()
    await page.locator('#ex-range').fill(`${from} - ${to}`)
    await page.locator('#ex-range').press('Escape')
    await page.getByRole('dialog').getByRole('button', { name: 'Сохранить' }).click()
  }
  // Даты далеко в будущем, чтобы не пересечься с демо-освобождениями
  await addExemption('01.03.2031', '05.03.2031')
  await expect(page.getByText('Освобождение добавлено')).toBeVisible()
  await expect(page.locator('.p-tabpanel:visible .p-datatable-tbody tr', { hasText: '01.03.2031' })).toBeVisible()

  await addExemption('04.03.2031', '10.03.2031')
  await expect(page.getByText('Период пересекается с уже существующим освобождением')).toBeVisible()
  await page.getByRole('dialog').getByRole('button', { name: 'Отмена' }).click()

  await page
    .locator('.p-tabpanel:visible .p-datatable-tbody tr', { hasText: '01.03.2031' })
    .getByRole('button', { name: 'Удалить' })
    .click()
  await page.getByRole('button', { name: 'Удалить' }).last().click()
  await expect(page.getByText('Освобождение удалено')).toBeVisible()
  await expect(page.locator('.p-tabpanel:visible .p-datatable-tbody tr')).toHaveCount(Math.max(rowsBefore, 1))
})

test('наблюдатель видит карточку только для чтения', async ({ page }) => {
  await login(page, 'faculty_viewer')
  await expect(page.getByRole('button', { name: 'Добавить' })).toHaveCount(0)
  await page.locator('.p-datatable-tbody tr .fio').first().click()
  await expect(page.getByText('Только просмотр')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сохранить' })).toHaveCount(0)
  await expect(page.getByLabel('Фамилия')).toBeDisabled()
})

test('список разбит на страницы', async ({ page }) => {
  await login(page, 'faculty_admin')
  await expect(page.locator('.p-datatable-tbody tr')).toHaveCount(50)
  await expect(page.getByText(/^1–50 из \d+/)).toBeVisible()
  const firstOnPage1 = await page.locator('.p-datatable-tbody tr .fio').first().innerText()
  await page.locator('.p-paginator-next').click()
  await expect(page.getByText(/^51–100 из \d+/)).toBeVisible()
  await expect(page.locator('.p-datatable-tbody tr .fio').first()).not.toHaveText(firstOnPage1)
})

test('исключение из списков с причиной и восстановление', async ({ page }) => {
  await login(page, 'faculty_admin')
  const row = page.locator('.p-datatable-tbody tr').nth(7)
  const name = await row.locator('.fio').innerText()
  await row.locator('.fio').click()

  await page.getByRole('button', { name: 'Исключить из списков' }).click()
  await page.getByLabel('Комментарий (приказ, дата)').fill('Приказ № 1 (e2e)')
  await page.getByRole('dialog').getByRole('button', { name: 'Исключить' }).click()
  await expect(page.locator('.p-toast-message', { hasText: 'Исключён из списков личного состава' })).toBeVisible()
  await expect(page.getByText("Увольнение: Приказ № 1 (e2e)").first()).toBeVisible()

  // В общем списке его нет, с флажком «исключённые» — есть
  await page.getByRole('button', { name: 'Назад' }).click()
  await page.getByLabel('Поиск').fill(name.split(' ')[0] ?? name)
  await expect(page.locator('.p-datatable-tbody tr', { hasText: name })).toHaveCount(0)
  await page.getByText('Показывать исключённых из списков').click()
  await page.locator('.p-datatable-tbody tr', { hasText: name }).locator('.fio').click()

  await page.getByRole('button', { name: 'Восстановить в списках' }).click()
  await page.getByRole('button', { name: 'Восстановить' }).last().click()
  await expect(page.locator('.p-toast-message', { hasText: 'Восстановлен в списках' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Исключить из списков' })).toBeVisible()
})
