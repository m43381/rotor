"""Эксплуатация (фаза 7c): сертификаты внутреннего УЦ, проверки doctor, признак жизни."""

import ipaddress
from pathlib import Path

import pytest
from cryptography import x509

from dutyflow_common.certs import days_left, generate, main


def test_generate_and_renew(tmp_path: Path) -> None:
    generate(tmp_path, ["dutyflow.local", "10.0.0.5"])
    ca = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    server = x509.load_pem_x509_certificate((tmp_path / "server.crt").read_bytes())
    assert server.issuer == ca.subject
    san = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert san.get_values_for_type(x509.DNSName) == ["dutyflow.local"]
    assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("10.0.0.5")]
    assert 700 < days_left(tmp_path / "server.crt") <= 730

    # Продление: новый сертификат сервера, корневой — тот же
    generate(tmp_path, ["dutyflow.local"])
    again = x509.load_pem_x509_certificate((tmp_path / "ca.crt").read_bytes())
    assert again.serial_number == ca.serial_number
    renewed = x509.load_pem_x509_certificate((tmp_path / "server.crt").read_bytes())
    assert renewed.serial_number != server.serial_number


def test_cli_check(tmp_path: Path) -> None:
    assert main(["generate", "--out", str(tmp_path), "--host", "localhost", "--days", "10"]) == 0
    assert main(["check", "--cert", str(tmp_path / "server.crt"), "--warn-days", "5"]) == 0
    assert main(["check", "--cert", str(tmp_path / "server.crt"), "--warn-days", "30"]) == 1


def test_doctor_cert_check(tmp_path: Path) -> None:
    from dutyflow_common.doctor import Report, check_cert

    report = Report()
    check_cert(report, tmp_path / "server.crt")
    assert report.problems  # сертификата нет

    generate(tmp_path, ["localhost"], days=10)
    report = Report()
    check_cert(report, tmp_path / "server.crt")
    assert not report.problems
    assert report.warnings  # скоро истекает

    generate(tmp_path, ["localhost"])
    report = Report()
    check_cert(report, tmp_path / "server.crt")
    assert not report.problems
    assert not report.warnings


def test_heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    from dutyflow_common import heartbeat

    monkeypatch.setenv("HEARTBEAT_FILE", str(tmp_path / "hb"))
    assert heartbeat.main(["60"]) == 1  # процесс ещё не отметился
    heartbeat.beat()
    assert heartbeat.main(["60"]) == 0
    os.utime(tmp_path / "hb", (0, 0))
    assert heartbeat.main(["60"]) == 1  # отметка устарела
