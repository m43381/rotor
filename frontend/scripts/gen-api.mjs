// Генерирует типы API из OpenAPI-схем сервисов: `npm run gen:api`.
// Схемы выгружаются из кода (tools/export_openapi.py), сервисы запускать не нужно.
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import openapiTS, { astToString } from 'openapi-typescript'

const root = new URL('../../', import.meta.url)
execFileSync('uv', ['run', 'python', 'tools/export_openapi.py'], { cwd: root, stdio: 'inherit' })

for (const service of ['org', 'personnel', 'scheduling']) {
  const schemaUrl = new URL(`../src/api/generated/${service}.openapi.json`, import.meta.url)
  const schema = JSON.parse(readFileSync(schemaUrl, 'utf-8'))
  const ast = await openapiTS(schema)
  const header = '// Сгенерировано `npm run gen:api` из OpenAPI сервиса. Не редактировать вручную.\n'
  writeFileSync(new URL(`../src/api/generated/${service}.ts`, import.meta.url), header + astToString(ast))
  console.log(`types: ${service}`)
}
