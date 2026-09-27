"""Выгружает OpenAPI-схемы сервисов без запуска серверов — для генерации клиента фронтенда."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "src" / "api" / "generated"


def main() -> int:
    from org.main import create_app as org_app
    from personnel.main import create_app as personnel_app
    from scheduling.main import create_app as scheduling_app

    OUT.mkdir(parents=True, exist_ok=True)
    for name, factory in (
        ("org", org_app),
        ("personnel", personnel_app),
        ("scheduling", scheduling_app),
    ):
        schema = factory().openapi()
        text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
        (OUT / f"{name}.openapi.json").write_text(text, encoding="utf-8", newline="\n")
        print(f"OpenAPI: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
