from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile

from app.core.config import settings


class WalletPassConfigurationError(RuntimeError):
    pass


class WalletPassSigningError(RuntimeError):
    pass


class WalletPassService:
    ARCHIVE_FILENAMES = (
        "pass.json",
        "manifest.json",
        "signature",
        "icon.png",
        "icon@2x.png",
        "logo.png",
        "logo@2x.png",
    )

    def __init__(self) -> None:
        self.asset_dir = Path(__file__).resolve().parent.parent / "assets" / "wallet"

    def configured_for_local_signing(self) -> bool:
        return all(
            [
                (settings.wallet_pass_type_identifier or "").strip(),
                (settings.wallet_team_identifier or "").strip(),
                self._has_material(
                    path_value=settings.wallet_signer_certificate_path,
                    pem_value=settings.wallet_signer_certificate_pem,
                ),
                self._has_material(
                    path_value=settings.wallet_signer_key_path,
                    pem_value=settings.wallet_signer_key_pem,
                ),
                self._has_material(
                    path_value=settings.wallet_wwdr_certificate_path,
                    pem_value=settings.wallet_wwdr_certificate_pem,
                ),
            ]
        )

    def build_pass(self, *, title: str, code: str, payload: str) -> bytes:
        pass_type_identifier = self._required_value(
            settings.wallet_pass_type_identifier,
            "WALLET_PASS_TYPE_IDENTIFIER",
        )
        team_identifier = self._required_value(
            settings.wallet_team_identifier,
            "WALLET_TEAM_IDENTIFIER",
        )

        required_assets = {
            "icon.png": self.asset_dir / "icon.png",
            "icon@2x.png": self.asset_dir / "icon@2x.png",
            "logo.png": self.asset_dir / "logo.png",
            "logo@2x.png": self.asset_dir / "logo@2x.png",
        }
        for name, path in required_assets.items():
            if not path.exists():
                raise WalletPassConfigurationError(f"Missing Apple Wallet asset: {name}")

        with tempfile.TemporaryDirectory(prefix="perknation-pkpass-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            cert_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="signer.pem",
                path_value=settings.wallet_signer_certificate_path,
                pem_value=settings.wallet_signer_certificate_pem,
                path_env_name="WALLET_SIGNER_CERTIFICATE_PATH",
                pem_env_name="WALLET_SIGNER_CERTIFICATE_PEM",
            )
            key_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="signer.key.pem",
                path_value=settings.wallet_signer_key_path,
                pem_value=settings.wallet_signer_key_pem,
                path_env_name="WALLET_SIGNER_KEY_PATH",
                pem_env_name="WALLET_SIGNER_KEY_PEM",
            )
            wwdr_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="wwdr.pem",
                path_value=settings.wallet_wwdr_certificate_path,
                pem_value=settings.wallet_wwdr_certificate_pem,
                path_env_name="WALLET_WWDR_CERTIFICATE_PATH",
                pem_env_name="WALLET_WWDR_CERTIFICATE_PEM",
            )
            pass_json = self._build_pass_json(
                title=title,
                code=code,
                payload=payload,
                pass_type_identifier=pass_type_identifier,
                team_identifier=team_identifier,
            )
            (temp_dir / "pass.json").write_text(
                json.dumps(pass_json, separators=(",", ":"), ensure_ascii=False),
                encoding="utf-8",
            )

            for name, source in required_assets.items():
                shutil.copy2(source, temp_dir / name)

            manifest = self._build_manifest(temp_dir)
            (temp_dir / "manifest.json").write_text(
                json.dumps(manifest, separators=(",", ":"), ensure_ascii=False),
                encoding="utf-8",
            )

            self._sign_manifest(
                manifest_path=temp_dir / "manifest.json",
                signature_path=temp_dir / "signature",
                signer_certificate_path=cert_path,
                signer_key_path=key_path,
                wwdr_certificate_path=wwdr_path,
            )

            return self._zip_pass(temp_dir)

    def _required_value(self, value: str | None, env_name: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise WalletPassConfigurationError(f"{env_name} is not configured.")
        return normalized

    def _required_path(self, raw_path: str | None, env_name: str) -> Path:
        value = self._required_value(raw_path, env_name)
        path = Path(value).expanduser()
        if not path.exists():
            raise WalletPassConfigurationError(f"{env_name} does not exist at {path}.")
        return path

    @staticmethod
    def _has_material(*, path_value: str | None, pem_value: str | None) -> bool:
        return bool((path_value or "").strip() or (pem_value or "").strip())

    def _materialize_material(
        self,
        *,
        temp_dir: Path,
        filename: str,
        path_value: str | None,
        pem_value: str | None,
        path_env_name: str,
        pem_env_name: str,
    ) -> Path:
        if (path_value or "").strip():
            return self._required_path(path_value, path_env_name)

        pem_text = (pem_value or "").strip()
        if not pem_text:
            raise WalletPassConfigurationError(
                f"Configure either {path_env_name} or {pem_env_name}."
            )

        material_path = temp_dir / filename
        normalized_pem = pem_text.replace("\\n", "\n").strip()
        if not normalized_pem.endswith("\n"):
            normalized_pem += "\n"
        material_path.write_text(normalized_pem, encoding="utf-8")
        return material_path

    def _build_pass_json(
        self,
        *,
        title: str,
        code: str,
        payload: str,
        pass_type_identifier: str,
        team_identifier: str,
    ) -> dict[str, object]:
        serial_number = hashlib.sha1(f"{title}|{code}|{payload}".encode("utf-8")).hexdigest()
        support_host = urlparse(payload).netloc or "perknation.app"
        safe_title = title.strip()[:80]
        safe_code = code.strip()[:80]

        return {
            "formatVersion": 1,
            "passTypeIdentifier": pass_type_identifier,
            "serialNumber": serial_number,
            "teamIdentifier": team_identifier,
            # Prevent Wallet pass forwarding between users.
            "sharingProhibited": True,
            "organizationName": settings.wallet_organization_name,
            "description": safe_title,
            "logoText": "PerkNation",
            "foregroundColor": "rgb(255,255,255)",
            "backgroundColor": "rgb(15,23,42)",
            "labelColor": "rgb(166,184,211)",
            "barcodes": [
                {
                    "format": "PKBarcodeFormatQR",
                    "message": payload,
                    "messageEncoding": "iso-8859-1",
                    "altText": safe_code,
                }
            ],
            "barcode": {
                "format": "PKBarcodeFormatQR",
                "message": payload,
                "messageEncoding": "iso-8859-1",
                "altText": safe_code,
            },
            "generic": {
                "primaryFields": [
                    {
                        "key": "title",
                        "label": "Offer",
                        "value": safe_title,
                    }
                ],
                "secondaryFields": [
                    {
                        "key": "code",
                        "label": "Code",
                        "value": safe_code,
                    }
                ],
                "auxiliaryFields": [
                    {
                        "key": "open",
                        "label": "Open",
                        "value": "Scan or tap to redeem in PerkNation",
                    }
                ],
                "backFields": [
                    {
                        "key": "link",
                        "label": "PerkNation link",
                        "value": payload,
                    },
                    {
                        "key": "support",
                        "label": "Support",
                        "value": f"https://{support_host}",
                    },
                ],
            },
        }

    def _build_manifest(self, temp_dir: Path) -> dict[str, str]:
        manifest: dict[str, str] = {}
        for name in self.ARCHIVE_FILENAMES:
            if name in {"manifest.json", "signature"}:
                continue
            file_path = temp_dir / name
            if not file_path.is_file():
                raise WalletPassConfigurationError(f"Missing Apple Wallet archive file: {name}")
            manifest[file_path.name] = hashlib.sha1(file_path.read_bytes()).hexdigest()
        return manifest

    def _sign_manifest(
        self,
        *,
        manifest_path: Path,
        signature_path: Path,
        signer_certificate_path: Path,
        signer_key_path: Path,
        wwdr_certificate_path: Path,
    ) -> None:
        command = [
            "openssl",
            "smime",
            "-binary",
            "-sign",
            "-signer",
            str(signer_certificate_path),
            "-inkey",
            str(signer_key_path),
            "-certfile",
            str(wwdr_certificate_path),
            "-in",
            str(manifest_path),
            "-out",
            str(signature_path),
            "-outform",
            "DER",
        ]

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise WalletPassSigningError(f"OpenSSL is unavailable: {exc}") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise WalletPassSigningError(
                stderr or "OpenSSL failed while signing the Apple Wallet pass."
            )

    def _zip_pass(self, temp_dir: Path) -> bytes:
        output_path = temp_dir / "wallet.pkpass"
        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
            for name in self.ARCHIVE_FILENAMES:
                archive.write(temp_dir / name, arcname=name)
        return output_path.read_bytes()

    @staticmethod
    def filename_for_code(code: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", code).strip("-").lower() or "perk-pass"
        return f"{slug}.pkpass"


wallet_pass_service = WalletPassService()
