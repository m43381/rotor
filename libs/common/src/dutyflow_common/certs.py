"""Сертификаты HTTPS на внутреннем УЦ (фаза 7c, open-questions №60).

    python -m dutyflow_common.certs generate --out deploy/certs --host localhost --host 10.0.0.5
    python -m dutyflow_common.certs check --cert deploy/certs/server.crt --warn-days 30

- Корневой сертификат организации (`ca.crt`, 10 лет) создаётся один раз и при продлении
  сохраняется — клиентским местам не нужно устанавливать его заново.
- Сертификат сервера (`server.crt`, 2 года) выпускается на все указанные имена и IP (SAN).
- Ключи (`ca.key`, `server.key`) — с правами только владельца; `ca.key` в пакет поставки и
  в репозиторий не попадает.
- Сертификаты заказчика можно положить в тот же каталог вместо сгенерированных.

Модуль есть в образе любого сервиса, поэтому на целевой машине Python не нужен:
`docker run --rm -v $PWD/certs:/certs dutyflow/org:<версия> python -m dutyflow_common.certs …`.
"""

import argparse
import datetime as dt
import ipaddress
import os
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CA_DAYS = 3650
SERVER_DAYS = 730
ORG = "DutyFlow"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    os.chmod(path, 0o600)


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _ca(out: Path) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    crt, key_path = out / "ca.crt", out / "ca.key"
    if crt.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(crt.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        assert isinstance(key, rsa.RSAPrivateKey)
        return cert, key
    key = _key()
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{ORG} Root CA"),
        ]
    )
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(key_path, key)
    _write_cert(crt, cert)
    return cert, key


def generate(out: Path, hosts: list[str], days: int = SERVER_DAYS) -> Path:
    """Выпускает сертификат сервера на `hosts`; корневой — создаёт или переиспользует."""
    if not hosts:
        raise ValueError("Укажите хотя бы одно имя хоста или IP")
    out.mkdir(parents=True, exist_ok=True)
    ca_cert, ca_key = _ca(out)
    key = _key()
    names: list[x509.GeneralName] = []
    for host in hosts:
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG),
                    x509.NameAttribute(NameOID.COMMON_NAME, hosts[0]),
                ]
            )
        )
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write_key(out / "server.key", key)
    _write_cert(out / "server.crt", cert)
    return out / "server.crt"


def days_left(cert_path: Path) -> int:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return (cert.not_valid_after_utc - dt.datetime.now(dt.UTC)).days


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m dutyflow_common.certs")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="выпустить сертификат сервера (и корневой, если нет)")
    gen.add_argument("--out", type=Path, required=True)
    gen.add_argument("--host", action="append", default=[], help="имя или IP, можно несколько")
    gen.add_argument("--days", type=int, default=SERVER_DAYS)
    chk = sub.add_parser("check", help="сколько дней действует сертификат")
    chk.add_argument("--cert", type=Path, required=True)
    chk.add_argument("--warn-days", type=int, default=30)
    args = parser.parse_args(argv)
    if args.command == "generate":
        path = generate(args.out, args.host, args.days)
        print(f"Сертификат сервера: {path} (имена: {', '.join(args.host)})")
        print(f"Корневой сертификат для клиентских мест: {args.out / 'ca.crt'}")
        return 0
    left = days_left(args.cert)
    print(f"Сертификат {args.cert.name} действует ещё {left} дн.")
    return 0 if left >= args.warn_days else 1


if __name__ == "__main__":
    sys.exit(main())
