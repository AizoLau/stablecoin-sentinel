// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MockUSDC} from "../src/MockUSDC.sol";

/// @notice Deploy MockUSDC to Arc Testnet (chain ID 5042002).
/// @dev    Required env vars:
///         - DEPLOYER_PRIVATE_KEY  : deploys the contract; also becomes OWNER
///         - SENTINEL_ADDRESS      : address that will receive SENTINEL_ROLE
///         - DEMO_ALICE_ADDRESS    : receives initial mint for demo
///         Run with:
///         forge script script/Deploy.s.sol --rpc-url arc_testnet --broadcast
contract Deploy is Script {
    function run() external {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address sentinel = vm.envAddress("SENTINEL_ADDRESS");
        address demoAlice = vm.envAddress("DEMO_ALICE_ADDRESS");
        address deployer = vm.addr(deployerKey);

        console2.log("Deployer (OWNER):", deployer);
        console2.log("Sentinel:", sentinel);
        console2.log("Demo Alice:", demoAlice);

        vm.startBroadcast(deployerKey);

        MockUSDC token = new MockUSDC(deployer, sentinel);
        console2.log("MockUSDC deployed at:", address(token));

        // Seed Alice with 10,000 mUSDC for demo transfers
        uint256 seedAmount = 10_000 * 10 ** 6;
        token.mint(demoAlice, seedAmount);
        console2.log("Minted to Alice:", seedAmount);

        vm.stopBroadcast();
    }
}
