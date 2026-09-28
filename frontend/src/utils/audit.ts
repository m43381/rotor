// Человекочитаемые подписи сводного журнала аудита (фаза 7b). Неизвестные коды показываются
// как есть — журнал не должен терять записи из-за отсутствия подписи.

export const ACTION_LABELS: Record<string, string> = {
  'unit.create': 'Создано подразделение',
  'unit.update': 'Изменено подразделение',
  'unit.move': 'Подразделение перенесено',
  'unit.deactivate': 'Подразделение расформировано',
  'unit_type.create': 'Создан тип подразделения',
  'unit_type.update': 'Изменён тип подразделения',
  'rank.create': 'Добавлено звание',
  'rank.update': 'Изменено звание',
  'calendar.upsert': 'Изменён производственный календарь',
  'calendar.delete': 'Удалён день календаря',
  'position.create': 'Добавлена должность',
  'position.update': 'Изменена должность',
  'attribute_definition.create': 'Добавлена характеристика',
  'attribute_definition.update': 'Изменена характеристика',
  'exemption_reason.create': 'Добавлена причина освобождения',
  'exemption_reason.update': 'Изменена причина освобождения',
  'person.create': 'Добавлен человек',
  'person.update': 'Изменена карточка',
  'person.transfer': 'Перевод в другое подразделение',
  'person.archive': 'Исключён из списков',
  'person.restore': 'Восстановлен в списках',
  'exemption.create': 'Добавлено освобождение',
  'exemption.update': 'Изменено освобождение',
  'exemption.delete': 'Удалено освобождение',
  'clearance.grant': 'Выдан допуск',
  'clearance.grant_override': 'Выдан допуск вопреки требованиям',
  'clearance.update': 'Изменён срок допуска',
  'clearance.revoke': 'Отозван допуск',
  'duty_type.create': 'Создан наряд',
  'duty_type.update': 'Изменён наряд',
  'duty_role.create': 'Добавлена роль наряда',
  'duty_role.update': 'Изменена роль наряда',
  'duty_limit.create': 'Задан лимит нарядов',
  'duty_limit.update': 'Изменён лимит нарядов',
  'duty_limit.delete': 'Удалён лимит нарядов',
  'schedule.create': 'Создан график',
  'schedule.publish': 'График опубликован',
  'schedule.archive': 'График в архиве',
  'day_plan.delegate': 'Ячейки переданы подразделению',
  'day_plan.accept': 'Входящие ячейки приняты',
  'day_plan.pin': 'Ячейки закреплены',
  'assignment.create': 'Назначен в наряд',
  'assignment.override': 'Назначен с нарушением (подтверждено)',
  'assignment.auto': 'Назначен автораспределением',
  'assignment.delete': 'Снят с наряда',
  'assignment.pin': 'Назначение закреплено',
  'allocation.preview': 'Рассчитано автораспределение',
  'allocation.apply': 'Применено автораспределение',
  'allocation.discard': 'Отменён предпросмотр распределения',
  'document_settings.update': 'Изменены реквизиты документов',
  'document_settings.clear': 'Удалены реквизиты документов',
  'print_template.upload': 'Загружен шаблон печатной формы',
  'print_template.reset': 'Возвращён встроенный шаблон',
  'operator.create': 'Создан оператор',
  'operator.update': 'Изменён оператор',
  'operator.block': 'Оператор заблокирован',
  'operator.unblock': 'Оператор разблокирован',
  'operator.reset_password': 'Сброшен пароль оператора',
  'operator.logout': 'Завершены сессии оператора',
}

export const ENTITY_LABELS: Record<string, string> = {
  unit: 'Подразделение',
  unit_type: 'Тип подразделения',
  rank: 'Звание',
  calendar: 'Календарь',
  position: 'Должность',
  attribute_definition: 'Характеристика',
  exemption_reason: 'Причина освобождения',
  person: 'Человек',
  exemption: 'Освобождение',
  clearance: 'Допуск',
  duty_type: 'Наряд',
  duty_role: 'Роль наряда',
  duty_limit: 'Лимит',
  schedule: 'График',
  day_plan: 'Ячейка графика',
  assignment: 'Назначение',
  allocation_run: 'Автораспределение',
  document_settings: 'Реквизиты документов',
  print_template: 'Шаблон формы',
  operator: 'Оператор',
}

export const SERVICE_LABELS: Record<string, string> = {
  org: 'Структура',
  personnel: 'Личный состав',
  scheduling: 'Графики',
  documents: 'Документы',
  'auth-admin': 'Операторы',
}

const FIELD_LABELS: Record<string, string> = {
  last_name: 'Фамилия',
  first_name: 'Имя',
  middle_name: 'Отчество',
  personal_no: 'Личный номер',
  rank_id: 'Звание',
  position_id: 'Должность',
  unit_id: 'Подразделение',
  parent_id: 'Вышестоящее',
  person_id: 'Человек',
  is_active: 'Действует',
  note: 'Примечание',
  name: 'Название',
  short_name: 'Сокращение',
  code: 'Код',
  order: 'Порядок',
  level: 'Уровень',
  date: 'Дата',
  date_from: 'С',
  date_to: 'По',
  valid_from: 'Действует с',
  valid_to: 'Действует по',
  reason_id: 'Причина',
  comment: 'Комментарий',
  status: 'Статус',
  role: 'Роль',
  enabled: 'Активен',
  username: 'Логин',
  headcount: 'Численность',
  start_time: 'Начало',
  duration_minutes: 'Длительность, мин',
  kind: 'Вид',
  attributes: 'Характеристики',
  executor_unit_id: 'Исполнитель',
  person_name: 'Человек',
  approver_position: 'Должность утверждающего',
  approver_rank: 'Звание утверждающего',
  approver_name: 'Утверждающий',
  compiler_position: 'Должность составителя',
  compiler_rank: 'Звание составителя',
  compiler_name: 'Составитель',
}

// Коды статусов и ролей, которые встречаются в значениях «было/стало»
const VALUE_LABELS: Record<string, string> = {
  draft: 'черновик',
  published: 'опубликован',
  archived: 'в архиве',
  preview_ready: 'предпросмотр',
  queued: 'в очереди',
  running: 'считается',
  applied: 'применён',
  discarded: 'отменён',
  stale: 'устарел',
  failed: 'ошибка',
  pending: 'ожидает принятия',
  accepted: 'принято',
  manual: 'вручную',
  auto: 'автоматически',
  superadmin: 'суперадминистратор',
  unit_admin: 'администратор подразделения',
  operator: 'оператор',
  viewer: 'наблюдатель',
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key
}

export function valueText(value: unknown, unitName: (id: string) => string | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'да' : 'нет'
  if (typeof value === 'string') {
    const unit = unitName(value)
    if (unit) return unit
    if (VALUE_LABELS[value]) return VALUE_LABELS[value]
    const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    if (iso) return `${iso[3]}.${iso[2]}.${iso[1]}`
    return value
  }
  if (Array.isArray(value)) return value.map((v) => valueText(v, unitName)).join(', ')
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => `${fieldLabel(k)}: ${valueText(v, unitName)}`)
      .join('; ')
  }
  return String(value)
}

export function changes(
  before: Record<string, unknown> | null | undefined,
  after: Record<string, unknown> | null | undefined,
): { field: string; before: unknown; after: unknown }[] {
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]))
  return keys.map((k) => ({ field: k, before: before?.[k], after: after?.[k] }))
}
