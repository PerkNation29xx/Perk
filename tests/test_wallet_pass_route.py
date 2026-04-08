import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_wallet_pass_route_returns_clear_error_when_unconfigured() -> None:
    originals = {
        "wallet_pass_service_url": settings.wallet_pass_service_url,
        "wallet_pass_type_identifier": settings.wallet_pass_type_identifier,
        "wallet_team_identifier": settings.wallet_team_identifier,
        "wallet_signer_certificate_path": settings.wallet_signer_certificate_path,
        "wallet_signer_key_path": settings.wallet_signer_key_path,
        "wallet_wwdr_certificate_path": settings.wallet_wwdr_certificate_path,
        "wallet_signer_certificate_pem": settings.wallet_signer_certificate_pem,
        "wallet_signer_key_pem": settings.wallet_signer_key_pem,
        "wallet_wwdr_certificate_pem": settings.wallet_wwdr_certificate_pem,
    }
    settings.wallet_pass_service_url = None
    settings.wallet_pass_type_identifier = None
    settings.wallet_team_identifier = None
    settings.wallet_signer_certificate_path = None
    settings.wallet_signer_key_path = None
    settings.wallet_wwdr_certificate_path = None
    settings.wallet_signer_certificate_pem = None
    settings.wallet_signer_key_pem = None
    settings.wallet_wwdr_certificate_pem = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/wallet/pass",
                params={
                    "title": "PerkNation offer",
                    "code": "PKN-123",
                    "payload": "https://perknation.app/redeem?code=PKN-123",
                },
            )
        assert response.status_code == 503
        assert "Apple Wallet passes are not enabled" in response.json()["detail"]
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)


def test_wallet_pass_route_redirects_to_configured_service() -> None:
    originals = {
        "wallet_pass_service_url": settings.wallet_pass_service_url,
        "wallet_pass_type_identifier": settings.wallet_pass_type_identifier,
        "wallet_team_identifier": settings.wallet_team_identifier,
        "wallet_signer_certificate_path": settings.wallet_signer_certificate_path,
        "wallet_signer_key_path": settings.wallet_signer_key_path,
        "wallet_wwdr_certificate_path": settings.wallet_wwdr_certificate_path,
        "wallet_signer_certificate_pem": settings.wallet_signer_certificate_pem,
        "wallet_signer_key_pem": settings.wallet_signer_key_pem,
        "wallet_wwdr_certificate_pem": settings.wallet_wwdr_certificate_pem,
    }
    settings.wallet_pass_service_url = "https://wallet.perknation.net/pass?channel=ios"
    settings.wallet_pass_type_identifier = None
    settings.wallet_team_identifier = None
    settings.wallet_signer_certificate_path = None
    settings.wallet_signer_key_path = None
    settings.wallet_wwdr_certificate_path = None
    settings.wallet_signer_certificate_pem = None
    settings.wallet_signer_key_pem = None
    settings.wallet_wwdr_certificate_pem = None
    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/wallet/pass",
                params={
                    "title": "PerkNation referral",
                    "code": "PKN-REF",
                    "payload": "https://perknation.app/invite?code=PKN-REF",
                },
                follow_redirects=False,
            )
        assert response.status_code == 307
        location = response.headers["location"]
        assert location.startswith("https://wallet.perknation.net/pass?")
        assert "channel=ios" in location
        assert "title=PerkNation+referral" in location
        assert "code=PKN-REF" in location
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)


def test_wallet_pass_route_generates_pkpass_when_local_signing_is_configured(tmp_path: Path) -> None:
    signer_key = tmp_path / "signer.key.pem"
    signer_cert = tmp_path / "signer.pem"
    wwdr_cert = tmp_path / "wwdr.pem"

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(signer_key),
            "-out",
            str(signer_cert),
            "-days",
            "2",
            "-nodes",
            "-subj",
            "/CN=PerkNation Test Pass",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wwdr_cert.write_bytes(signer_cert.read_bytes())

    originals = {
        "wallet_pass_service_url": settings.wallet_pass_service_url,
        "wallet_pass_type_identifier": settings.wallet_pass_type_identifier,
        "wallet_team_identifier": settings.wallet_team_identifier,
        "wallet_signer_certificate_path": settings.wallet_signer_certificate_path,
        "wallet_signer_key_path": settings.wallet_signer_key_path,
        "wallet_wwdr_certificate_path": settings.wallet_wwdr_certificate_path,
        "wallet_signer_certificate_pem": settings.wallet_signer_certificate_pem,
        "wallet_signer_key_pem": settings.wallet_signer_key_pem,
        "wallet_wwdr_certificate_pem": settings.wallet_wwdr_certificate_pem,
    }
    settings.wallet_pass_service_url = None
    settings.wallet_pass_type_identifier = "pass.com.neonflux.perknation"
    settings.wallet_team_identifier = "PL9PGQKXUW"
    settings.wallet_signer_certificate_path = str(signer_cert)
    settings.wallet_signer_key_path = str(signer_key)
    settings.wallet_wwdr_certificate_path = str(wwdr_cert)
    settings.wallet_signer_certificate_pem = None
    settings.wallet_signer_key_pem = None
    settings.wallet_wwdr_certificate_pem = None

    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/wallet/pass",
                params={
                    "title": "PerkNation offer",
                    "code": "PKN-LOCAL",
                    "payload": "https://perknation.app/redeem?code=PKN-LOCAL",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.apple.pkpass")
        assert response.content[:2] == b"PK"
        with ZipFile(BytesIO(response.content)) as archive:
            names = set(archive.namelist())
            assert names == {
                "pass.json",
                "manifest.json",
                "signature",
                "icon.png",
                "icon@2x.png",
                "logo.png",
                "logo@2x.png",
            }
            pass_json = json.loads(archive.read("pass.json").decode("utf-8"))
            assert pass_json.get("sharingProhibited") is True
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            assert set(manifest) == {
                "pass.json",
                "icon.png",
                "icon@2x.png",
                "logo.png",
                "logo@2x.png",
            }
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)


def test_wallet_pass_route_generates_pkpass_when_pem_values_are_configured(tmp_path: Path) -> None:
    signer_key = tmp_path / "signer.key.pem"
    signer_cert = tmp_path / "signer.pem"
    wwdr_cert = tmp_path / "wwdr.pem"

    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(signer_key),
            "-out",
            str(signer_cert),
            "-days",
            "2",
            "-nodes",
            "-subj",
            "/CN=PerkNation Test Pass",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wwdr_cert.write_bytes(signer_cert.read_bytes())

    originals = {
        "wallet_pass_service_url": settings.wallet_pass_service_url,
        "wallet_pass_type_identifier": settings.wallet_pass_type_identifier,
        "wallet_team_identifier": settings.wallet_team_identifier,
        "wallet_signer_certificate_path": settings.wallet_signer_certificate_path,
        "wallet_signer_key_path": settings.wallet_signer_key_path,
        "wallet_wwdr_certificate_path": settings.wallet_wwdr_certificate_path,
        "wallet_signer_certificate_pem": settings.wallet_signer_certificate_pem,
        "wallet_signer_key_pem": settings.wallet_signer_key_pem,
        "wallet_wwdr_certificate_pem": settings.wallet_wwdr_certificate_pem,
    }
    settings.wallet_pass_service_url = None
    settings.wallet_pass_type_identifier = "pass.com.neonflux.perknation"
    settings.wallet_team_identifier = "PL9PGQKXUW"
    settings.wallet_signer_certificate_path = None
    settings.wallet_signer_key_path = None
    settings.wallet_wwdr_certificate_path = None
    settings.wallet_signer_certificate_pem = signer_cert.read_text(encoding="utf-8")
    settings.wallet_signer_key_pem = signer_key.read_text(encoding="utf-8")
    settings.wallet_wwdr_certificate_pem = wwdr_cert.read_text(encoding="utf-8")

    try:
        with TestClient(app) as client:
            response = client.get(
                "/v1/wallet/pass",
                params={
                    "title": "PerkNation offer",
                    "code": "PKN-PEM",
                    "payload": "https://perknation.app/redeem?code=PKN-PEM",
                },
            )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/vnd.apple.pkpass")
        assert response.content[:2] == b"PK"
        with ZipFile(BytesIO(response.content)) as archive:
            pass_json = json.loads(archive.read("pass.json").decode("utf-8"))
            assert pass_json.get("sharingProhibited") is True
    finally:
        for key, value in originals.items():
            setattr(settings, key, value)
