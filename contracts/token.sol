// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Token {
    mapping(address => uint256) public balances;
    uint256 public totalSupply;
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function mint(uint256 amount) public {
        // Intentional bug: anyone can mint
        totalSupply += amount;
        balances[msg.sender] += amount;
    }

    function burn(uint256 amount) public {
        require(balances[msg.sender] >= amount, "insufficient balance");

        // Intentional bug: no check for totalSupply underflow
        balances[msg.sender] -= amount;
        totalSupply -= amount;
    }

    function transfer(address to, uint256 amount) public {
        require(balances[msg.sender] >= amount, "insufficient balance");

        // Another intentional bug: unchecked arithmetic
        balances[msg.sender] -= amount;
        balances[to] += amount;
    }
}
