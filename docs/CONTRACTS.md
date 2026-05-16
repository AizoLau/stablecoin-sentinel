# Smart Contract Reference

The repo deploys one contract: **`MockUSDC`** (`contracts/src/MockUSDC.sol`).

| Property | Value |
|---|---|
| Solidity version | `^0.8.24` |
| OpenZeppelin version | v5.6.1 (`@openzeppelin/contracts/token/ERC20/ERC20.sol` + `access/AccessControl.sol`) |
| Token name / symbol | `Mock USDC` / `mUSDC` |
| Decimals | **6** (matches real USDC) |
| Deployed address (Arc Testnet) | `0xA43143DF2C00Bce848af35eF4Cb69911Ae37d95B` |

The contract stands in for real USDC at the regulated-asset interface level
(transfer / mint / burn) while exposing **issuer-tier** AML/CFT primitives
(freeze / refund / quarantine) that real USDC does not give third-party
developers. In production these would be invoked via Circle's compliance API
against the canonical USDC contract.

---

## Roles

`AccessControl` from OpenZeppelin. Two roles defined:

| Role | bytes32 | Granted to | Capabilities |
|---|---|---|---|
| `DEFAULT_ADMIN_ROLE` (a.k.a. **OWNER**) | `0x00...00` | Deployer (`$DEPLOYER_ADDRESS`) at constructor time | `mint`, `burn`, `unfreezeAddress`, manage roles |
| `SENTINEL_ROLE` | `keccak256("SENTINEL_ROLE")` | Circle sentinel wallet (`$CIRCLE_SENTINEL_WALLET_ADDRESS`), granted by OWNER post-deploy via `grantRole` | `freezeAddress`, `refundTransfer`, `quarantineTransfer` — **cannot mint or burn** |

### Role-isolation invariant

This is the security backbone of the project: even with full agent compromise +
private-key leakage, the attacker can only freeze or quarantine — they cannot
inflate supply or unilaterally drain wallets. Tested in
`contracts/test/MockUSDC.t.sol::test_SentinelCannotMint` and
`test_SentinelCannotBurn`.

---

## Functions

### Constructor

```solidity
constructor(address owner_, address sentinel_)
```

Grants `DEFAULT_ADMIN_ROLE` to `owner_` and `SENTINEL_ROLE` to `sentinel_`.
Reverts with `InvalidAddress()` if either is `address(0)`.

Both addresses are passed via the Foundry deploy script (`Deploy.s.sol`); the
sentinel role is **separately** granted to the Circle wallet post-deploy via
`grantRole` (see `docs/deployment.md`).

### `decimals()` `pure external returns (uint8)`

Returns `6`. Overrides OZ ERC20's default `18`.

---

### OWNER-only functions

#### `mint(address to, uint256 amount)`

Mints `amount` raw units to `to`. Reverts with `InvalidAddress()` if
`to == address(0)`.

| | |
|---|---|
| Caller | `DEFAULT_ADMIN_ROLE` |
| Reverts on caller mismatch | `AccessControlUnauthorizedAccount` |
| Approx gas | 48k |

#### `burn(address from, uint256 amount, string paragraphRef)`

Burns `amount` from `from`. Emits `ComplianceBurn(from, amount, paragraphRef)`.
The `paragraphRef` is stored only in the event log; intended for on-chain
auditability of which HKMA paragraph the burn invokes (typically `5.10(c)`).

| | |
|---|---|
| Caller | `DEFAULT_ADMIN_ROLE` |
| Sentinel cannot invoke | `AccessControlUnauthorizedAccount` |
| Approx gas | 34k |

#### `unfreezeAddress(address target)`

Clears the `frozen[target]` flag and `freezeReason[target]`. Emits
`AddressUnfrozen(target)`.

| | |
|---|---|
| Caller | `DEFAULT_ADMIN_ROLE` |
| Sentinel cannot invoke | `AccessControlUnauthorizedAccount` |
| Approx gas | 57k |

Used in the demo's `unfreeze_first` flow so a previously-frozen recipient can
be re-frozen by the agent.

---

### SENTINEL-only functions

These are the on-chain enforcement primitives the agent can invoke. Each emits
an event carrying the cited HKMA paragraph reference for traceability.

#### `freezeAddress(address target, string reason, string paragraphRef)`

Marks `target` as frozen. After this call, any `transfer` or `transferFrom`
**from or to** `target` reverts with `AccountFrozen(target)`. Emits
`AddressFrozen(target, reason, paragraphRef)`.

| | |
|---|---|
| Caller | `SENTINEL_ROLE` |
| Reverts on `target == address(0)` | `InvalidAddress()` |
| Approx gas | 68k |
| Typical paragraphRef | `"5.10(c)"`, `"7.5"`, or comma-joined like `"5.10, 6.29, 4.39"` |

#### `refundTransfer(bytes32 originalTxHash, address from, address to, uint256 amount, string paragraphRef)`

Force-moves `amount` units from `to` back to `from`. Emits
`TransferRefunded(originalTxHash, from, to, amount, paragraphRef)`. The
`originalTxHash` is the tx hash of the suspicious transfer being unwound.

| | |
|---|---|
| Caller | `SENTINEL_ROLE` |
| Reverts on `amount == 0` | `InvalidAmount()` |
| **Important**: Must be invoked BEFORE freezing either party — once frozen, the internal `_transfer` reverts | — |
| Approx gas | 47k |
| Typical paragraphRef | `"6.22-6.24"` |

#### `quarantineTransfer(bytes32 originalTxHash, address from, address recovery, uint256 amount, string paragraphRef)`

Force-moves `amount` units from `from` to `recovery` (a pre-registered recovery
wallet). Emits `TransferQuarantined(originalTxHash, from, recovery, amount, paragraphRef)`.

| | |
|---|---|
| Caller | `SENTINEL_ROLE` |
| Reverts on `recovery == address(0)` | `InvalidAddress()` |
| Reverts on `amount == 0` | `InvalidAmount()` |
| Approx gas | 69k |
| Typical paragraphRef | `"6.41"` |

---

### Public state-reading functions

#### `frozen(address) returns (bool)`

Public mapping getter. `true` if the address has been frozen by sentinel and
not since unfrozen by owner.

#### `freezeReason(address) returns (string)`

Public mapping getter. Returns the `reason` argument from the most recent
`freezeAddress` call. Empty after `unfreezeAddress`.

---

### Overridden ERC20 hooks

#### `_update(address from, address to, uint256 value)` `internal override`

OpenZeppelin v5's unified transfer hook (replaces v4's `_beforeTokenTransfer`).
We override to reject transfers when either endpoint is frozen:

```solidity
function _update(address from, address to, uint256 value) internal override {
    if (from != address(0) && frozen[from]) revert AccountFrozen(from);
    if (to != address(0) && frozen[to]) revert AccountFrozen(to);
    super._update(from, to, value);
}
```

Notes:
- Mint (`from == address(0)`) bypasses the `from` check.
- Burn (`to == address(0)`) bypasses the `to` check.
- This means a frozen address **can still be burned** by OWNER (Para 5.10(c)
  unilateral burn pathway), which is the intended behavior.

---

## Events

All sentinel actions emit a paragraph-tagged event. Events serve two purposes:
(1) traceable on-chain audit trail, (2) downstream listeners (e.g. a separate
compliance reporting system) can subscribe without needing to know the agent's
internal state.

```solidity
event AddressFrozen(address indexed target, string reason, string paragraphRef);
event AddressUnfrozen(address indexed target);
event TransferRefunded(
    bytes32 indexed originalTxHash,
    address indexed from,
    address indexed to,
    uint256 amount,
    string paragraphRef
);
event TransferQuarantined(
    bytes32 indexed originalTxHash,
    address indexed from,
    address indexed recovery,
    uint256 amount,
    string paragraphRef
);
event ComplianceBurn(address indexed from, uint256 amount, string paragraphRef);
```

Plus the standard ERC20 `Transfer(from, to, value)` event from OpenZeppelin's
base contract.

### Event signatures (topic[0])

For raw log parsing:

| Event | Topic 0 |
|---|---|
| `AddressFrozen` | `keccak256("AddressFrozen(address,string,string)")` |
| `AddressUnfrozen` | `keccak256("AddressUnfrozen(address)")` |
| `TransferRefunded` | `keccak256("TransferRefunded(bytes32,address,address,uint256,string)")` |
| `TransferQuarantined` | `keccak256("TransferQuarantined(bytes32,address,address,uint256,string)")` |
| `ComplianceBurn` | `keccak256("ComplianceBurn(address,uint256,string)")` |
| `Transfer` | `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` |

---

## Custom errors

```solidity
error AccountFrozen(address account);
error InvalidAmount();
error InvalidAddress();
```

Plus `AccessControlUnauthorizedAccount(address account, bytes32 neededRole)`
inherited from OpenZeppelin v5.

### Error signatures (4-byte selectors)

| Error | Selector |
|---|---|
| `AccountFrozen(address)` | `0x...` (`bytes4(keccak256("AccountFrozen(address)"))`) |
| `InvalidAmount()` | `0x...` |
| `InvalidAddress()` | `0x...` |
| `AccessControlUnauthorizedAccount(address,bytes32)` | OZ standard |

(Compute with `cast sig "ErrorName(types)"`.)

---

## Test coverage

`contracts/test/MockUSDC.t.sol` — **18 tests, 18 passing**:

| Test | Verifies |
|---|---|
| `test_InitialRolesGranted` | Constructor wiring of OWNER + SENTINEL roles |
| `test_DecimalsIsSix` | USDC-compatible 6-decimal precision |
| `test_OwnerCanMint` | Owner can mint |
| `test_SentinelCannotMint` | **Role isolation**: sentinel reverts on mint |
| `test_OwnerCanBurn` | Owner can burn |
| `test_SentinelCannotBurn` | **Role isolation**: sentinel reverts on burn |
| `test_SentinelCanFreeze` | Sentinel can freeze + emits event |
| `test_OwnerCannotFreeze` | Reverse role isolation: owner cannot freeze (only sentinel) |
| `test_FrozenAddressCannotSend` | Transfer from frozen address reverts |
| `test_FrozenAddressCannotReceive` | Transfer to frozen address reverts |
| `test_OwnerCanUnfreeze` | Owner can unfreeze + clears reason |
| `test_SentinelCannotUnfreeze` | Sentinel cannot unfreeze |
| `test_SentinelCanRefund` | Sentinel can force-return funds |
| `test_RefundRevertsOnZeroAmount` | InvalidAmount() error path |
| `test_SentinelCanQuarantine` | Sentinel can force-move to recovery |
| `test_QuarantineRevertsOnZeroRecovery` | InvalidAddress() error path |
| `test_FreezeEventCarriesParagraphRef` | Event carries `paragraphRef` field for traceability |
| `test_RefundEventCarriesParagraphRef` | Same, for refund |

Run from `contracts/`:

```bash
forge test
forge test --gas-report   # for gas costs
forge test -vvv           # for traces
```

---

## Deployment

See `contracts/script/Deploy.s.sol` and `docs/deployment.md`.

Summary:

```bash
cd contracts
set -a; source ../.env; set +a
forge script script/Deploy.s.sol:Deploy \
  --rpc-url https://rpc.testnet.arc.network \
  --broadcast
```

Required env vars: `DEPLOYER_PRIVATE_KEY`, `SENTINEL_ADDRESS`,
`DEMO_ALICE_ADDRESS` (alice gets a 10k mUSDC seed).

**Post-deploy step**: grant `SENTINEL_ROLE` to the Circle Wallet:

```bash
cast send <MOCK_USDC_ADDR> "grantRole(bytes32,address)" \
  $(cast keccak "SENTINEL_ROLE") <CIRCLE_SENTINEL_WALLET_ADDRESS> \
  --rpc-url https://rpc.testnet.arc.network \
  --private-key $DEPLOYER_PRIVATE_KEY
```

The deployed instance has SENTINEL_ROLE already granted to
`0x11afacf004f144db1df3857ee1ea555d233c33c7` (our Circle wallet).
