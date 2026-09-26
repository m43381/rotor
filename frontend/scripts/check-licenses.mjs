// Проверка лицензий production-зависимостей фронтенда: `npm run check:licenses`.
// Причина: PrimeVue 5 и primeicons 8 стали коммерческими (ключ лицензии, баннер в UI).
// Разрешены только пермиссивные лицензии; всё остальное роняет проверку (docs/adr/0012).
import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const ALLOWED = new Set(['MIT', 'ISC', 'BSD-2-Clause', 'BSD-3-Clause', 'Apache-2.0', '0BSD'])

const tree = JSON.parse(
  execSync('npm ls --omit=dev --all --json --long', {
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
  }),
)

const seen = new Map()
const walk = (deps = {}) => {
  for (const [name, info] of Object.entries(deps)) {
    const key = `${name}@${info.version}`
    if (seen.has(key) || !info.path) continue
    const pkg = JSON.parse(readFileSync(join(info.path, 'package.json'), 'utf-8'))
    const license = typeof pkg.license === 'string' ? pkg.license : pkg.license?.type ?? 'UNKNOWN'
    seen.set(key, license)
    walk(info.dependencies)
  }
}
walk(tree.dependencies)

const isAllowed = (license) =>
  license
    .replace(/[()]/g, '')
    .split(/\s+OR\s+/)
    .some((part) => ALLOWED.has(part.trim()))

const bad = [...seen].filter(([, license]) => !isAllowed(license))
if (bad.length) {
  console.error('Недопустимые лицензии production-зависимостей:')
  for (const [pkg, license] of bad) console.error(`  ${pkg}: ${license}`)
  process.exit(1)
}
console.log(`Лицензии в порядке: ${seen.size} пакетов`)
