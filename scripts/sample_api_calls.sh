#!/usr/bin/env bash
set -euo pipefail

BASE_URL=${BASE_URL:-http://localhost:8000}

USER_TOKEN=$(curl -s "$BASE_URL/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@perknation.dev","password":"UserPass123!"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

MERCHANT_TOKEN=$(curl -s "$BASE_URL/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email":"merchant@perknation.dev","password":"MerchantPass123!"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

ADMIN_TOKEN=$(curl -s "$BASE_URL/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@perknation.dev","password":"AdminPass123!"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

echo "Consumer offers:"
curl -s "$BASE_URL/v1/consumer/offers" -H "Authorization: Bearer $USER_TOKEN" | python3 -m json.tool

echo "Merchant metrics:"
curl -s "$BASE_URL/v1/merchant/metrics" -H "Authorization: Bearer $MERCHANT_TOKEN" | python3 -m json.tool

echo "Admin approvals:"
curl -s "$BASE_URL/v1/admin/approvals" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool
