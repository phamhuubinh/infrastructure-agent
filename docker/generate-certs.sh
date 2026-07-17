#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
mkdir -p "$CERT_DIR"

CERT_FILE="$CERT_DIR/localhost.crt"
KEY_FILE="$CERT_DIR/localhost.key"

if [[ -f "$CERT_FILE" && -f "$KEY_FILE" ]]; then
    echo "[*] Self-signed cert already exists at $CERT_DIR — skipping generation"
    exit 0
fi

echo "[*] Generating self-signed certificate for local development..."
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -subj "/CN=localhost/O=Orion Development/C=US" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 "$KEY_FILE"
echo "[+] Certificate: $CERT_FILE"
echo "[+] Key:        $KEY_FILE"
