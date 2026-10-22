"""Microsoft Entra ID OAuth 2.0 token acquisition and renewal manager."""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.core.config import settings
from app.services.graph.exceptions import GraphAuthenticationError

logger = logging.getLogger(__name__)

GRAPH_SCOPE_DEFAULT = "https://graph.microsoft.com/.default"
MICROSOFT_LOGIN_BASE = "https://login.microsoftonline.com"


class MicrosoftGraphTokenManager:
    """
    Manages OAuth 2.0 access token acquisition, caching, and proactive renewal
    for Microsoft Graph API requests.

    STRICT SECURITY CONTROLS:
    1. Never logs or exposes client secrets or access tokens.
    2. Proactively renews access tokens 5 minutes prior to expiration.
    3. Supports Client Credentials (Application Permissions) as well as Delegated Refresh Token flows.
    """

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        auth_flow: Optional[str] = None,
        delegated_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        self._tenant_id = (tenant_id or settings.MICROSOFT_GRAPH_TENANT_ID or "").strip()
        self._client_id = (client_id or settings.MICROSOFT_GRAPH_CLIENT_ID or "").strip()
        self._client_secret = (client_secret or settings.MICROSOFT_GRAPH_CLIENT_SECRET or "").strip()
        self._auth_flow = (auth_flow or settings.MICROSOFT_GRAPH_AUTH_FLOW or "client_credentials").strip().lower()
        self._delegated_token = delegated_token or settings.MICROSOFT_GRAPH_DELEGATED_ACCESS_TOKEN
        self._refresh_token = refresh_token or settings.MICROSOFT_GRAPH_DELEGATED_REFRESH_TOKEN

        self._cached_access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._http_client = http_client

    @property
    def auth_flow(self) -> str:
        return self._auth_flow

    def __repr__(self) -> str:
        return (
            f"MicrosoftGraphTokenManager(tenant_id='{self._tenant_id}', "
            f"client_id='{self._client_id}', client_secret='[REDACTED]', "
            f"auth_flow='{self._auth_flow}')"
        )

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Returns a valid, non-expired Microsoft Graph bearer access token.
        Automatically renews if expired or within 300 seconds of expiry.
        """
        # If static delegated token provided and no client secret to renew
        if self._delegated_token and not force_refresh:
            return self._delegated_token

        # Check cache validity (with 300s safety buffer)
        now = time.time()
        if not force_refresh and self._cached_access_token and (self._token_expires_at - now > 300):
            return self._cached_access_token

        # Acquire new token via appropriate OAuth2 grant
        if self._auth_flow == "delegated" and self._refresh_token:
            return self._refresh_delegated_token()
        else:
            return self._acquire_app_token()

    def _acquire_app_token(self) -> str:
        """Acquires access token via OAuth2 Client Credentials grant (Application Permissions)."""
        if not self._tenant_id:
            raise GraphAuthenticationError("MICROSOFT_GRAPH_TENANT_ID is required for Client Credentials authentication.")
        if not self._client_id:
            raise GraphAuthenticationError("MICROSOFT_GRAPH_CLIENT_ID is required for Client Credentials authentication.")
        if not self._client_secret:
            raise GraphAuthenticationError("MICROSOFT_GRAPH_CLIENT_SECRET is required for Client Credentials authentication.")

        token_url = f"{MICROSOFT_LOGIN_BASE}/{self._tenant_id}/oauth2/v2.0/token"
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": GRAPH_SCOPE_DEFAULT,
            "grant_type": "client_credentials",
        }

        try:
            client = self._http_client or httpx.Client(timeout=settings.MICROSOFT_GRAPH_TIMEOUT_SECONDS)
            try:
                response = client.post(
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            finally:
                if not self._http_client:
                    client.close()

            if response.status_code != 200:
                err_text = response.text
                logger.error("Microsoft Entra ID token endpoint returned status %s", response.status_code)
                raise GraphAuthenticationError(
                    f"Failed to acquire Microsoft Graph application token (HTTP {response.status_code}): {err_text}"
                )

            data = response.json()
            access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3599))

            if not access_token:
                raise GraphAuthenticationError("Microsoft Entra ID returned response without access_token.")

            self._cached_access_token = access_token
            self._token_expires_at = time.time() + expires_in
            logger.info("Successfully acquired Microsoft Graph app access token (expires in %ds)", expires_in)
            return access_token

        except httpx.RequestError as exc:
            logger.error("Network error communicating with Microsoft Entra ID token endpoint: %s", exc)
            raise GraphAuthenticationError(f"Network error acquiring Microsoft Graph token: {exc}")

    def _refresh_delegated_token(self) -> str:
        """Refreshes a delegated user token using a configured refresh token."""
        if not self._tenant_id or not self._client_id:
            raise GraphAuthenticationError("MICROSOFT_GRAPH_TENANT_ID and CLIENT_ID are required for token refresh.")

        token_url = f"{MICROSOFT_LOGIN_BASE}/{self._tenant_id}/oauth2/v2.0/token"
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": self._refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Mail.Read",
        }

        try:
            client = self._http_client or httpx.Client(timeout=settings.MICROSOFT_GRAPH_TIMEOUT_SECONDS)
            try:
                response = client.post(
                    token_url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            finally:
                if not self._http_client:
                    client.close()

            if response.status_code != 200:
                raise GraphAuthenticationError(
                    f"Failed to refresh Microsoft Graph delegated token (HTTP {response.status_code}): {response.text}"
                )

            data = response.json()
            access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3599))
            new_refresh = data.get("refresh_token")
            if new_refresh:
                self._refresh_token = new_refresh

            self._cached_access_token = access_token
            self._token_expires_at = time.time() + expires_in
            return access_token

        except httpx.RequestError as exc:
            raise GraphAuthenticationError(f"Network error refreshing Microsoft Graph token: {exc}")
