"""
Centralized key hashing utilities for VedaCore.

Provides secure, policy-friendly alternatives to MD5 for cache keys
and internal identifiers. Uses BLAKE2b for speed and SHA-256 for
maximum compatibility.
"""

from hashlib import blake2b, sha256


def key_digest(data: str | bytes, short: int = 16, fast: bool = True) -> str:
    """
    Generate deterministic digest for cache keys and identifiers.

    Args:
        data: Input string or bytes to hash
        short: Number of hex characters to return (default 16 for compact paths)
        fast: If True, uses BLAKE2b (fast & secure); otherwise SHA-256

    Returns:
        Hex digest string of specified length

    Examples:
        >>> key_digest("test_key")
        '7d865e959b2466918c9863afca942d0f'

        >>> key_digest("test_key", short=8)
        '7d865e95'

        >>> key_digest("test_key", fast=False)  # Uses SHA-256
        'e3b0c44298fc1c14'
    """
    b = data.encode() if isinstance(data, str) else data

    if fast:
        # BLAKE2b: Fast, secure, and modern
        digest = blake2b(b, digest_size=32).hexdigest()
    else:
        # SHA-256: Maximum compatibility for corporate environments
        digest = sha256(b).hexdigest()

    return digest[:short]


def cache_key_hash(key_str: str) -> str:
    """
    Generate cache key hash compatible with existing VedaCore patterns.

    Args:
        key_str: Cache key string to hash

    Returns:
        16-character hex hash suitable for file paths
    """
    return key_digest(key_str, short=16, fast=True)


def context_hash(context_yaml: str) -> str:
    """
    Generate context hash for ATS and similar components.

    Args:
        context_yaml: YAML context string

    Returns:
        8-character hex hash for compact identification
    """
    return key_digest(context_yaml, short=8, fast=True)


def analysis_id_hash(id_str: str) -> str:
    """
    Generate analysis ID hash for facade components.

    Args:
        id_str: Analysis identifier string

    Returns:
        16-character hex hash for analysis tracking
    """
    return key_digest(id_str, short=16, fast=True)
