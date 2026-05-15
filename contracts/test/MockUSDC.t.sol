// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {MockUSDC} from "../src/MockUSDC.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";

contract MockUSDCTest is Test {
    MockUSDC internal token;

    address internal owner = makeAddr("owner");
    address internal sentinel = makeAddr("sentinel");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");
    address internal recovery = makeAddr("recovery");

    bytes32 internal constant SENTINEL_ROLE = keccak256("SENTINEL_ROLE");
    bytes32 internal constant ADMIN_ROLE = 0x00;

    function setUp() public {
        token = new MockUSDC(owner, sentinel);
        vm.prank(owner);
        token.mint(alice, 1_000_000_000);
    }

    // ---------- Role setup ----------

    function test_InitialRolesGranted() public view {
        assertTrue(token.hasRole(ADMIN_ROLE, owner));
        assertTrue(token.hasRole(SENTINEL_ROLE, sentinel));
        assertFalse(token.hasRole(SENTINEL_ROLE, owner));
        assertFalse(token.hasRole(ADMIN_ROLE, sentinel));
    }

    function test_DecimalsIsSix() public view {
        assertEq(token.decimals(), 6);
    }

    // ---------- Mint / burn role isolation ----------

    function test_OwnerCanMint() public {
        vm.prank(owner);
        token.mint(bob, 500);
        assertEq(token.balanceOf(bob), 500);
    }

    function test_SentinelCannotMint() public {
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, sentinel, ADMIN_ROLE)
        );
        vm.prank(sentinel);
        token.mint(bob, 500);
    }

    function test_OwnerCanBurn() public {
        vm.prank(owner);
        token.burn(alice, 100, "5.10(c)");
        assertEq(token.balanceOf(alice), 1_000_000_000 - 100);
    }

    function test_SentinelCannotBurn() public {
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, sentinel, ADMIN_ROLE)
        );
        vm.prank(sentinel);
        token.burn(alice, 100, "5.10(c)");
    }

    // ---------- Freeze flow ----------

    function test_SentinelCanFreeze() public {
        vm.prank(sentinel);
        token.freezeAddress(bob, "mixer-tag-match", "5.10(c)");
        assertTrue(token.frozen(bob));
        assertEq(token.freezeReason(bob), "mixer-tag-match");
    }

    function test_OwnerCannotFreeze() public {
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, owner, SENTINEL_ROLE)
        );
        vm.prank(owner);
        token.freezeAddress(bob, "test", "5.10(c)");
    }

    function test_FrozenAddressCannotSend() public {
        vm.prank(owner);
        token.mint(bob, 100);

        vm.prank(sentinel);
        token.freezeAddress(bob, "mixer", "5.10(c)");

        vm.expectRevert(abi.encodeWithSelector(MockUSDC.AccountFrozen.selector, bob));
        vm.prank(bob);
        token.transfer(alice, 1);
    }

    function test_FrozenAddressCannotReceive() public {
        vm.prank(sentinel);
        token.freezeAddress(bob, "mixer", "5.10(c)");

        vm.expectRevert(abi.encodeWithSelector(MockUSDC.AccountFrozen.selector, bob));
        vm.prank(alice);
        token.transfer(bob, 1);
    }

    function test_OwnerCanUnfreeze() public {
        vm.prank(sentinel);
        token.freezeAddress(bob, "mixer", "5.10(c)");

        vm.prank(owner);
        token.unfreezeAddress(bob);

        assertFalse(token.frozen(bob));
        assertEq(token.freezeReason(bob), "");
    }

    function test_SentinelCannotUnfreeze() public {
        vm.prank(sentinel);
        token.freezeAddress(bob, "mixer", "5.10(c)");

        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, sentinel, ADMIN_ROLE)
        );
        vm.prank(sentinel);
        token.unfreezeAddress(bob);
    }

    // ---------- Refund flow ----------

    function test_SentinelCanRefund() public {
        vm.prank(alice);
        token.transfer(bob, 50);
        assertEq(token.balanceOf(bob), 50);

        vm.prank(sentinel);
        token.refundTransfer(bytes32(uint256(0xdead)), alice, bob, 50, "6.22-6.24");

        assertEq(token.balanceOf(bob), 0);
        assertEq(token.balanceOf(alice), 1_000_000_000);
    }

    function test_RefundRevertsOnZeroAmount() public {
        vm.expectRevert(MockUSDC.InvalidAmount.selector);
        vm.prank(sentinel);
        token.refundTransfer(bytes32(uint256(0xdead)), alice, bob, 0, "6.22-6.24");
    }

    // ---------- Quarantine flow ----------

    function test_SentinelCanQuarantine() public {
        vm.prank(alice);
        token.transfer(bob, 50);

        vm.prank(sentinel);
        token.quarantineTransfer(bytes32(uint256(0xbeef)), bob, recovery, 50, "6.41");

        assertEq(token.balanceOf(bob), 0);
        assertEq(token.balanceOf(recovery), 50);
    }

    function test_QuarantineRevertsOnZeroRecovery() public {
        vm.prank(alice);
        token.transfer(bob, 50);

        vm.expectRevert(MockUSDC.InvalidAddress.selector);
        vm.prank(sentinel);
        token.quarantineTransfer(bytes32(uint256(0xbeef)), bob, address(0), 50, "6.41");
    }

    // ---------- Events emit paragraph references ----------

    function test_FreezeEventCarriesParagraphRef() public {
        vm.expectEmit(true, false, false, true, address(token));
        emit MockUSDC.AddressFrozen(bob, "sanctions-list-match", "7.5");
        vm.prank(sentinel);
        token.freezeAddress(bob, "sanctions-list-match", "7.5");
    }

    function test_RefundEventCarriesParagraphRef() public {
        vm.prank(alice);
        token.transfer(bob, 25);

        vm.expectEmit(true, true, true, true, address(token));
        emit MockUSDC.TransferRefunded(bytes32(uint256(0xfeed)), alice, bob, 25, "6.22-6.24");
        vm.prank(sentinel);
        token.refundTransfer(bytes32(uint256(0xfeed)), alice, bob, 25, "6.22-6.24");
    }
}
