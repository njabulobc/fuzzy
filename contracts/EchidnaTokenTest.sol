// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./Token.sol";

// Echidna will deploy this, and fuzz all public functions
contract EchidnaTokenTest {
    Token token;

    constructor() {
        token = new Token();
    }

    // Echidna requirement:
    // Property functions must return bool and start with "echidna_"
    function echidna_totalSupply_non_negative() public view returns (bool) {
        return token.totalSupply() >= 0;
    }

    function echidna_balance_never_negative() public view returns (bool) {
        return token.balances(address(this)) >= 0;
    }
}
