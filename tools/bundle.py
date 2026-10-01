"""Пакет поставки для изолированной сети (фаза 7c, ADR-0017).

    uv run python tools/bundle.py --version 1.0.0 [--no-build] [--out dist]

Результат — каталог `dist/dutyflow-<версия>/` и архив `dist/dutyflow-<версия>.tar` рядом:

    images.tar.gz        образы DutyFlow с тегом версии и сторонние (PostgreSQL, Redis, Keycloak)
    docker-compose.yml   без секций build, pull_policy: never — стенд не обращается в реестры
    .env.example         шаблон настроек с DUTYFLOW_VERSION
    dutyflow.sh          init / install / update / backup / restore / doctor
    nginx/ keycloak/ postgres/   конфигурация, как в deploy/
    demo/                        демонстрационные данные (`./dutyflow.sh demo`)
    README.md            руководство администратора (deploy/README.md)
    VERSION, MANIFEST.sha256

На сервере нужен только Docker с плагином compose: `./dutyflow.sh install`.
"""

import argparse
import gzip
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
COMPOSE = DEPLOY / "docker-compose.yml"
# Каталоги и файлы deploy/, которые едут в пакет как есть
PAYLOAD = ("nginx", "keycloak", "postgres", "demo", "dutyflow.sh", "README.md")
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$")


def run(*args: str, env_version: str | None = None, capture: bool = False) -> str:
    env = dict(os.environ)
    if env_version:
        env["DUTYFLOW_VERSION"] = env_version
    # Команда — только docker с фиксированными ключами; версия проверена VERSION_RE
    result = subprocess.run(  # noqa: S603
        args, check=True, env=env, text=True, capture_output=capture, encoding="utf-8"
    )
    return result.stdout if capture else ""


def compose(*args: str, version: str, capture: bool = False) -> str:
    # Шаблон .env.example: для сборки и списка образов секреты не нужны
    return run(
        "docker",
        "compose",
        "-f",
        str(COMPOSE),
        "--env-file",
        str(DEPLOY / ".env.example"),
        "--profile",
        "ops",
        *args,
        env_version=version,
        capture=capture,
    )


def delivery_compose(text: str) -> str:
    """Compose для пакета: без `build`, образы только локальные."""
    out: list[str] = []
    skipping = False
    for line in text.split("\n"):
        if skipping:
            if line.startswith("      ") or not line.strip():
                continue
            skipping = False
        if line == "    build:":
            skipping = True
            continue
        out.append(line)
        if re.fullmatch(r"    image: \S+", line):
            out.append("    pull_policy: never")
    result = "\n".join(out)
    header = (
        "# Пакет поставки DutyFlow: образы загружаются из images.tar.gz\n"
        "# (`./dutyflow.sh install`), из реестров ничего не скачивается (pull_policy: never).\n"
    )
    return header + result


def save_images(images: list[str], target: Path) -> None:
    print(f"Сохранение {len(images)} образов…")
    with (
        subprocess.Popen(["docker", "save", *images], stdout=subprocess.PIPE) as proc,  # noqa: S603, S607
        gzip.open(target, "wb", compresslevel=3) as gz,
    ):
        assert proc.stdout is not None
        shutil.copyfileobj(proc.stdout, gz, length=4 * 1024 * 1024)
    if proc.returncode:
        raise SystemExit(f"docker save завершился с кодом {proc.returncode}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--version", required=True, help="номер выпуска, например 1.0.0")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--no-build", action="store_true", help="образы с этим тегом уже есть")
    args = parser.parse_args()
    version: str = args.version
    if not VERSION_RE.match(version) or version == "dev":
        parser.error("версия: буквы, цифры, точки, дефисы; не «dev»")

    target = args.out / f"dutyflow-{version}"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    if not args.no_build:
        print(f"Сборка образов {version}…")
        compose("build", version=version)
    images = sorted(set(compose("config", "--images", version=version, capture=True).split()))
    save_images(images, target / "images.tar.gz")

    (target / "docker-compose.yml").write_text(
        delivery_compose(COMPOSE.read_text(encoding="utf-8")), encoding="utf-8", newline="\n"
    )
    env = (DEPLOY / ".env.example").read_text(encoding="utf-8").rstrip("\n")
    env += (
        "\n\n# Версия установленного пакета (обновляет ./dutyflow.sh update)\n"
        f"DUTYFLOW_VERSION={version}\n"
    )
    (target / ".env.example").write_text(env, encoding="utf-8", newline="\n")
    for name in PAYLOAD:
        src = DEPLOY / name
        if src.is_dir():
            shutil.copytree(src, target / name)
        else:
            shutil.copy2(src, target / name)
    (target / "VERSION").write_text(version + "\n", encoding="utf-8", newline="\n")

    files = sorted(p for p in target.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256")
    manifest = "".join(f"{sha256(p)}  ./{p.relative_to(target).as_posix()}\n" for p in files)
    (target / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")

    archive = args.out / f"dutyflow-{version}.tar"
    with tarfile.open(archive, "w") as tar:
        for path in sorted(target.rglob("*")):
            info = tar.gettarinfo(str(path), arcname=path.relative_to(args.out).as_posix())
            # Права: скрипты исполняемые независимо от ОС, на которой собирался пакет
            if path.is_file():
                info.mode = 0o755 if path.suffix == ".sh" else 0o644
            else:
                info.mode = 0o755
            if path.is_file():
                with path.open("rb") as f:
                    tar.addfile(info, f)
            else:
                tar.addfile(info)
    size = archive.stat().st_size / 1024**3
    print(f"Пакет: {archive} ({size:.2f} ГБ), образов: {len(images)}")
    for image in images:
        print(f"  {image}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
