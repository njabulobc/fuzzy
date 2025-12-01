// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

contract Token {
    mapping(address => uint256) public balances;
    uint256 public totalSupply;

    constructor() {
        uint256 amount = 1_000_000;
        balances[msg.sender] = amount;
        totalSupply = amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        if (balances[msg.sender] < amount) {
            return false;
        }
        balances[msg.sender] -= amount;
        balances[to] += amount;
        return true;
    }
}
