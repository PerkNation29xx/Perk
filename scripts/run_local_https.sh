#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$ROOT_DIR/certs"
CERT_FILE="$CERT_DIR/localhost.crt"
KEY_FILE="$CERT_DIR/localhost.key"
OPENSSL_CONFIG="$CERT_DIR/localhost-openssl.cnf"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"

mkdir -p "$CERT_DIR"

NEEDS_REGEN=0
if [[ ! -f "$CERT_FILE" || ! -f "$KEY_FILE" ]]; then
  NEEDS_REGEN=1
elif [[ -n "$LAN_IP" ]]; then
  if ! openssl x509 -in "$CERT_FILE" -noout -text | grep -q "IP Address:$LAN_IP"; then
    NEEDS_REGEN=1
  fi
fi

if [[ "$NEEDS_REGEN" -eq 1 ]]; then
  cat > "$OPENSSL_CONFIG" <<'EOF'
[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = dn

[dn]
CN = localhost

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
EOF

  if [[ -n "$LAN_IP" ]]; then
    {
      echo "IP.2 = $LAN_IP"
    } >> "$OPENSSL_CONFIG"
  fi

  openssl req \
    -x509 \
    -nodes \
    -days 825 \
    -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -config "$OPENSSL_CONFIG"
fi

if [[ -n "$LAN_IP" ]]; then
  echo "Starting HTTPS API at https://127.0.0.1:8443 and https://$LAN_IP:8443"
else
  echo "Starting HTTPS API at https://127.0.0.1:8443"
fi
cd "$ROOT_DIR"
exec "$ROOT_DIR/.venv/bin/uvicorn" \
  app.main:app \
  --host 0.0.0.0 \
  --port 8443 \
  --ssl-keyfile "$KEY_FILE" \
  --ssl-certfile "$CERT_FILE"
