# Deployment Record

## Arc Testnet (Chain ID 5042002)

### MockUSDC

- **Contract address**: `0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B`
- **Deployed**: 2026-05-15
- **Deployer (OWNER)**: `0x1a7Fa6e012F648010fe4AF51123808D0cf9E1755`
- **Sentinel (SENTINEL_ROLE)**: `0xE14Ee06918eCA58cC034fe6466B77A80eA439844`
- **Name / Symbol / Decimals**: Mock USDC / mUSDC / 6
- **Initial mint**: 10,000 mUSDC to Alice (`0x6F106e2D89B58FEC6Fa1037Fd6e2cEAa586F7d59`)
- **RPC**: https://rpc.testnet.arc.network
- **Explorer**: https://explorer.testnet.arc.network/address/0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B

### Verification

```
name        = "Mock USDC"
symbol      = "mUSDC"
decimals    = 6
totalSupply = 10,000,000,000 (= 10,000 mUSDC)
Alice.bal   = 10,000,000,000
SENTINEL_ROLE granted to sentinel address: true
```

## Demo Wallets (testnet only)

| Role | Address |
|---|---|
| Deployer / OWNER | `0x1a7Fa6e012F648010fe4AF51123808D0cf9E1755` |
| Sentinel | `0xE14Ee06918eCA58cC034fe6466B77A80eA439844` |
| Alice (clean sender) | `0x6F106e2D89B58FEC6Fa1037Fd6e2cEAa586F7d59` |
| Bob (risky recipient) | `0x0F7Ba243461ba7E5043383E9D4D9B96AE8b02201` |
| Recovery (quarantine target) | `0x92daf439dC28071fdcDaA69C1d7297663E283f27` |

Private keys are stored in `.env` (gitignored). For reproducible demo, regenerate with
`cast wallet new -n 5` and fund each address via https://faucet.circle.com (20 USDC
per address per 2 hours on Arc Testnet).
