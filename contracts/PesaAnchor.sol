// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PesaAnchor
 * @notice Stores Merkle roots of M-Pesa transaction hashes for public
 *         verifiability. Transaction data stays local and private — only a
 *         cryptographic fingerprint is published on-chain.
 *
 * Deploy once to Polygon PoS (chainId 137). Store the deployed address
 * in your .env as CONTRACT_ADDRESS.
 *
 * anchor(bytes32)  — called by the Python backend to publish a root
 * verify(bytes32)  — anyone can check if a root was anchored
 * anchors[root]    — returns the block number (0 = not anchored)
 *
 * Estimated gas: ~25,000 gas per anchor ≈ $0.001 on Polygon
 */
contract PesaAnchor {

    // ── Storage ───────────────────────────────────────────────────────────

    mapping(bytes32 => uint256) public anchors;  // root → block number
    bytes32[] public anchorHistory;
    address public owner;

    // ── Events ────────────────────────────────────────────────────────────

    event Anchored(bytes32 indexed merkleRoot, uint256 blockNumber, uint256 indexed anchorIndex);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    // ── Errors ────────────────────────────────────────────────────────────

    error NotOwner();
    error ZeroRoot();
    error AlreadyAnchored(bytes32 root, uint256 blockNumber);

    // ── Constructor ───────────────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    // ── Write ─────────────────────────────────────────────────────────────

    /**
     * @notice Anchor a Merkle root on-chain.
     * @param merkleRoot  32-byte SHA-256 Merkle root from the Python backend.
     */
    function anchor(bytes32 merkleRoot) external onlyOwner {
        if (merkleRoot == bytes32(0)) revert ZeroRoot();
        if (anchors[merkleRoot] != 0) revert AlreadyAnchored(merkleRoot, anchors[merkleRoot]);

        anchors[merkleRoot] = block.number;
        anchorHistory.push(merkleRoot);

        emit Anchored(merkleRoot, block.number, anchorHistory.length - 1);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "PesaAnchor: zero address");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    // ── Read ──────────────────────────────────────────────────────────────

    /// @notice Returns true if the root was previously anchored.
    function verify(bytes32 merkleRoot) external view returns (bool) {
        return anchors[merkleRoot] != 0;
    }

    /// @notice Total number of anchors submitted.
    function anchorCount() external view returns (uint256) {
        return anchorHistory.length;
    }

    /// @notice Returns the most recent N roots and their block numbers.
    function recentAnchors(uint256 n)
        external
        view
        returns (bytes32[] memory roots, uint256[] memory blockNumbers)
    {
        uint256 total = anchorHistory.length;
        uint256 count = n > total ? total : n;
        roots = new bytes32[](count);
        blockNumbers = new uint256[](count);
        for (uint256 i = 0; i < count; i++) {
            bytes32 root = anchorHistory[total - count + i];
            roots[i] = root;
            blockNumbers[i] = anchors[root];
        }
    }
}