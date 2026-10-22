"""Microsoft Graph REST API client for support mailbox message reading."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, urlparse

import httpx

from app.core.config import settings
from app.services.graph.auth import MicrosoftGraphTokenManager
from app.services.graph.exceptions import (
    GraphAPIError,
    GraphAuthenticationError,
    GraphDeltaTokenExpiredError,
    GraphMailboxNotFoundError,
    GraphMailboxScopeError,
    GraphPermissionError,
    GraphSecurityError,
    GraphThrottlingError,
)

logger = logging.getLogger(__name__)


@dataclass
class GraphMessage:
    """Parsed message object retrieved from Microsoft Graph."""
    id: str
    conversation_id: Optional[str]
    internet_message_id: Optional[str]
    subject: Optional[str]
    body_preview: Optional[str]
    body_content: Optional[str]
    body_content_type: str
    received_at: datetime
    is_read: bool
    has_attachments: bool
    from_email: str
    from_name: Optional[str]
    to_recipients: List[str]
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def sender_email(self) -> str:
        return self.from_email

    @property
    def sender_name(self) -> Optional[str]:
        return self.from_name

    @property
    def recipient_email(self) -> str:
        return self.to_recipients[0] if self.to_recipients else ""


@dataclass
class GraphMessagePage:
    """Page of messages with optional next-page link."""
    messages: List[GraphMessage]
    next_link: Optional[str] = None
    delta_link: Optional[str] = None


@dataclass
class DeltaQueryResult:
    """
    Result of a Microsoft Graph delta query.
    Implements 2-tuple unpacking (messages, delta_link) for backward compatibility
    while exposing `is_complete` to distinguish a terminal @odata.deltaLink from
    an intermediate continuation @odata.nextLink.
    """
    messages: List[GraphMessage]
    delta_link: Optional[str] = None
    is_complete: bool = True

    def __iter__(self):
        return iter((self.messages, self.delta_link))

    def __getitem__(self, item):
        return (self.messages, self.delta_link)[item]

    def __len__(self):
        return 2


class MicrosoftGraphClient:
    """
    Client for interacting with the Microsoft Graph REST API to read inbound emails
    from the approved support mailbox.

    STRICT SAFETY GUARANTEES:
    1. Scoped strictly to the approved support mailbox (e.g. support@agilereceivables.com).
       Rejects attempts to access other mailboxes to enforce least privilege.
    2. Read-only: Does NOT execute delete, patch, or send requests against the mailbox.
    3. Handles Graph rate limits (HTTP 429) using Retry-After backoff.
    4. Distinguishes authentication (401), permission (403), and missing mailbox (404) errors.
    """

    def __init__(
        self,
        token_manager: Optional[MicrosoftGraphTokenManager] = None,
        http_client: Optional[httpx.Client] = None,
        approved_mailbox: Optional[str] = None,
        base_url: Optional[str] = None,
        max_retries: int = 3,
    ):
        self._token_manager = token_manager or MicrosoftGraphTokenManager()
        self._http_client = http_client
        self._approved_mailbox = (
            approved_mailbox or settings.MICROSOFT_GRAPH_SUPPORT_MAILBOX
        ).strip().lower()
        self._base_url = (base_url or settings.MICROSOFT_GRAPH_BASE_URL).rstrip("/")
        self._max_retries = max_retries

    @property
    def approved_mailbox(self) -> str:
        return self._approved_mailbox

    def _verify_mailbox_scope(self, mailbox: Optional[str]) -> str:
        """Enforces that only the explicitly approved support mailbox can be queried."""
        target = (mailbox or self._approved_mailbox).strip().lower()
        if target != self._approved_mailbox:
            raise GraphMailboxScopeError(
                f"Unauthorized mailbox '{target}'. Access is strictly restricted to the "
                f"approved support mailbox '{self._approved_mailbox}'."
            )
        return target

    def _validate_graph_url(self, url: str, expected_folder: Optional[str] = "inbox") -> str:
        """
        Validates Microsoft Graph URLs to prevent SSRF and cross-tenant / cross-mailbox access.

        STRICT CRITERIA:
        1. Scheme must be HTTPS.
        2. Host must be exactly graph.microsoft.com.
        3. Port must be 443 or default (None). User credentials in URL are strictly prohibited.
        4. Path must start with /v1.0/users/{approved_mailbox} (or /beta/).
        5. If expected_folder is specified, mailFolders segment must match expected_folder.
        """
        if not url or not isinstance(url, str):
            raise GraphSecurityError("Graph URL cannot be empty.")

        try:
            parsed = urlparse(url)
        except Exception as exc:
            raise GraphSecurityError(f"Malformed Microsoft Graph URL: {exc}")

        if parsed.scheme.lower() != "https":
            raise GraphSecurityError(
                f"Insecure scheme '{parsed.scheme}' in Graph URL. HTTPS is strictly required."
            )

        hostname = (parsed.hostname or "").lower()
        if hostname != "graph.microsoft.com":
            raise GraphSecurityError(
                f"Untrusted host '{hostname}' in Graph URL. Expected 'graph.microsoft.com'."
            )

        if parsed.port not in (None, 443):
            raise GraphSecurityError(
                f"Non-standard port '{parsed.port}' in Graph URL. Port 443 is required."
            )

        if parsed.username or parsed.password:
            raise GraphSecurityError("User credentials in Graph URL are strictly prohibited.")

        # Path validation: /v1.0/users/{mailbox}/...
        path_segments = [s for s in parsed.path.strip("/").split("/") if s]
        if len(path_segments) < 3:
            raise GraphSecurityError(f"Incomplete Graph URL path '{parsed.path}'.")

        version, entity_type, mailbox_segment = path_segments[0], path_segments[1], path_segments[2]

        if version.lower() not in ("v1.0", "beta"):
            raise GraphSecurityError(f"Unsupported Graph API version '{version}'.")

        if entity_type.lower() != "users":
            raise GraphSecurityError(f"Expected '/users/' endpoint in Graph URL, got '/{entity_type}/'.")

        unquoted_mailbox = unquote(mailbox_segment).strip().lower()
        if unquoted_mailbox != self._approved_mailbox:
            raise GraphMailboxScopeError(
                f"Unauthorized mailbox '{unquoted_mailbox}' in Graph URL. "
                f"Strictly restricted to approved mailbox '{self._approved_mailbox}'."
            )

        if expected_folder:
            folder_clean = expected_folder.strip().lower()
            if len(path_segments) >= 5 and path_segments[3].lower() == "mailfolders":
                actual_folder = unquote(path_segments[4]).strip().lower()
                if actual_folder != folder_clean:
                    raise GraphSecurityError(
                        f"Unauthorized folder '{actual_folder}' in Graph URL. "
                        f"Expected folder '{folder_clean}'."
                    )
            else:
                raise GraphSecurityError(
                    f"Graph URL path '{parsed.path}' is missing required mailFolders segment for folder '{folder_clean}'."
                )

        return url

    def _execute_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Executes HTTP request against Microsoft Graph with token renewal, redirect rejection, and 429 throttling backoff."""
        attempt = 0
        while attempt < self._max_retries:
            token = self._token_manager.get_access_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            client = self._http_client or httpx.Client(
                timeout=settings.MICROSOFT_GRAPH_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
            try:
                response = client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    follow_redirects=False,
                )
            except httpx.RequestError as exc:
                if not self._http_client:
                    client.close()
                raise GraphAPIError(f"Network error calling Microsoft Graph: {exc}")

            if not self._http_client:
                client.close()

            # Reject redirects (SSRF mitigation)
            if response.is_redirect or (300 <= response.status_code < 400):
                redirect_target = response.headers.get("Location", "")
                raise GraphSecurityError(
                    f"Microsoft Graph request was redirected (HTTP {response.status_code}) to '{redirect_target}'. "
                    "HTTP redirects are strictly prohibited for Microsoft Graph requests."
                )

            # Handle throttling (429)
            if response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After")
                retry_after = int(retry_after_header) if retry_after_header and retry_after_header.isdigit() else (2 ** attempt)
                logger.warning(
                    "Microsoft Graph rate limit reached (HTTP 429). Retrying after %d seconds (attempt %d/%d)...",
                    retry_after,
                    attempt + 1,
                    self._max_retries,
                )
                if attempt + 1 >= self._max_retries:
                    raise GraphThrottlingError(
                        f"Microsoft Graph throttled request after {self._max_retries} attempts.",
                        retry_after=retry_after,
                    )
                time.sleep(retry_after)
                attempt += 1
                continue

            # Handle expired token (401)
            if response.status_code == 401 and attempt == 0:
                logger.info("Microsoft Graph returned 401 Unauthorized. Forcing token refresh and retrying...")
                self._token_manager.get_access_token(force_refresh=True)
                attempt += 1
                continue

            # Handle Forbidden (403)
            if response.status_code == 403:
                raise GraphPermissionError(
                    "Microsoft Graph access denied (HTTP 403). Check that Entra ID has granted "
                    "Mail.Read (Application) or Mail.Read.Shared (Delegated) permissions."
                )

            # Handle Not Found (404)
            if response.status_code == 404:
                raise GraphMailboxNotFoundError(
                    f"Target mailbox or folder not found in Microsoft 365 Exchange Online (HTTP 404)."
                )

            # Handle Delta Token Expired (410 Gone)
            if response.status_code == 410:
                raise GraphDeltaTokenExpiredError(
                    "Microsoft Graph delta token has expired (HTTP 410 Gone). "
                    "Full resynchronization checkpoint required."
                )

            # Handle other client/server errors
            if response.status_code >= 400:
                try:
                    err_json = response.json().get("error", {})
                    code = err_json.get("code")
                    msg = err_json.get("message")
                except Exception:
                    code = None
                    msg = response.text

                # Microsoft Graph error codes indicating delta token expiration or invalidation
                if code in ("resyncRequired", "SyncStateNotFound"):
                    raise GraphDeltaTokenExpiredError(
                        f"Microsoft Graph delta token has expired or is invalid ({code}). "
                        "Full resynchronization checkpoint required."
                    )

                raise GraphAPIError(
                    f"Microsoft Graph API error (HTTP {response.status_code}): {msg}",
                    status_code=response.status_code,
                    error_code=code,
                )

            return response

        raise GraphAPIError("Exhausted retries calling Microsoft Graph.")

    def get_messages(
        self,
        mailbox: Optional[str] = None,
        folder: str = "Inbox",
        top: int = 50,
        skip_token: Optional[str] = None,
        next_link: Optional[str] = None,
    ) -> GraphMessagePage:
        """
        Reads messages from the approved support mailbox.
        Supports pagination via next_link or $skip token.
        Fetches full message body and headers required for complete inbound email reading.
        """
        target_mailbox = self._verify_mailbox_scope(mailbox)
        encoded_mailbox = quote(target_mailbox)
        folder_clean = folder.strip()

        if next_link:
            self._validate_graph_url(next_link, expected_folder=folder_clean)
            url = next_link
            params = None
        else:
            folder_clean_encoded = quote(folder_clean)
            url = f"{self._base_url}/users/{encoded_mailbox}/mailFolders/{folder_clean_encoded}/messages"
            self._validate_graph_url(url, expected_folder=folder_clean)
            params = {
                "$select": (
                    "id,conversationId,internetMessageId,subject,bodyPreview,body,"
                    "receivedDateTime,hasAttachments,from,toRecipients,isRead,importance"
                ),
                "$top": min(max(top, 1), 250),
                "$orderby": "receivedDateTime desc",
            }
            if skip_token:
                params["$skip"] = skip_token

        response = self._execute_request("GET", url, params=params)
        data = response.json()

        raw_messages = data.get("value", [])
        parsed_messages: List[GraphMessage] = []

        for item in raw_messages:
            parsed = self._parse_graph_message(item)
            if parsed:
                parsed_messages.append(parsed)

        next_link_out = data.get("@odata.nextLink")
        if next_link_out:
            self._validate_graph_url(next_link_out, expected_folder=folder_clean)

        delta_link_out = data.get("@odata.deltaLink")
        if delta_link_out:
            self._validate_graph_url(delta_link_out, expected_folder=folder_clean)

        return GraphMessagePage(
            messages=parsed_messages,
            next_link=next_link_out,
            delta_link=delta_link_out,
        )

    def get_next_page(self, next_link: str) -> GraphMessagePage:
        """Convenience method to retrieve the subsequent page using an @odata.nextLink URL."""
        return self.get_messages(next_link=next_link)

    def get_delta_messages(
        self,
        mailbox: Optional[str] = None,
        folder: str = "Inbox",
        delta_link: Optional[str] = None,
        max_pages: int = 20,
        max_messages: Optional[int] = None,
    ) -> DeltaQueryResult:
        """
        Retrieves messages incrementally using Microsoft Graph Delta Query.
        Follows @odata.nextLink until the final page, returning a DeltaQueryResult
        (which behaves as a 2-tuple (messages, delta_link) for backward compatibility,
        while exposing `is_complete`).
        
        If delta_link is provided, queries changes or resumes from that checkpoint.
        If delta_link has expired (HTTP 410 or resyncRequired), automatically recovers
        by initiating a fresh full delta sync.
        """
        target_mailbox = self._verify_mailbox_scope(mailbox)
        encoded_mailbox = quote(target_mailbox)
        folder_clean = folder.strip()

        if delta_link:
            self._validate_graph_url(delta_link, expected_folder=folder_clean)

        try:
            return self._fetch_delta_pages(
                encoded_mailbox=encoded_mailbox,
                folder_clean=folder_clean,
                delta_link=delta_link,
                max_pages=max_pages,
                max_messages=max_messages,
            )
        except GraphDeltaTokenExpiredError:
            logger.warning(
                "Delta link expired for mailbox %s. Resetting delta link and initiating fresh delta query.",
                target_mailbox,
            )
            return self._fetch_delta_pages(
                encoded_mailbox=encoded_mailbox,
                folder_clean=folder_clean,
                delta_link=None,
                max_pages=max_pages,
                max_messages=max_messages,
            )

    def _fetch_delta_pages(
        self,
        encoded_mailbox: str,
        folder_clean: str,
        delta_link: Optional[str],
        max_pages: int,
        max_messages: Optional[int] = None,
    ) -> DeltaQueryResult:
        if delta_link:
            self._validate_graph_url(delta_link, expected_folder=folder_clean)
            current_url: Optional[str] = delta_link
            params: Optional[Dict[str, Any]] = None
        else:
            folder_clean_encoded = quote(folder_clean)
            current_url = f"{self._base_url}/users/{encoded_mailbox}/mailFolders/{folder_clean_encoded}/messages/delta"
            self._validate_graph_url(current_url, expected_folder=folder_clean)
            params = {
                "$select": (
                    "id,conversationId,internetMessageId,subject,bodyPreview,body,"
                    "receivedDateTime,hasAttachments,from,toRecipients,isRead,importance"
                ),
                "$top": min(max(settings.MICROSOFT_GRAPH_MAX_MESSAGES_PER_PAGE, 1), 250),
            }

        all_messages: List[GraphMessage] = []
        safe_checkpoint: Optional[str] = delta_link
        new_continuation_link: Optional[str] = None
        is_complete = False
        pages_fetched = 0

        while current_url and pages_fetched < max_pages:
            self._validate_graph_url(current_url, expected_folder=folder_clean)
            response = self._execute_request("GET", current_url, params=params)
            data = response.json()
            raw_items = data.get("value", [])

            parsed_page_messages: List[GraphMessage] = []
            for item in raw_items:
                # Microsoft Graph delta can return deleted items with '@removed' property
                if "@removed" in item:
                    continue
                parsed = self._parse_graph_message(item)
                if parsed:
                    parsed_page_messages.append(parsed)

            # Check message limit
            if max_messages is not None:
                remaining_budget = max_messages - len(all_messages)
                if remaining_budget <= 0:
                    new_continuation_link = safe_checkpoint
                    is_complete = False
                    break
                elif len(parsed_page_messages) > remaining_budget:
                    # Partial page consumption:
                    # Ingest only up to remaining budget.
                    # CRITICAL: Do NOT advance the durable checkpoint past unprocessed messages on this page.
                    # Retain safe_checkpoint so subsequent runs resume and process remaining messages.
                    all_messages.extend(parsed_page_messages[:remaining_budget])
                    new_continuation_link = safe_checkpoint
                    is_complete = False
                    break
                else:
                    all_messages.extend(parsed_page_messages)
            else:
                all_messages.extend(parsed_page_messages)

            pages_fetched += 1

            # Check next link vs delta link
            next_link = data.get("@odata.nextLink")
            delta_link_candidate = data.get("@odata.deltaLink")

            if next_link:
                self._validate_graph_url(next_link, expected_folder=folder_clean)
                safe_checkpoint = next_link
                current_url = next_link
                params = None  # query params already encoded in nextLink

                if (max_messages is not None and len(all_messages) >= max_messages) or pages_fetched >= max_pages:
                    new_continuation_link = safe_checkpoint
                    is_complete = False
                    break
            else:
                if delta_link_candidate:
                    self._validate_graph_url(delta_link_candidate, expected_folder=folder_clean)
                safe_checkpoint = delta_link_candidate
                new_continuation_link = safe_checkpoint
                is_complete = True
                break

        return DeltaQueryResult(
            messages=all_messages,
            delta_link=new_continuation_link,
            is_complete=is_complete,
        )

    def get_message(self, message_id: str, mailbox: Optional[str] = None) -> GraphMessage:
        """Retrieves an individual message by its Graph Message ID."""
        target_mailbox = self._verify_mailbox_scope(mailbox)
        encoded_mailbox = quote(target_mailbox)
        encoded_msg_id = quote(message_id)

        url = f"{self._base_url}/users/{encoded_mailbox}/messages/{encoded_msg_id}"
        self._validate_graph_url(url, expected_folder=None)
        params = {
            "$select": (
                "id,conversationId,internetMessageId,subject,bodyPreview,body,"
                "receivedDateTime,hasAttachments,from,toRecipients,isRead,importance"
            )
        }

        response = self._execute_request("GET", url, params=params)
        data = response.json()
        parsed = self._parse_graph_message(data)
        if not parsed:
            raise GraphAPIError(f"Failed to parse Microsoft Graph message '{message_id}'.")
        return parsed

    def _parse_graph_message(self, item: Dict[str, Any]) -> Optional[GraphMessage]:
        """Safely parses raw Microsoft Graph message payload into typed GraphMessage."""
        msg_id = item.get("id")
        if not msg_id:
            return None

        # Sender extraction
        from_data = item.get("from") or {}
        email_addr = from_data.get("emailAddress") or {}
        from_email = (email_addr.get("address") or "").strip().lower()
        from_name = email_addr.get("name")

        # To recipients extraction
        to_recipients: List[str] = []
        for r in item.get("toRecipients", []):
            addr = (r.get("emailAddress", {}).get("address") or "").strip().lower()
            if addr:
                to_recipients.append(addr)

        # Body extraction
        body_obj = item.get("body") or {}
        body_content = body_obj.get("content")
        body_content_type = (body_obj.get("contentType") or "html").lower()

        # Timestamp parsing
        received_str = item.get("receivedDateTime")
        if received_str:
            try:
                # e.g. "2026-10-21T12:00:00Z"
                received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
            except Exception:
                received_at = datetime.now(timezone.utc)
        else:
            received_at = datetime.now(timezone.utc)

        return GraphMessage(
            id=msg_id,
            conversation_id=item.get("conversationId"),
            internet_message_id=item.get("internetMessageId"),
            subject=item.get("subject"),
            body_preview=item.get("bodyPreview"),
            body_content=body_content,
            body_content_type=body_content_type,
            received_at=received_at,
            is_read=bool(item.get("isRead", False)),
            has_attachments=bool(item.get("hasAttachments", False)),
            from_email=from_email,
            from_name=from_name,
            to_recipients=to_recipients,
            raw_data=item,
        )
