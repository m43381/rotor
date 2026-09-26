"""Создаёт deploy/.env из deploy/.env.example, заменяя CHANGE_ME случайными секретами.

Существующий deploy/.env не перезаписывается — секреты стенда не должны меняться сами.
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
    if TARGET.exists():
        print(f"{TARGET.relative_to(ROOT)} уже есть — оставляю как есть")
        return 0
    lines = []
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        if line.rstrip().endswith("=CHANGE_ME"):
            line = line.replace("CHANGE_ME", secrets.token_urlsafe(24))
        lines.append(line)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Создан {TARGET.relative_to(ROOT)}. Пароль admin: см. DUTYFLOW_ADMIN_PASSWORD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
