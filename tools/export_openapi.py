"""Выгружает OpenAPI-схемы сервисов без запуска серверов — для генерации клиента фронтенда."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "api" / "generated"


def main() -> int:
    from org.main import create_app

    OUT.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    (OUT / "org.openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print("OpenAPI: org")
    return 0


if __name__ == "__main__":
    sys.exit(main())
