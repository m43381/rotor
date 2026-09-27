"""Создаёт deploy/.env из deploy/.env.example, заменяя CHANGE_ME случайными секретами.

Существующий deploy/.env не перезаписывается — секреты стенда не должны меняться сами.
Если в шаблоне появились новые переменные (например, пароль БД нового сервиса), они
дописываются в конец существующего файла.
"""

import io
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy" / ".env.example"
TARGET = ROOT / "deploy" / ".env"


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию в cp1251
    template = [_fill(line) for line in TEMPLATE.read_text(encoding="utf-8").splitlines()]
    name = TARGET.relative_to(ROOT)
    if TARGET.exists():
        existing = TARGET.read_text(encoding="utf-8")
        present = {_key(line) for line in existing.splitlines()}
        missing = [line for line in template if _key(line) and _key(line) not in present]
        if not missing:
            print(f"{name} уже есть — оставляю как есть")
            return 0
        with TARGET.open("a", encoding="utf-8", newline="\n") as f:
            f.write(("" if existing.endswith("\n") else "\n") + "\n".join(missing) + "\n")
        print(f"{name}: добавлены новые переменные {', '.join(str(_key(m)) for m in missing)}")
        return 0
    TARGET.write_text("\n".join(template) + "\n", encoding="utf-8", newline="\n")
    print(f"Создан {name}. Пароль admin: см. DUTYFLOW_ADMIN_PASSWORD")
    return 0


def _fill(line: str) -> str:
    if line.rstrip().endswith("=CHANGE_ME"):
        return line.replace("CHANGE_ME", secrets.token_urlsafe(24))
    return line


def _key(line: str) -> str | None:
    """Имя переменной в строке `KEY=value`; для комментариев и пустых строк — None."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0]


if __name__ == "__main__":
    sys.exit(main())
