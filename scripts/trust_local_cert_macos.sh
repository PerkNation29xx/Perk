#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_FILE="$ROOT_DIR/certs/localhost.crt"

if [[ ! -f "$CERT_FILE" ]]; then
  echo "Certificate not found at $CERT_FILE"
  echo "Run scripts/run_local_https.sh first to generate it."
  exit 1
fi

security add-trusted-cert \
  -d \
  -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" \
  "$CERT_FILE"

echo "Trusted local certificate: $CERT_FILE"
