#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_CERT = Path("/Users/nation/.perknation-secrets/wallet/pass.pem")
DEFAULT_KEY = Path("/Users/nation/.perknation-secrets/wallet/pass.key.pem")
DEFAULT_WWDR = Path("/Users/nation/.perknation-secrets/wallet/AppleWWDRCAG4.pem")

DEFAULTS = {
    "WALLET_PASS_TYPE_IDENTIFIER": "pass.com.neonflux.perknation",
    "WALLET_TEAM_IDENTIFIER": "PL9PGQKXUW",
    "WALLET_ORGANIZATION_NAME": "PerkNation",
}


def _read_text(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    return path.read_text(encoding="utf-8").strip() + "\n"


def _wallet_env(cert_path: Path, key_path: Path, wwdr_path: Path) -> dict[str, str]:
    return {
        **DEFAULTS,
        "WALLET_SIGNER_CERTIFICATE_PEM": _read_text(cert_path),
        "WALLET_SIGNER_KEY_PEM": _read_text(key_path),
        "WALLET_WWDR_CERTIFICATE_PEM": _read_text(wwdr_path),
    }


def _copy_to_clipboard(value: str) -> None:
    try:
        subprocess.run(["pbcopy"], input=value, text=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Clipboard copy failed: {exc}") from exc


def _print_shell(env_map: dict[str, str]) -> None:
    for key, value in env_map.items():
        if "PEM" in key:
            escaped = value.replace("\\", "\\\\").replace("\n", "\\n")
            print(f"{key}='{escaped}'")
        else:
            print(f"{key}={value}")


def _print_human(env_map: dict[str, str]) -> None:
    for key, value in env_map.items():
        print(f"{key}")
        print(value.rstrip("\n"))
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit Render-ready Apple Wallet env values for PerkNation.",
    )
    parser.add_argument(
        "--copy",
        choices=[
            *DEFAULTS.keys(),
            "WALLET_SIGNER_CERTIFICATE_PEM",
            "WALLET_SIGNER_KEY_PEM",
            "WALLET_WWDR_CERTIFICATE_PEM",
        ],
        help="Copy one environment value to the macOS clipboard.",
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print values in single-line shell-friendly form (PEMs use literal \\n).",
    )
    parser.add_argument("--cert-path", type=Path, default=DEFAULT_CERT)
    parser.add_argument("--key-path", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--wwdr-path", type=Path, default=DEFAULT_WWDR)
    args = parser.parse_args()

    env_map = _wallet_env(args.cert_path, args.key_path, args.wwdr_path)

    if args.copy:
        _copy_to_clipboard(env_map[args.copy])
        print(f"Copied {args.copy} to clipboard.")
        return 0

    if args.shell:
        _print_shell(env_map)
        return 0

    _print_human(env_map)
    return 0


if __name__ == "__main__":
    sys.exit(main())
