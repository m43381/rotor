"""Файлы импорта: xlsx-шаблон для заполнения, разбор xlsx/csv в строки, отчёт об ошибках.

Столбцы шаблона описывает сервис-владелец данных (`personnel`, `/imports/{kind}/template`),
здесь — только их представление в Excel:
- лист «Данные» с заголовками (обязательные — со звёздочкой), выпадающими списками и
  форматом дат;
- скрытый лист «Списки» со значениями списков — ссылки на диапазоны вместо встроенного
  текста, который Excel ограничивает 255 символами;
- лист «Инструкция».

Разбор сопоставляет столбцы файла с шаблоном по заголовку (регистр, звёздочка и лишние
пробелы не важны), пропускает пустые строки, даты приводит к ISO. Бизнес-проверки делает
владелец данных.
"""

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from dutyflow_common.errors import ValidationFailedError

DATA_SHEET = "Данные"
LISTS_SHEET = "Списки"
HELP_SHEET = "Инструкция"
MAX_ROWS = 20_000
TEMPLATE_ROWS = 2_000  # на сколько строк растянуть списки и форматы в шаблоне

HEADER_FILL = PatternFill("solid", fgColor="DCE6F1")
REQUIRED_FONT = Font(bold=True, color="9C0006")
ERROR_FILL = PatternFill("solid", fgColor="FFC7CE")
WARNING_FILL = PatternFill("solid", fgColor="FFEB9C")
OK_FILL = PatternFill("solid", fgColor="C6EFCE")

ACTION_LABELS = {
    "create": "Будет создано",
    "update": "Будет изменено",
    "unchanged": "Без изменений",
    "error": "Ошибка",
}


def header(column: dict[str, Any]) -> str:
    return f"{column['title']} *" if column.get("required") else str(column["title"])


def _norm(title: Any) -> str:
    return " ".join(str(title or "").replace("*", " ").split()).lower()


# --- шаблон ------------------------------------------------------------------------------------


def build_template(template: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = DATA_SHEET
    lists = wb.create_sheet(LISTS_SHEET)
    lists.sheet_state = "hidden"
    list_col = 0
    for i, col in enumerate(template["columns"], start=1):
        letter = get_column_letter(i)
        cell = ws.cell(row=1, column=i, value=header(col))
        cell.fill = HEADER_FILL
        cell.font = REQUIRED_FONT if col.get("required") else Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[letter].width = max(14, min(45, len(header(col)) + 4))
        area = f"{letter}2:{letter}{TEMPLATE_ROWS + 1}"
        if col.get("hint"):
            from openpyxl.comments import Comment

            cell.comment = Comment(str(col["hint"]), "DutyFlow")
        options = col.get("options")
        if col.get("type") in ("list", "bool") and options:
            list_col += 1
            lletter = get_column_letter(list_col)
            lists.cell(row=1, column=list_col, value=col["title"])
            for n, option in enumerate(options, start=2):
                lists.cell(row=n, column=list_col, value=option)
            dv = DataValidation(
                type="list",
                formula1=f"'{LISTS_SHEET}'!${lletter}$2:${lletter}${len(options) + 1}",
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Значение не из списка",
                error="Выберите значение из выпадающего списка",
            )
            dv.add(area)
            ws.add_data_validation(dv)
            if col.get("type") == "list":
                ws.column_dimensions[letter].width = min(
                    60, max(ws.column_dimensions[letter].width, *(len(o) + 2 for o in options))
                )
        if col.get("type") == "date":
            dv = DataValidation(
                type="date",
                operator="greaterThan",
                formula1="1",
                allow_blank=True,
                showErrorMessage=True,
                errorTitle="Не дата",
                error="Введите дату в формате ДД.ММ.ГГГГ",
            )
            dv.add(area)
            ws.add_data_validation(dv)
            for row in range(2, TEMPLATE_ROWS + 2):
                ws.cell(row=row, column=i).number_format = "DD.MM.YYYY"
    ws.freeze_panes = "A2"

    help_ws = wb.create_sheet(HELP_SHEET)
    help_ws.column_dimensions["A"].width = 110
    help_ws.cell(row=1, column=1, value=f"Импорт: {template['title']}").font = Font(
        bold=True, size=13
    )
    lines = [
        *template.get("instructions", []),
        "Заполняйте лист «Данные», начиная со второй строки; первую строку не меняйте.",
        "Столбцы со звёздочкой обязательны. Значения со стрелкой выбираются из списка.",
        "Даты — в формате ДД.ММ.ГГГГ. Можно сохранить файл как CSV (UTF-8 или Windows-1251).",
        "После загрузки система покажет, что будет сделано по каждой строке, и ничего не "
        "изменит, пока вы не нажмёте «Применить».",
    ]
    for n, line in enumerate(lines, start=3):
        c = help_ws.cell(row=n, column=1, value=f"• {line}")
        c.alignment = Alignment(wrap_text=True, vertical="top")
    help_ws.cell(row=len(lines) + 4, column=1, value="Столбцы").font = Font(bold=True)
    for n, col in enumerate(template["columns"], start=len(lines) + 5):
        text = header(col) + (f" — {col['hint']}" if col.get("hint") else "")
        help_ws.cell(row=n, column=1, value=text).alignment = Alignment(wrap_text=True)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- разбор -----------------------------------------------------------------------------------


@dataclass
class Parsed:
    rows: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)


def _cell(value: Any) -> Any:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _table(matrix: list[list[Any]], columns: list[dict[str, Any]]) -> Parsed:
    """Первая непустая строка — заголовок; дальше — данные."""
    start = next((i for i, r in enumerate(matrix) if any(_cell(v) is not None for v in r)), None)
    if start is None:
        raise ValidationFailedError("Файл пустой")
    by_title = {_norm(c["title"]): c for c in columns}
    mapping: dict[int, str] = {}
    notes: list[str] = []
    for i, title in enumerate(matrix[start]):
        if _cell(title) is None:
            continue
        col = by_title.get(_norm(title))
        if col is None:
            notes.append(f"Столбец «{title}» не из шаблона — пропущен")
        elif col["key"] in mapping.values():
            notes.append(f"Столбец «{title}» повторяется — взят первый")
        else:
            mapping[i] = col["key"]
    if not mapping:
        raise ValidationFailedError(
            "Не найдено ни одного столбца шаблона. Скачайте шаблон и заполните его."
        )
    missing = [header(c) for c in columns if c.get("required") and c["key"] not in mapping.values()]
    if missing:
        raise ValidationFailedError(f"В файле нет обязательных столбцов: {', '.join(missing)}")
    rows = []
    for offset, raw in enumerate(matrix[start + 1 :], start=start + 2):
        values = {key: _cell(raw[i]) if i < len(raw) else None for i, key in mapping.items()}
        if all(v is None for v in values.values()):
            continue
        rows.append({"row": offset, "values": {k: v for k, v in values.items() if v is not None}})
        if len(rows) > MAX_ROWS:
            raise ValidationFailedError(f"В файле больше {MAX_ROWS} строк — разделите его")
    if not rows:
        raise ValidationFailedError("В файле нет строк с данными")
    return Parsed(rows, notes)


def parse(filename: str, content: bytes, columns: list[dict[str, Any]]) -> Parsed:
    name = filename.lower()
    if name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # битый архив, не xlsx, защищённый файл
            raise ValidationFailedError("Не удалось прочитать xlsx-файл") from exc
        ws = wb[DATA_SHEET] if DATA_SHEET in wb.sheetnames else wb.worksheets[0]
        matrix = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
        return _table(matrix, columns)
    if name.endswith(".csv"):
        return _table(_csv(content), columns)
    raise ValidationFailedError("Поддерживаются файлы .xlsx и .csv")


def _csv(content: bytes) -> list[list[Any]]:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover — cp1251 декодирует любые байты
        raise ValidationFailedError("Не удалось определить кодировку CSV")
    first = text.splitlines()[0] if text else ""
    delimiter = max((";", ",", "\t"), key=first.count)
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=delimiter)]


# --- отчёт ------------------------------------------------------------------------------------


def build_report(
    columns: list[dict[str, Any]], rows: list[dict[str, Any]], report: list[dict[str, Any]]
) -> bytes:
    """Строки файла как в шаблоне плюс «Результат» и «Ошибки и предупреждения»; ячейки
    с ошибкой подсвечены. Исправленный отчёт можно загрузить снова — лишние столбцы
    при разборе пропускаются."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = DATA_SHEET
    keys = [c["key"] for c in columns]
    titles = [header(c) for c in columns] + ["Результат", "Ошибки и предупреждения"]
    for i, title in enumerate(titles, start=1):
        cell = ws.cell(row=1, column=i, value=title)
        cell.fill = HEADER_FILL
        cell.font = Font(bold=True)
        ws.column_dimensions[get_column_letter(i)].width = 18
    ws.column_dimensions[get_column_letter(len(titles))].width = 70
    by_row = {r["row"]: r for r in report}
    for n, row in enumerate(rows, start=2):
        result = by_row.get(row["row"], {})
        for i, key in enumerate(keys, start=1):
            ws.cell(row=n, column=i, value=row["values"].get(key))
        action = result.get("action", "error")
        status = ws.cell(row=n, column=len(keys) + 1, value=ACTION_LABELS.get(action, action))
        status.fill = {"error": ERROR_FILL, "create": OK_FILL, "update": OK_FILL}.get(
            action, PatternFill()
        )
        messages = [f"Ошибка: {e['message']}" for e in result.get("errors", [])]
        messages += [f"Внимание: {w['message']}" for w in result.get("warnings", [])]
        messages += [
            f"{field}: {old if old is not None else '—'} → {new if new is not None else '—'}"
            for field, (old, new) in result.get("changes", {}).items()
        ]
        ws.cell(row=n, column=len(keys) + 2, value="\n".join(messages)).alignment = Alignment(
            wrap_text=True, vertical="top"
        )
        for e in result.get("errors", []):
            if e.get("column") in keys:
                ws.cell(row=n, column=keys.index(e["column"]) + 1).fill = ERROR_FILL
        for w in result.get("warnings", []):
            if w.get("column") in keys:
                c = ws.cell(row=n, column=keys.index(w["column"]) + 1)
                if c.fill != ERROR_FILL:
                    c.fill = WARNING_FILL
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(titles))}{len(rows) + 1}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
