"""
Microsoft Graph Integration Service Package.

Provides client, token management, ingestion, and sync services for
inbound email processing from the approved Agile Receivables support mailbox.
"""

from app.services.graph.exceptions import (
    GraphAPIError,
    GraphAuthenticationError,
    GraphDeltaTokenExpiredError,
    GraphMailboxNotFoundError,
    GraphMailboxScopeError,
    GraphPermissionError,
    GraphThrottlingError,
)
from app.services.graph.auth import MicrosoftGraphTokenManager
from app.services.graph.client import DeltaQueryResult, MicrosoftGraphClient
from app.services.graph.ingestion_service import (
    IngestionSummary,
    import_graph_messages,
    match_sender_to_crm,
    sanitize_body_preview,
)
from app.services.graph.sync_service import (
    acquire_sync_lock,
    get_checkpoint_status,
    get_inbound_email_detail,
    get_or_create_checkpoint,
    list_inbound_emails,
    list_sync_runs,
    release_sync_lock,
    sync_support_mailbox,
    update_manual_review_status,
)

__all__ = [
    "GraphAPIError",
    "GraphAuthenticationError",
    "GraphDeltaTokenExpiredError",
    "GraphPermissionError",
    "GraphThrottlingError",
    "GraphMailboxNotFoundError",
    "GraphMailboxScopeError",
    "MicrosoftGraphTokenManager",
    "MicrosoftGraphClient",
    "DeltaQueryResult",
    "IngestionSummary",
    "import_graph_messages",
    "match_sender_to_crm",
    "sanitize_body_preview",
    "sync_support_mailbox",
    "list_inbound_emails",
    "get_inbound_email_detail",
    "update_manual_review_status",
    "list_sync_runs",
    "get_or_create_checkpoint",
    "acquire_sync_lock",
    "release_sync_lock",
    "get_checkpoint_status",
]
