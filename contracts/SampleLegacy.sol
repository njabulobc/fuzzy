pragma solidity ^0.4.25;

contract SampleLegacy {
    address public owner;
    uint256 public storedValue;

    // Old-style constructor (0.4.x)
    function SampleLegacy() public {
        owner = msg.sender;
    }

    // BAD: Anyone can update storedValue (Slither will flag)
    function unsafeSetValue(uint256 x) public {
        storedValue = x;
    }

    // Proper protected setter
    function safeSetValue(uint256 x) public onlyOwner {
        storedValue = x;
    }

    // BAD: Reentrancy-prone withdraw (Slither will flag)
    function withdraw() public {
        uint256 amount = address(this).balance;
        // Pre-0.5 call pattern
        if (!msg.sender.call.value(amount)()) {
            revert();
        }
    }

    modifier onlyOwner() {
        require(msg.sender == owner);
        _;
    }

    // Old fallback syntax
    function() public payable {}
}
