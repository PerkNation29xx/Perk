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
        assets_root = Path(__file__).resolve().parent.parent / "assets"
        self.asset_dir = assets_root / "wallet"
        self.hq_asset_dir = assets_root / "wallet_hq"

    def configured_for_local_signing(self, *, template: str = "perknation") -> bool:
        resolved = self._resolve_template(template)
        pass_type_identifier, _ = self._resolve_template_value(
            resolved["pass_type_identifier"],
            resolved["pass_type_env_names"],
        )
        team_identifier, _ = self._resolve_template_value(
            resolved["team_identifier"],
            resolved["team_env_names"],
        )
        cert_path_value, cert_pem_value = self._resolve_template_material(
            path_value=resolved["cert_path"],
            pem_value=resolved["cert_pem"],
            path_env_names=resolved["cert_path_env_names"],
            pem_env_names=resolved["cert_pem_env_names"],
        )
        key_path_value, key_pem_value = self._resolve_template_material(
            path_value=resolved["key_path"],
            pem_value=resolved["key_pem"],
            path_env_names=resolved["key_path_env_names"],
            pem_env_names=resolved["key_pem_env_names"],
        )
        wwdr_path_value, wwdr_pem_value = self._resolve_template_material(
            path_value=resolved["wwdr_path"],
            pem_value=resolved["wwdr_pem"],
            path_env_names=resolved["wwdr_path_env_names"],
            pem_env_names=resolved["wwdr_pem_env_names"],
        )
        return all(
            [
                pass_type_identifier,
                team_identifier,
                self._has_material(path_value=cert_path_value, pem_value=cert_pem_value),
                self._has_material(path_value=key_path_value, pem_value=key_pem_value),
                self._has_material(path_value=wwdr_path_value, pem_value=wwdr_pem_value),
            ]
        )

    def build_pass(
        self,
        *,
        title: str,
        code: str,
        payload: str,
        template: str = "perknation",
        serial_number: str | None = None,
        status: str | None = None,
        expires_at: str | None = None,
        web_service_url: str | None = None,
        authentication_token: str | None = None,
        summary: str | None = None,
        terms: list[str] | str | None = None,
    ) -> bytes:
        resolved = self._resolve_template(template)
        pass_type_identifier, _ = self._resolve_template_value(
            resolved["pass_type_identifier"],
            resolved["pass_type_env_names"],
        )
        if not pass_type_identifier:
            return 0
        team_identifier = self._required_template_value(
            resolved["team_identifier"],
            resolved["team_env_names"],
        )
        cert_path_value, cert_pem_value = self._resolve_template_material(
            path_value=resolved["cert_path"],
            pem_value=resolved["cert_pem"],
            path_env_names=resolved["cert_path_env_names"],
            pem_env_names=resolved["cert_pem_env_names"],
        )
        key_path_value, key_pem_value = self._resolve_template_material(
            path_value=resolved["key_path"],
            pem_value=resolved["key_pem"],
            path_env_names=resolved["key_path_env_names"],
            pem_env_names=resolved["key_pem_env_names"],
        )
        wwdr_path_value, wwdr_pem_value = self._resolve_template_material(
            path_value=resolved["wwdr_path"],
            pem_value=resolved["wwdr_pem"],
            path_env_names=resolved["wwdr_path_env_names"],
            pem_env_names=resolved["wwdr_pem_env_names"],
        )

        required_assets = {
            "icon.png": resolved["asset_dir"] / "icon.png",
            "icon@2x.png": resolved["asset_dir"] / "icon@2x.png",
            "logo.png": resolved["asset_dir"] / "logo.png",
            "logo@2x.png": resolved["asset_dir"] / "logo@2x.png",
        }
        for name, path in required_assets.items():
            if not path.exists():
                raise WalletPassConfigurationError(f"Missing Apple Wallet asset: {name}")

        with tempfile.TemporaryDirectory(prefix="perknation-pkpass-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            cert_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="signer.pem",
                path_value=cert_path_value,
                pem_value=cert_pem_value,
                path_env_name=" or ".join(resolved["cert_path_env_names"]),
                pem_env_name=" or ".join(resolved["cert_pem_env_names"]),
            )
            key_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="signer.key.pem",
                path_value=key_path_value,
                pem_value=key_pem_value,
                path_env_name=" or ".join(resolved["key_path_env_names"]),
                pem_env_name=" or ".join(resolved["key_pem_env_names"]),
            )
            wwdr_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="wwdr.pem",
                path_value=wwdr_path_value,
                pem_value=wwdr_pem_value,
                path_env_name=" or ".join(resolved["wwdr_path_env_names"]),
                pem_env_name=" or ".join(resolved["wwdr_pem_env_names"]),
            )
            self._validate_signing_identity(
                signer_certificate_path=cert_path,
                expected_pass_type_identifier=pass_type_identifier,
                expected_team_identifier=team_identifier,
                template=resolved["key"],
            )
            pass_json = self._build_pass_json(
                title=title,
                code=code,
                payload=payload,
                pass_type_identifier=pass_type_identifier,
                team_identifier=team_identifier,
                template=resolved["key"],
                organization_name=resolved["organization_name"],
                description=resolved["description"],
                serial_number=serial_number,
                status=status,
                expires_at=expires_at,
                web_service_url=web_service_url,
                authentication_token=authentication_token,
                summary=summary,
                terms=terms,
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

    def _resolve_template(self, template: str) -> dict[str, object]:
        normalized = (template or "").strip().lower()
        if normalized == "hq":
            return {
                "key": "hq",
                "asset_dir": self.hq_asset_dir,
                "pass_type_identifier": settings.wallet_hq_pass_type_identifier,
                "pass_type_env_names": ("WALLET_HQ_PASS_TYPE_IDENTIFIER",),
                "team_identifier": settings.wallet_hq_team_identifier,
                "team_env_names": ("WALLET_HQ_TEAM_IDENTIFIER",),
                "organization_name": settings.wallet_hq_organization_name,
                "description": settings.wallet_hq_description,
                "cert_path": settings.wallet_hq_signer_certificate_path,
                "cert_pem": settings.wallet_hq_signer_certificate_pem,
                "cert_path_env_names": ("WALLET_HQ_SIGNER_CERTIFICATE_PATH",),
                "cert_pem_env_names": ("WALLET_HQ_SIGNER_CERTIFICATE_PEM",),
                "key_path": settings.wallet_hq_signer_key_path,
                "key_pem": settings.wallet_hq_signer_key_pem,
                "key_path_env_names": ("WALLET_HQ_SIGNER_KEY_PATH",),
                "key_pem_env_names": ("WALLET_HQ_SIGNER_KEY_PEM",),
                "wwdr_path": settings.wallet_hq_wwdr_certificate_path,
                "wwdr_pem": settings.wallet_hq_wwdr_certificate_pem,
                "wwdr_path_env_names": ("WALLET_HQ_WWDR_CERTIFICATE_PATH",),
                "wwdr_pem_env_names": ("WALLET_HQ_WWDR_CERTIFICATE_PEM",),
            }

        return {
            "key": "perknation",
            "asset_dir": self.asset_dir,
            "pass_type_identifier": settings.wallet_pass_type_identifier,
            "pass_type_env_names": ("WALLET_PASS_TYPE_IDENTIFIER",),
            "team_identifier": settings.wallet_team_identifier,
            "team_env_names": ("WALLET_TEAM_IDENTIFIER",),
            "organization_name": settings.wallet_organization_name,
            "description": "",
            "cert_path": settings.wallet_signer_certificate_path,
            "cert_pem": settings.wallet_signer_certificate_pem,
            "cert_path_env_names": ("WALLET_SIGNER_CERTIFICATE_PATH",),
            "cert_pem_env_names": ("WALLET_SIGNER_CERTIFICATE_PEM",),
            "key_path": settings.wallet_signer_key_path,
            "key_pem": settings.wallet_signer_key_pem,
            "key_path_env_names": ("WALLET_SIGNER_KEY_PATH",),
            "key_pem_env_names": ("WALLET_SIGNER_KEY_PEM",),
            "wwdr_path": settings.wallet_wwdr_certificate_path,
            "wwdr_pem": settings.wallet_wwdr_certificate_pem,
            "wwdr_path_env_names": ("WALLET_WWDR_CERTIFICATE_PATH",),
            "wwdr_pem_env_names": ("WALLET_WWDR_CERTIFICATE_PEM",),
        }

    @staticmethod
    def _resolve_template_value(
        primary_value: str | None,
        env_names: tuple[str, ...],
    ) -> tuple[str, tuple[str, ...]]:
        normalized = (primary_value or "").strip()
        if normalized:
            return normalized, env_names
        return "", env_names

    @staticmethod
    def _resolve_template_material(
        *,
        path_value: str | None,
        pem_value: str | None,
        path_env_names: tuple[str, ...],
        pem_env_names: tuple[str, ...],
    ) -> tuple[str | None, str | None]:
        normalized_path = (path_value or "").strip()
        if normalized_path:
            return normalized_path, None
        normalized_pem = (pem_value or "").strip()
        if normalized_pem:
            return None, normalized_pem
        return None, None

    def _required_template_value(self, value: str | None, env_names: tuple[str, ...]) -> str:
        normalized = (value or "").strip()
        if normalized:
            return normalized
        labels = " or ".join(env_names)
        raise WalletPassConfigurationError(f"{labels} is not configured.")

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
        normalized_path = (path_value or "").strip()
        if normalized_path:
            try:
                if Path(normalized_path).expanduser().exists():
                    return True
            except Exception:
                pass

        return bool((pem_value or "").strip())

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

    def _validate_signing_identity(
        self,
        *,
        signer_certificate_path: Path,
        expected_pass_type_identifier: str,
        expected_team_identifier: str,
        template: str,
    ) -> None:
        command = [
            "openssl",
            "x509",
            "-in",
            str(signer_certificate_path),
            "-noout",
            "-subject",
            "-nameopt",
            "RFC2253",
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise WalletPassConfigurationError(
                f"OpenSSL is unavailable while validating {template} signer certificate: {exc}"
            ) from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise WalletPassConfigurationError(
                stderr or f"Failed to read {template} signer certificate subject."
            )

        subject = (completed.stdout or "").strip()
        normalized_subject = subject.removeprefix("subject=").strip()
        uid = self._extract_subject_component(normalized_subject, "UID")
        team = self._extract_subject_component(normalized_subject, "OU")

        if not uid:
            raise WalletPassConfigurationError(
                f"The {template} signer certificate is missing UID. Use a Pass Type ID certificate "
                f"for {expected_pass_type_identifier}."
            )
        if uid.lower() != expected_pass_type_identifier.lower():
            raise WalletPassConfigurationError(
                f"The {template} signer certificate UID ({uid}) does not match the configured "
                f"pass type identifier ({expected_pass_type_identifier})."
            )
        if not team:
            raise WalletPassConfigurationError(
                f"The {template} signer certificate is missing OU/team identifier."
            )
        if team != expected_team_identifier:
            raise WalletPassConfigurationError(
                f"The {template} signer certificate OU ({team}) does not match the configured "
                f"team identifier ({expected_team_identifier})."
            )

    @staticmethod
    def _extract_subject_component(subject: str, key: str) -> str:
        match = re.search(rf"(?:^|,){re.escape(key)}=([^,]+)", subject)
        if not match:
            return ""
        return match.group(1).strip().strip('"')

    def _build_pass_json(
        self,
        *,
        title: str,
        code: str,
        payload: str,
        pass_type_identifier: str,
        team_identifier: str,
        template: str,
        organization_name: str,
        description: str,
        serial_number: str | None,
        status: str | None,
        expires_at: str | None,
        web_service_url: str | None,
        authentication_token: str | None,
        summary: str | None,
        terms: list[str] | str | None,
    ) -> dict[str, object]:
        serial_number = serial_number or self.serial_number_for(
            template=template,
            title=title,
            code=code,
            payload=payload,
        )
        support_host = urlparse(payload).netloc or "perknation.app"
        safe_title = title.strip()[:80]
        safe_code = code.strip()[:80]
        safe_summary = str(summary or "").strip()[:120]
        if isinstance(terms, list):
            safe_terms = "\n".join(str(term).strip() for term in terms if str(term).strip())[:1000]
        else:
            safe_terms = str(terms or "").strip()[:1000]
        normalized_status = str(status or "active").strip().lower()
        status_label = {
            "active": "Active",
            "issued": "Active",
            "redeemed": "Redeemed",
            "expired": "Expired",
            "voided": "Deactivated",
        }.get(normalized_status, "Active")
        is_voided = normalized_status in {"redeemed", "expired", "voided"}

        if template == "hq":
            display_name = safe_title or "The HQ Member"
            member_id = safe_code or "HQ-MEMBER"
            barcode_common = {
                "format": "PKBarcodeFormatQR",
                "message": payload,
                "messageEncoding": "iso-8859-1",
                "altText": member_id,
            }
            pass_json = {
                "formatVersion": 1,
                "passTypeIdentifier": pass_type_identifier,
                "serialNumber": serial_number,
                "teamIdentifier": team_identifier,
                "sharingProhibited": True,
                "organizationName": organization_name,
                "description": description or "The HQ",
                "logoText": "The HQ",
                "foregroundColor": "rgb(255,255,255)",
                "backgroundColor": "rgb(20,20,20)",
                "labelColor": "rgb(255,255,255)",
                "barcodes": [barcode_common],
                "barcode": barcode_common,
                "storeCard": {
                    "primaryFields": [
                        {
                            "key": "member",
                            "label": "Member",
                            "value": display_name,
                        },
                        {
                            "key": "member_id",
                            "label": "Member ID",
                            "value": member_id,
                        },
                    ],
                    "auxiliaryFields": [
                        {
                            "key": "status",
                            "label": "Status",
                            "value": "Active",
                        }
                    ],
                    "backFields": [
                        {
                            "key": "link",
                            "label": "The HQ link",
                            "value": payload,
                        }
                    ],
                },
            }
            if web_service_url and authentication_token:
                pass_json["webServiceURL"] = str(web_service_url).rstrip("/")
                pass_json["authenticationToken"] = str(authentication_token)
            return pass_json

        pass_json = {
            "formatVersion": 1,
            "passTypeIdentifier": pass_type_identifier,
            "serialNumber": serial_number,
            "teamIdentifier": team_identifier,
            "sharingProhibited": False,
            "organizationName": organization_name,
            "description": safe_title,
            "logoText": "PerkNation",
            "voided": is_voided,
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
                        "label": "Ticket",
                        "value": safe_title,
                    }
                ],
                "secondaryFields": [
                    *(
                        [
                            {
                                "key": "includes",
                                "label": "Includes",
                                "value": safe_summary,
                            }
                        ]
                        if safe_summary
                        else []
                    ),
                    {
                        "key": "code",
                        "label": "Code",
                        "value": safe_code,
                    }
                ],
                "auxiliaryFields": [
                    {
                        "key": "status",
                        "label": "Status",
                        "value": status_label,
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
                    *(
                        [
                            {
                                "key": "terms",
                                "label": "Ticket terms",
                                "value": safe_terms,
                            }
                        ]
                        if safe_terms
                        else []
                    ),
                ],
            },
        }
        if web_service_url and authentication_token:
            pass_json["webServiceURL"] = str(web_service_url).rstrip("/")
            pass_json["authenticationToken"] = str(authentication_token)
        if expires_at:
            pass_json["expirationDate"] = str(expires_at)
        return pass_json

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

    def send_update_notifications(self, push_tokens: list[str], *, template: str = "perknation") -> int:
        """
        Best-effort PassKit update push.

        Apple Wallet still falls back to polling the web service endpoints below;
        this just speeds up updates when a device has registered a push token.
        """
        tokens = [str(token or "").strip() for token in push_tokens if str(token or "").strip()]
        if not tokens:
            return 0

        resolved = self._resolve_template(template)
        pass_type_identifier = self._required_template_value(
            resolved["pass_type_identifier"],
            resolved["pass_type_env_names"],
        )
        cert_path_value, cert_pem_value = self._resolve_template_material(
            path_value=resolved["cert_path"],
            pem_value=resolved["cert_pem"],
            path_env_names=resolved["cert_path_env_names"],
            pem_env_names=resolved["cert_pem_env_names"],
        )
        key_path_value, key_pem_value = self._resolve_template_material(
            path_value=resolved["key_path"],
            pem_value=resolved["key_pem"],
            path_env_names=resolved["key_path_env_names"],
            pem_env_names=resolved["key_pem_env_names"],
        )

        if not self._has_material(path_value=cert_path_value, pem_value=cert_pem_value):
            return 0
        if not self._has_material(path_value=key_path_value, pem_value=key_pem_value):
            return 0
        if not shutil.which("curl"):
            return 0

        delivered = 0
        with tempfile.TemporaryDirectory(prefix="perknation-apns-") as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            cert_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="signer.pem",
                path_value=cert_path_value,
                pem_value=cert_pem_value,
                path_env_name=" or ".join(resolved["cert_path_env_names"]),
                pem_env_name=" or ".join(resolved["cert_pem_env_names"]),
            )
            key_path = self._materialize_material(
                temp_dir=temp_dir,
                filename="signer.key.pem",
                path_value=key_path_value,
                pem_value=key_pem_value,
                path_env_name=" or ".join(resolved["key_path_env_names"]),
                pem_env_name=" or ".join(resolved["key_pem_env_names"]),
            )
            for token in tokens:
                completed = subprocess.run(
                    [
                        "curl",
                        "--silent",
                        "--show-error",
                        "--http2",
                        "--max-time",
                        "8",
                        "--cert",
                        str(cert_path),
                        "--key",
                        str(key_path),
                        "-H",
                        f"apns-topic: {pass_type_identifier}",
                        "-H",
                        "apns-push-type: background",
                        "-H",
                        "content-type: application/json",
                        "-d",
                        "{}",
                        f"https://api.push.apple.com/3/device/{token}",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode == 0:
                    delivered += 1
        return delivered

    def _zip_pass(self, temp_dir: Path) -> bytes:
        output_path = temp_dir / "wallet.pkpass"
        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
            for name in self.ARCHIVE_FILENAMES:
                archive.write(temp_dir / name, arcname=name)
        return output_path.read_bytes()

    @staticmethod
    def filename_for_code(code: str, template: str = "perknation") -> str:
        normalized_template = (template or "").strip().lower()
        fallback_slug = "hq-pass" if normalized_template == "hq" else "perk-pass"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", code).strip("-").lower() or fallback_slug
        return f"{slug}.pkpass"

    @staticmethod
    def serial_number_for(*, template: str, title: str, code: str, payload: str) -> str:
        normalized_template = (template or "perknation").strip().lower() or "perknation"
        return hashlib.sha1(
            f"{normalized_template}|{title}|{code}|{payload}".encode("utf-8")
        ).hexdigest()


wallet_pass_service = WalletPassService()
