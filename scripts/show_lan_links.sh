#!/bin/zsh
set -euo pipefail

ROOT_DIR="/Users/nation/Documents/New project/PerkNationBackend"

find_lan_ip() {
  local ip=""
  ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
  if [[ -z "$ip" ]]; then
    ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
  fi
  if [[ -z "$ip" ]]; then
    ip="$(ifconfig | awk '/inet / && $2 != "127.0.0.1" {print $2; exit}')"
  fi
  print -r -- "$ip"
}

LAN_IP="$(find_lan_ip)"
if [[ -z "$LAN_IP" ]]; then
  echo "Could not detect LAN IP."
  exit 1
fi

echo "PerkNation LAN URLs (share these on your local network):"
echo "Main website (dark):  http://$LAN_IP:8000/"
echo "Main website (white): http://$LAN_IP:8000/white/"
echo "Login page:           http://$LAN_IP:8000/login"
echo "User portal:          http://$LAN_IP:8000/user"
echo "Merchant portal:      http://$LAN_IP:8000/merchant"
echo "Admin portal:         http://$LAN_IP:8000/admin"
echo "API docs:             http://$LAN_IP:8000/docs"
echo ""
echo "HTTPS (self-signed):  https://$LAN_IP:8443/"
echo ""
echo "Tip: if services are down, run:"
echo "  cd \"$ROOT_DIR\" && ./scripts/watchdog_services.sh"
