"""Register a Circle Developer-Controlled Wallets Entity Secret.

Two modes:

1. Fully automated (default):
   - Requires CIRCLE_API_KEY in .env
   - Generates 32-byte entity secret
   - Fetches Circle's RSA public key
   - Encrypts entity secret with RSA-OAEP-SHA256
   - Registers ciphertext with Circle
   - Saves entity secret to .env (and prints recovery file location)

2. Offline encrypt (if Console UI requires you to paste ciphertext manually):
   - Pass `--public-key-pem path/to/key.pem`
   - Generates entity secret + encrypts + prints ciphertext
   - You paste ciphertext into Console manually

Usage:
    # Mode 1 (automated):
    python scripts/register_entity_secret.py

    # Mode 2 (offline):
    python scripts/register_entity_secret.py --public-key-pem circle_pubkey.pem
"""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import sys
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CIRCLE_BASE = "https://api.circle.com"  # sandbox base URL


def encrypt_entity_secret(entity_secret_hex: str, public_key_pem: bytes) -> str:
    pub = serialization.load_pem_public_key(public_key_pem)
    ct = pub.encrypt(
        bytes.fromhex(entity_secret_hex),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ct).decode()


def append_to_env(key: str, value: str) -> None:
    """Append a KEY=VALUE line to .env if not already present."""
    text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    if f"{key}=" in text:
        # Replace existing line
        lines = []
        for line in text.splitlines():
            if line.startswith(f"{key}=") and "=" not in line.split("=", 1)[1]:
                lines.append(f"{key}={value}")
            elif line.startswith(f"{key}="):
                lines.append(f"{key}={value}")
            else:
                lines.append(line)
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        with ENV_PATH.open("a", encoding="utf-8") as f:
            f.write(f"\n{key}={value}\n")


def offline_mode(pem_path: Path) -> None:
    print(f"Reading public key from {pem_path}")
    pem = pem_path.read_bytes()
    secret = secrets.token_hex(32)
    print(f"\nGenerated ENTITY_SECRET (save this in .env immediately):")
    print(f"  CIRCLE_ENTITY_SECRET={secret}")
    ct = encrypt_entity_secret(secret, pem)
    print(f"\nCIPHERTEXT (paste this into Circle Console 'Register Entity Secret' form):")
    print(ct)


def automated_mode(api_key: str) -> None:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print("Fetching Circle's RSA public key...")
    r = httpx.get(f"{CIRCLE_BASE}/v1/w3s/config/entity/publicKey", headers=headers, timeout=20)
    r.raise_for_status()
    pem_str = r.json()["data"]["publicKey"]
    pem_bytes = pem_str.encode()
    print("  Got public key.")

    secret = secrets.token_hex(32)
    print(f"\nGenerated ENTITY_SECRET (32 bytes hex).")
    ct = encrypt_entity_secret(secret, pem_bytes)
    print(f"  Ciphertext length: {len(ct)} chars (base64).")

    print("\nRegistering ciphertext with Circle...")
    r = httpx.post(
        f"{CIRCLE_BASE}/v1/w3s/config/entity/entitySecret",
        headers=headers,
        json={"entitySecretCiphertext": ct},
        timeout=30,
    )
    if r.status_code >= 400:
        print(f"  ERROR {r.status_code}: {r.text}")
        print("\nLikely causes: entity secret already registered (only allowed once),")
        print("or the API key does not have entity admin permissions.")
        sys.exit(1)
    data = r.json().get("data", {})
    print("  Registration successful.")

    recovery_b64 = data.get("recoveryFile", "")
    if recovery_b64:
        recovery_path = PROJECT_ROOT / "circle_recovery_file.dat"
        recovery_path.write_bytes(base64.b64decode(recovery_b64))
        print(f"\nRecovery file saved to: {recovery_path}")
        print("BACK THIS UP somewhere safe. It is the ONLY way to recover wallets")
        print("if you lose the entity secret.")

    append_to_env("CIRCLE_ENTITY_SECRET", secret)
    print(f"\nSaved CIRCLE_ENTITY_SECRET to {ENV_PATH}")
    print("\nDone. Next step: create a wallet on ARC-TESTNET via")
    print("  scripts/create_sentinel_wallet.py")


def main() -> None:
    load_dotenv(ENV_PATH)
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-key-pem", type=Path, help="Offline mode: encrypt with given PEM file")
    args = parser.parse_args()

    if args.public_key_pem:
        offline_mode(args.public_key_pem)
        return

    api_key = os.environ.get("CIRCLE_API_KEY", "")
    if not api_key:
        print("CIRCLE_API_KEY is not set in .env. Either fill it first, or use --public-key-pem mode.")
        sys.exit(1)
    automated_mode(api_key)


if __name__ == "__main__":
    main()
