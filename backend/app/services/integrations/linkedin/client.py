"""LinkedIn OAuth 2.0 and OpenID Connect client for token exchange and identity verification."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class LinkedInOAuthClient:
    """
    Client for interacting with LinkedIn's OAuth 2.0 authorization-code flow
    and OpenID Connect endpoints.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        auth_url: Optional[str] = None,
        token_url: Optional[str] = None,
        jwks_url: Optional[str] = None,
        userinfo_url: Optional[str] = None,
        timeout: Optional[float] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        jwks_client: Optional[PyJWKClient] = None,
    ) -> None:
        self.client_id = (client_id or settings.LINKEDIN_CLIENT_ID or "").strip()
        self.client_secret = (client_secret or settings.LINKEDIN_CLIENT_SECRET or "").strip()
        self.redirect_uri = (redirect_uri or settings.LINKEDIN_REDIRECT_URI).strip()
        self.auth_url = auth_url or settings.LINKEDIN_AUTH_URL
        self.token_url = token_url or settings.LINKEDIN_TOKEN_URL
        self.jwks_url = jwks_url or settings.LINKEDIN_JWKS_URL
        self.userinfo_url = userinfo_url or settings.LINKEDIN_USERINFO_URL
        self.timeout = timeout or settings.LINKEDIN_TIMEOUT_SECONDS
        self._http_client = http_client
        self._jwks_client = jwks_client

    def is_configured(self) -> bool:
        """Check if client ID and secret are populated."""
        return bool(self.client_id and self.client_secret)

    def get_authorization_url(self, state: str, nonce: Optional[str] = None) -> str:
        """
        Generate the LinkedIn OAuth 2.0 authorization redirect URL.
        Includes response_type=code, client_id, redirect_uri, state, and scopes.
        """
        if not self.client_id:
            raise ValueError("LinkedIn client ID is not configured.")

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": settings.LINKEDIN_SCOPES,
        }
        if nonce:
            params["nonce"] = nonce

        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange an authorization code securely for access token and ID token.
        Never logs authorization codes, client secrets, or returned tokens.
        """
        if not self.is_configured():
            raise ValueError("LinkedIn OAuth credentials are not configured on the backend.")

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        async def _do_post(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                self.token_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )

        if self._http_client:
            resp = await _do_post(self._http_client)
        else:
            async with httpx.AsyncClient() as client:
                resp = await _do_post(client)

        if resp.status_code != 200:
            error_data = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {}
            err_code = error_data.get("error", f"http_{resp.status_code}")
            err_desc = error_data.get("error_description", resp.text[:200])
            logger.warning(
                "LinkedIn authorization code exchange failed with status %d: %s",
                resp.status_code,
                err_code,
            )
            raise ValueError(f"LinkedIn token exchange failed: {err_code} - {err_desc}")

        data = resp.json()
        if "access_token" not in data:
            logger.error("LinkedIn token exchange response missing 'access_token'.")
            raise ValueError("LinkedIn token exchange failed: missing access_token in response.")

        return data

    def _get_jwks_client(self) -> PyJWKClient:
        """Get or initialize the cached PyJWKClient for LinkedIn JWKS."""
        if not self._jwks_client:
            self._jwks_client = PyJWKClient(self.jwks_url, cache_jwk_set=True, lifespan=3600)
        return self._jwks_client

    async def validate_id_token(
        self,
        id_token: str,
        nonce: Optional[str] = None,
        signing_key_override: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Validate an OpenID Connect ID token using LinkedIn's JWKS.
        Verifies RS256 signature, issuer ('https://www.linkedin.com'),
        audience (client_id), expiration, and optional nonce.
        """
        if not id_token or not id_token.strip():
            raise ValueError("ID token cannot be empty.")

        try:
            if signing_key_override is not None:
                key = signing_key_override
            else:
                jwks = self._get_jwks_client()
                signing_key = jwks.get_signing_key_from_jwt(id_token)
                key = signing_key.key

            payload = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id if self.client_id else None,
                issuer="https://www.linkedin.com",
                options={
                    "require": ["sub", "iss", "aud", "exp"],
                    "verify_aud": bool(self.client_id),
                    "verify_iss": True,
                    "verify_exp": True,
                },
            )

            if nonce and payload.get("nonce") and payload.get("nonce") != nonce:
                logger.warning("ID token nonce mismatch.")
                raise ValueError("ID token nonce does not match the authorization request.")

            return payload

        except jwt.ExpiredSignatureError as exc:
            logger.warning("LinkedIn ID token has expired.")
            raise ValueError("ID token has expired.") from exc
        except jwt.InvalidAudienceError as exc:
            logger.warning("LinkedIn ID token audience mismatch.")
            raise ValueError("ID token audience mismatch.") from exc
        except jwt.InvalidIssuerError as exc:
            logger.warning("LinkedIn ID token issuer mismatch.")
            raise ValueError("ID token issuer mismatch.") from exc
        except jwt.InvalidSignatureError as exc:
            logger.warning("LinkedIn ID token signature verification failed.")
            raise ValueError("ID token signature verification failed.") from exc
        except Exception as exc:
            logger.warning("LinkedIn ID token validation failed: %s", type(exc).__name__)
            raise ValueError(f"ID token validation failed: {exc}") from exc

    async def get_userinfo(self, access_token: str) -> Dict[str, Any]:
        """
        Retrieve member identity details from the OpenID Connect userinfo endpoint.
        Used to extract or enrich member profile info (name, email, picture).
        """
        if not access_token or not access_token.strip():
            raise ValueError("Access token is required for userinfo retrieval.")

        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Accept": "application/json",
        }

        async def _do_get(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(self.userinfo_url, headers=headers, timeout=self.timeout)

        if self._http_client:
            resp = await _do_get(self._http_client)
        else:
            async with httpx.AsyncClient() as client:
                resp = await _do_get(client)

        if resp.status_code != 200:
            logger.warning("LinkedIn userinfo retrieval returned status %d", resp.status_code)
            raise ValueError(f"Failed to fetch LinkedIn userinfo: HTTP {resp.status_code}")

        return resp.json()
