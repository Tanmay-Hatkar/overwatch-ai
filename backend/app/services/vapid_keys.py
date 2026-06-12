"""
vapid_keys.py — Derive the VAPID public key from the private key.

VAPID uses an EC P-256 keypair. The public key is mathematically derivable
from the private key, so we never need to *configure* the public key
separately — we compute it. This makes push resilient: the private key
(the one real secret, in env) is the single source of truth, and the
public key served to browsers is always guaranteed to match it.

This permanently sidesteps the class of bug where a stale/wrong
VAPID_PUBLIC_KEY env var gets out of sync with the private key.
"""

import base64
import logging

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger(__name__)


def derive_vapid_public_key(private_key_b64url: str) -> str | None:
    """
    Compute the base64url VAPID public key from a base64url private key.

    Args:
        private_key_b64url: The VAPID private key (base64url, 32-byte P-256
            scalar) — typically settings.vapid_private_key.

    Returns:
        The 87-char base64url public key (uncompressed EC point), or None if
        the private key is empty or can't be parsed (so the caller can 503).
    """
    if not private_key_b64url:
        return None
    try:
        padding = "=" * (-len(private_key_b64url) % 4)
        raw = base64.urlsafe_b64decode(private_key_b64url + padding)
        private_value = int.from_bytes(raw, "big")
        private_key = ec.derive_private_key(private_value, ec.SECP256R1())
        point = private_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )  # 65 bytes, 0x04-prefixed uncompressed point
        return base64.urlsafe_b64encode(point).rstrip(b"=").decode("ascii")
    except (ValueError, TypeError):
        logger.exception("Failed to derive VAPID public key from private key")
        return None
