"""AWS SNS cryptographic signature verification and safe webhook validation."""
from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
import httpx

logger = logging.getLogger(__name__)

# Strict regex matching official AWS SNS certificate domains
SNS_CERT_HOST_REGEX = re.compile(
    r"^sns\.[a-z0-9\-]+\.amazonaws\.com(?:\.cn)?$",
    re.IGNORECASE,
)

# In-memory certificate cache: cert_url -> (Certificate, expires_at_timestamp)
_CERT_CACHE: Dict[str, Tuple[x509.Certificate, float]] = {}
_MAX_CACHE_ENTRIES = 32
_CACHE_TTL_SECONDS = 3600.0  # 1 hour


class SNSVerificationError(Exception):
    """Base exception for SNS message verification failures."""
    pass


class InvalidSNSSignatureError(SNSVerificationError):
    """Raised when an SNS cryptographic signature fails verification."""
    pass


class UntrustedSNSCertificateURLError(SNSVerificationError):
    """Raised when an SNS SigningCertURL or SubscribeURL points to an untrusted host or scheme."""
    pass


class MalformedSNSPayloadError(SNSVerificationError):
    """Raised when an SNS notification envelope is missing required fields or uses an unsupported format."""
    pass


def is_valid_sns_cert_url(url: str) -> bool:
    """
    Validate that a signing certificate URL points strictly to an official AWS SNS endpoint over HTTPS.
    Guards against SSRF and unauthorized certificate injection.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        if not parsed.hostname or not SNS_CERT_HOST_REGEX.match(parsed.hostname):
            return False
        if parsed.port not in (None, 443):
            return False
        if parsed.username or parsed.password:
            return False
        if not parsed.path or not parsed.path.endswith(".pem"):
            return False
        return True
    except Exception:
        return False


def is_valid_sns_subscribe_url(url: str) -> bool:
    """
    Validate that an SNS SubscribeURL points strictly to an official AWS SNS endpoint over HTTPS.
    Guards against blind GET SSRF during SubscriptionConfirmation handling.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        if not parsed.hostname or not SNS_CERT_HOST_REGEX.match(parsed.hostname):
            return False
        if parsed.port not in (None, 443):
            return False
        if parsed.username or parsed.password:
            return False
        return True
    except Exception:
        return False


def get_sns_canonical_string(payload: Dict[str, Any]) -> str:
    """
    Construct the canonical UTF-8 string to sign from an SNS message envelope
    in accordance with the Amazon SNS message signature specification.
    """
    msg_type = payload.get("Type")
    if not msg_type:
        raise MalformedSNSPayloadError("Missing 'Type' field in SNS payload.")

    lines = []
    if msg_type == "Notification":
        keys = ["Message", "MessageId"]
        if "Subject" in payload and payload["Subject"] is not None:
            keys.append("Subject")
        keys.extend(["Timestamp", "TopicArn", "Type"])
    elif msg_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        keys = ["Message", "MessageId", "SubscribeURL", "Timestamp", "TopicArn", "Token", "Type"]
    else:
        raise MalformedSNSPayloadError(f"Unsupported SNS message type: '{msg_type}'.")

    for key in keys:
        val = payload.get(key)
        if val is None:
            raise MalformedSNSPayloadError(f"Missing required field '{key}' for SNS message type '{msg_type}'.")
        lines.append(f"{key}\n{val}\n")

    return "".join(lines)


async def get_or_fetch_sns_cert(cert_url: str) -> x509.Certificate:
    """
    Retrieve and parse an X.509 certificate for SNS verification with in-memory caching.
    Validates the certificate URL format before attempting retrieval.
    """
    if not is_valid_sns_cert_url(cert_url):
        raise UntrustedSNSCertificateURLError(
            f"SigningCertURL '{cert_url}' is not a valid trusted AWS SNS certificate URL."
        )

    now = time.time()
    cached = _CERT_CACHE.get(cert_url)
    if cached:
        cert, expiry = cached
        if now < expiry:
            return cert

    # Fetch certificate over HTTPS with strict timeout
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(cert_url)
            if resp.status_code != 200:
                raise UntrustedSNSCertificateURLError(
                    f"Failed to fetch SNS signing certificate from '{cert_url}': HTTP {resp.status_code}."
                )
            cert_bytes = resp.content
    except httpx.RequestError as exc:
        raise UntrustedSNSCertificateURLError(
            f"Network error fetching SNS signing certificate from '{cert_url}': {exc}"
        )

    try:
        cert = x509.load_pem_x509_certificate(cert_bytes)
    except Exception as exc:
        raise MalformedSNSPayloadError(f"Invalid PEM certificate content from '{cert_url}': {exc}")

    # Evict if cache exceeds limit
    if len(_CERT_CACHE) >= _MAX_CACHE_ENTRIES:
        oldest_key = min(_CERT_CACHE.keys(), key=lambda k: _CERT_CACHE[k][1])
        _CERT_CACHE.pop(oldest_key, None)

    _CERT_CACHE[cert_url] = (cert, now + _CACHE_TTL_SECONDS)
    return cert


async def verify_sns_message(payload: Dict[str, Any], verify_signature: bool = True) -> bool:
    """
    Verify an incoming AWS SNS message envelope.
    Validates message structure, signing certificate URL, and cryptographic signature.

    Returns True if valid.
    Raises MalformedSNSPayloadError, UntrustedSNSCertificateURLError, or InvalidSNSSignatureError on failure.
    """
    if not isinstance(payload, dict):
        raise MalformedSNSPayloadError("Payload must be a JSON object dictionary.")

    msg_type = payload.get("Type")
    if not msg_type:
        raise MalformedSNSPayloadError("Missing 'Type' field in SNS payload.")

    if not verify_signature:
        # Signature verification bypassed (e.g., local mock tests)
        return True

    sig_version = str(payload.get("SignatureVersion", "")).strip()
    if sig_version not in ("1", "2"):
        raise MalformedSNSPayloadError(
            f"Unsupported SNS SignatureVersion '{sig_version}'. Expected '1' or '2'."
        )

    signature_b64 = payload.get("Signature")
    if not signature_b64 or not isinstance(signature_b64, str):
        raise MalformedSNSPayloadError("Missing or empty 'Signature' field in SNS payload.")

    cert_url = payload.get("SigningCertURL")
    if not cert_url or not isinstance(cert_url, str):
        raise MalformedSNSPayloadError("Missing 'SigningCertURL' field in SNS payload.")

    # 1. Validate cert URL and retrieve certificate
    cert = await get_or_fetch_sns_cert(cert_url)

    # 2. Construct canonical signable string
    canonical_string = get_sns_canonical_string(payload)

    # 3. Decode signature
    try:
        raw_signature = base64.b64decode(signature_b64)
    except Exception as exc:
        raise InvalidSNSSignatureError(f"Malformed base64 signature in SNS payload: {exc}")

    # 4. Determine hash algorithm based on SignatureVersion
    hash_algo = hashes.SHA256() if sig_version == "2" else hashes.SHA1()

    # 5. Cryptographic public key verification
    try:
        pub_key = cert.public_key()
        pub_key.verify(
            raw_signature,
            canonical_string.encode("utf-8"),
            padding.PKCS1v15(),
            hash_algo,
        )
    except Exception as exc:
        raise InvalidSNSSignatureError(f"Cryptographic verification failed for SNS message: {exc}")

    return True


async def confirm_sns_subscription(subscribe_url: str) -> bool:
    """
    Safely confirm an AWS SNS subscription by performing an HTTP GET to SubscribeURL.
    Strictly verifies that SubscribeURL points to an official AWS SNS endpoint over HTTPS.
    """
    if not is_valid_sns_subscribe_url(subscribe_url):
        logger.warning("Rejected untrusted SNS SubscribeURL: %s", subscribe_url)
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(subscribe_url)
            if resp.status_code in (200, 204):
                logger.info("Successfully confirmed SNS subscription via %s", subscribe_url)
                return True
            else:
                logger.warning("SNS SubscribeURL GET returned unexpected status %d", resp.status_code)
                return False
    except Exception as exc:
        logger.error("Failed to confirm SNS subscription via %s: %s", subscribe_url, exc)
        return False
