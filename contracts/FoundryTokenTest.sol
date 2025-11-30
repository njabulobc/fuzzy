// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "forge-std/Test.sol";
import "./Token.sol";

contract FoundryTokenTest is Test {
    Token token;

    function setUp() public {
        token = new Token();
    }

    function testMintIncreasesBalance() public {
        token.mint(100);
        assertEq(token.balances(address(this)), 100);
    }

    function testBurnFailsIfInsufficient() public {
        vm.expectRevert();
        token.burn(1);
    }

    // Foundry invariant (runs during --fuzz or invariant testing)
    function invariant_totalSupply_non_negative() public {
        assert(token.totalSupply() >= 0);
    }
}
