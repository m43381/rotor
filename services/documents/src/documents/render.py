"""Отрисовка печатных форм: HTML-шаблон → PDF (WeasyPrint), XLSX (openpyxl), DOCX
(python-docx) — из одного контекста `documents.forms`.

HTML-шаблоны выполняются в песочнице Jinja2 (`SandboxedEnvironment`): загруженный
суперадминистратором шаблон не может вызывать методы объектов вне безопасного набора,
обращаться к «служебным» атрибутам и читать файлы — у окружения нет загрузчика.
WeasyPrint подключается лениво: ему нужны системные библиотеки (pango), которые есть
в образе сервиса, но не обязательно на машине разработчика.
"""

import io
from functools import cache
from importlib import resources
from typing import Any

from jinja2 import TemplateError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from dutyflow_common.errors import ValidationFailedError
from dutyflow_common.internal import ServiceUnavailableError

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MEDIA = {"pdf": PDF, "xlsx": XLSX, "docx": DOCX}
MAX_TEMPLATE = 200_000


@cache
def _env() -> SandboxedEnvironment:
    return SandboxedEnvironment(autoescape=True, trim_blocks=True, lstrip_blocks=True)


def builtin_template(form: str) -> str:
    return (resources.files("documents") / "templates" / f"{form}.html").read_text(encoding="utf-8")


def render_html(body: str, context: dict[str, Any]) -> str:
    if len(body) > MAX_TEMPLATE:
        raise ValidationFailedError("Шаблон слишком большой")
    try:
        return _env().from_string(body).render(**context)
    except SecurityError as exc:
        raise ValidationFailedError(f"Шаблон обращается к недоступным данным: {exc}") from exc
    except TemplateError as exc:
        line = getattr(exc, "lineno", None)
        where = f" (строка {line})" if line else ""
        raise ValidationFailedError(f"Ошибка в шаблоне{where}: {exc.message or exc}") from exc


def html_to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except OSError as exc:  # нет системных библиотек (pango) — только вне образа сервиса
        raise ServiceUnavailableError("Печать в PDF недоступна на этом сервере") from exc
    # Внешних ресурсов нет: базовый URL пустой, картинки и шрифты — только встроенные
    pdf: bytes = HTML(string=html, base_url=None).write_pdf()
    return pdf


# --- XLSX: график на месяц -------------------------------------------------------------------

THIN = Side(style="thin", color="000000")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
OFF = PatternFill("solid", fgColor="EEEEEE")


def schedule_xlsx(ctx: dict[str, Any]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "График"
    columns = [c for page in ctx["pages"] for c in page["columns"]]
    width = len(columns) + 1
    req = ctx["requisites"]
    row = 1
    if ctx["draft"]:
        ws.cell(row=row, column=1, value="ПРОЕКТ").font = Font(bold=True, size=14)
    else:
        right = max(1, width - 2)
        for line in (
            "УТВЕРЖДАЮ",
            req["approver_position"],
            f"{req['approver_rank']} ____________ {req['approver_name']}".strip(),
            f"«____» ______________ {ctx['month'].year} г.",
        ):
            ws.cell(row=row, column=right, value=line)
            row += 1
    row += 1
    ws.cell(row=row, column=1, value=ctx["title"]).font = Font(bold=True, size=13)
    row += 1
    ws.cell(row=row, column=1, value=f"{ctx['unit']['name']} на {ctx['month_name']}")
    row += 2
    header = row
    ws.cell(row=header, column=1, value="Дата")
    ws.merge_cells(start_row=header, start_column=1, end_row=header + 1, end_column=1)
    col = 2
    for page in ctx["pages"]:
        for g in page["groups"]:
            ws.cell(row=header, column=col, value=f"{g['duty_type']} ({g['start']})")
            if g["span"] > 1:
                ws.merge_cells(
                    start_row=header,
                    start_column=col,
                    end_row=header,
                    end_column=col + g["span"] - 1,
                )
            col += g["span"]
    for i, c in enumerate(columns, start=2):
        suffix = f" ×{c['headcount']}" if c["headcount"] > 1 else ""
        ws.cell(row=header + 1, column=i, value=f"{c['role']}{suffix}")
    for r in (header, header + 1):
        for c in range(1, width + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = BORDER
    days = ctx["pages"][0]["rows"] if ctx["pages"] else []
    for i, day in enumerate(days):
        r = header + 2 + i
        off = day["kind"] in ("weekend", "holiday")
        cells = [c for page in ctx["pages"] for c in page["rows"][i]["cells"]]
        ws.cell(row=r, column=1, value=f"{day['day']} {day['weekday']}")
        for j, cell in enumerate(cells, start=2):
            text = ""
            if cell is not None:
                if cell["executor"]:
                    text = cell["executor"]
                else:
                    lines = list(cell["lines"])
                    if cell["missing"]:
                        lines.append(f"не назначено: {cell['missing']}")
                    text = "\n".join(lines)
            ws.cell(row=r, column=j, value=text)
        for c in range(1, width + 1):
            target = ws.cell(row=r, column=c)
            target.border = BORDER
            target.alignment = Alignment(vertical="top", wrap_text=True)
            if off:
                target.fill = OFF
                if c == 1:
                    target.font = Font(bold=True)
    last = header + 2 + len(days) + 1
    ws.cell(
        row=last,
        column=1,
        value=(
            f"Составил: {req['compiler_position']} {req['compiler_rank']} ____________ "
            f"{req['compiler_name']}"
        ),
    )
    ws.column_dimensions["A"].width = 9
    for c in range(2, width + 1):
        ws.column_dimensions[get_column_letter(c)].width = 22
    ws.freeze_panes = ws.cell(row=header + 2, column=2)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header}:{header + 1}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --- DOCX: суточный наряд ---------------------------------------------------------------------


def daily_docx(ctx: dict[str, Any], form: str) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Mm, Pt

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin, section.right_margin = Mm(25), Mm(15)
    section.top_margin = section.bottom_margin = Mm(20)
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(13 if form == "daily_order" else 12)
    req = ctx["requisites"]

    def para(text: str, *, bold: bool = False, center: bool = False, right: bool = False) -> None:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif right:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    if ctx["draft"]:
        para("ПРОЕКТ", bold=True)
    if form == "daily_order":
        para("ПРИКАЗ", bold=True, center=True)
        para(ctx["unit"]["name"], center=True)
        para(f"«____» ______________ {ctx['date'].year} г.            № ________")
        para(f"О назначении суточного наряда на {ctx['date_text']}", bold=True, center=True)
        para("В целях поддержания внутреннего порядка и несения службы суточным нарядом")
        para("ПРИКАЗЫВАЮ:", bold=True)
        para(f"1. Назначить в суточный наряд на {ctx['date_text']} ({ctx['weekday']}):")
        for n, duty in enumerate(ctx["duties"], start=1):
            parts = []
            for role in duty["roles"]:
                people = ", ".join(
                    f"{(p['rank'] or '').lower()} {p['full_name']}".strip()
                    + (f" ({p['unit']})" if p["unit"] else "")
                    for p in role["people"]
                )
                if role["missing"]:
                    people += (", " if people else "") + f"не назначено: {role['missing']}"
                parts.append(f"{role['name'].lower()} — {people}")
            para(
                f"1.{n}. {duty['name']} (с {duty['start']} до {duty['end']}): "
                + "; ".join(parts)
                + "."
            )
        para("2. Контроль за выполнением приказа оставляю за собой.")
        para("")
        para(
            f"{req['approver_position']}\n{req['approver_rank']}      ____________      "
            f"{req['approver_name']}"
        )
    else:
        if not ctx["draft"]:
            para(
                "УТВЕРЖДАЮ\n"
                f"{req['approver_position']}\n"
                f"{req['approver_rank']} ____________ {req['approver_name']}\n"
                f"«____» ______________ {ctx['date'].year} г.",
                right=True,
            )
        para("Ведомость суточного наряда", bold=True, center=True)
        day = f"{ctx['weekday']}, {ctx['day_name']}" if ctx["day_name"] else ctx["weekday"]
        para(f"{ctx['unit']['name']} на {ctx['date_text']} ({day})", center=True)
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        for cell, title in zip(
            table.rows[0].cells,
            ("№", "Наряд, роль", "Воинское звание", "Фамилия, имя, отчество", "Подразделение"),
            strict=True,
        ):
            cell.text = title
            cell.paragraphs[0].runs[0].bold = True
        n = 0
        for duty in ctx["duties"]:
            row = table.add_row().cells
            merged = row[0].merge(row[4])
            merged.text = f"{duty['name']} — с {duty['start']} до {duty['end']}"
            if duty["executor"]:
                merged.text += f" ({duty['executor']})"
            merged.paragraphs[0].runs[0].bold = True
            for role in duty["roles"]:
                for p in role["people"]:
                    n += 1
                    cells = table.add_row().cells
                    values = (
                        str(n),
                        role["name"],
                        p["rank"] or "",
                        p["full_name"],
                        p["unit"] or "",
                    )
                    for cell, value in zip(cells, values, strict=True):
                        cell.text = value
                for _ in range(role["missing"]):
                    cells = table.add_row().cells
                    cells[1].text = role["name"]
                    cells[2].merge(cells[4]).text = "не назначен"
        if not ctx["duties"]:
            cells = table.add_row().cells
            cells[0].merge(cells[4]).text = "Нарядов на эту дату нет"
        para("")
        para(
            f"Составил: {req['compiler_position']} {req['compiler_rank']} ____________ "
            f"{req['compiler_name']}"
        )
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
