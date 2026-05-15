// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title MockUSDC
/// @notice Stand-in for real USDC on Arc Testnet, granting the project freeze / refund /
///         quarantine primitives that the Circle USDC contract does not expose to third
///         parties. Mirrors the regulated-asset behavior required for the AML/CFT sentinel
///         demo (HKMA AML Guideline for Licensed Stablecoin Issuers, Para 4.34, 4.39, 5.7,
///         5.9-5.12, 6.40-6.42, 7.5). README maintains the full traceability matrix.
/// @dev    Roles: DEFAULT_ADMIN_ROLE (owner — mint/burn/unfreeze) and SENTINEL_ROLE
///         (agent — freeze/refund/quarantine; cannot mint/burn). Agent compromise
///         therefore cannot drain or inflate supply.
contract MockUSDC is ERC20, AccessControl {
    bytes32 public constant SENTINEL_ROLE = keccak256("SENTINEL_ROLE");

    mapping(address => bool) public frozen;
    mapping(address => string) public freezeReason;

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

    error AccountFrozen(address account);
    error InvalidAmount();
    error InvalidAddress();

    constructor(address owner_, address sentinel_) ERC20("Mock USDC", "mUSDC") {
        if (owner_ == address(0) || sentinel_ == address(0)) revert InvalidAddress();
        _grantRole(DEFAULT_ADMIN_ROLE, owner_);
        _grantRole(SENTINEL_ROLE, sentinel_);
    }

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    // ------------------------------------------------------------
    // OWNER actions
    // ------------------------------------------------------------

    function mint(address to, uint256 amount) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (to == address(0)) revert InvalidAddress();
        _mint(to, amount);
    }

    /// @notice Para 5.10(c) full-coverage. OWNER-only; sentinel cannot invoke.
    function burn(address from, uint256 amount, string calldata paragraphRef)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        _burn(from, amount);
        emit ComplianceBurn(from, amount, paragraphRef);
    }

    function unfreezeAddress(address target) external onlyRole(DEFAULT_ADMIN_ROLE) {
        frozen[target] = false;
        freezeReason[target] = "";
        emit AddressUnfrozen(target);
    }

    // ------------------------------------------------------------
    // SENTINEL actions
    // ------------------------------------------------------------

    /// @notice Para 5.10(c), 7.7 — freeze stablecoin upon AML/sanctions match.
    function freezeAddress(address target, string calldata reason, string calldata paragraphRef)
        external
        onlyRole(SENTINEL_ROLE)
    {
        if (target == address(0)) revert InvalidAddress();
        frozen[target] = true;
        freezeReason[target] = reason;
        emit AddressFrozen(target, reason, paragraphRef);
    }

    /// @notice Para 6.22-6.24 — force-refund a transfer to its original sender.
    /// @dev    Must be called BEFORE freezing either party; once frozen, transfers revert.
    function refundTransfer(
        bytes32 originalTxHash,
        address from,
        address to,
        uint256 amount,
        string calldata paragraphRef
    ) external onlyRole(SENTINEL_ROLE) {
        if (amount == 0) revert InvalidAmount();
        _transfer(to, from, amount);
        emit TransferRefunded(originalTxHash, from, to, amount, paragraphRef);
    }

    /// @notice High-risk: force-move funds to a pre-registered recovery wallet.
    /// @dev    Must be called BEFORE freezing the recovery address.
    function quarantineTransfer(
        bytes32 originalTxHash,
        address from,
        address recovery,
        uint256 amount,
        string calldata paragraphRef
    ) external onlyRole(SENTINEL_ROLE) {
        if (recovery == address(0)) revert InvalidAddress();
        if (amount == 0) revert InvalidAmount();
        _transfer(from, recovery, amount);
        emit TransferQuarantined(originalTxHash, from, recovery, amount, paragraphRef);
    }

    // ------------------------------------------------------------
    // Transfer hook
    // ------------------------------------------------------------

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && frozen[from]) revert AccountFrozen(from);
        if (to != address(0) && frozen[to]) revert AccountFrozen(to);
        super._update(from, to, value);
    }
}
