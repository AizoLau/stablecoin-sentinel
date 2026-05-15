"""Application settings loaded from environment / .env.

Centralized config so chain/agent/data layers never read env vars directly.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Arc Testnet
    arc_rpc_url: str = "https://rpc.testnet.arc.network"
    arc_chain_id: int = 5042002
    arc_rpc_url_alchemy: str = ""
    arc_rpc_url_quicknode: str = ""
    arc_explorer_url: str = "https://explorer.testnet.arc.network"

    # External services
    anthropic_api_key: str = ""
    dune_api_key: str = ""

    # Circle Wallets
    circle_api_key: str = ""
    circle_entity_secret: str = ""
    circle_sentinel_wallet_id: str = ""
    circle_sentinel_wallet_address: str = ""

    # Contracts
    mock_usdc_addr: str = ""

    # Demo wallets (testnet only)
    deployer_private_key: str = ""
    demo_alice_private_key: str = ""
    demo_bob_private_key: str = ""
    demo_recovery_address: str = ""

    # Backend
    log_level: str = "INFO"
    sqlite_path: str = "./audit.db"
    sse_heartbeat_seconds: int = 15

    sanctions_json_path: str = Field(
        default_factory=lambda: str(PROJECT_ROOT / "backend" / "data" / "sanctions_mock.json")
    )


def get_settings() -> Settings:
    return Settings()
