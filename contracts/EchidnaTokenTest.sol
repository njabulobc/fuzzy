// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import "./Token.sol";

// Echidna will deploy this contract and fuzz it.
contract EchidnaTokenTest {
    Token public token;

    constructor() {
        token = new Token();
    }

    // Property 1: totalSupply never changes from 1_000_000
    function echidna_total_supply_constant() public view returns (bool) {
        return token.totalSupply() == 1_000_000;
    }

    // Property 2: this contract's balance is never greater than totalSupply
    function echidna_balance_not_more_than_supply() public view returns (bool) {
        return token.balances(address(this)) <= token.totalSupply();
    }
}
