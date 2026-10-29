"""LinkedIn Integration Service orchestrating OAuth authorization, replay protection, token encryption, and member identity lifecycle."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.linkedin import LinkedInConnection, LinkedInOAuthState
from app.models.tenant import Organization, User
from app.services.integrations.linkedin.client import LinkedInOAuthClient
from app.services.integrations.linkedin.encryption import encrypt_token

logger = logging.getLogger(__name__)

# State expiration TTL in minutes (15 minutes)
OAUTH_STATE_TTL_MINUTES = 15


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime to timezone-aware UTC across SQLite and PostgreSQL."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class LinkedInIntegrationService:
    """
    Manages LinkedIn OAuth state lifecycle, token exchange, OpenID Connect identity verification,
    encrypted persistence, and tenant-isolated disconnects.
    """

    def __init__(
        self,
        db: Session,
        client: Optional[LinkedInOAuthClient] = None,
    ) -> None:
        self.db = db
        self.client = client or LinkedInOAuthClient()

    def create_authorization_flow(
        self,
        user: User,
        org: Organization,
    ) -> Dict[str, str]:
        """
        Initiate an OAuth 2.0 authorization attempt.
        Generates cryptographically random state and nonce, binds them to the user and organization,
        persists replay protection record with a 15-minute TTL, and returns the authorization URL.
        """
        if not self.client.is_configured():
            raise ValueError(
                "LinkedIn integration credentials are not configured. "
                "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set."
            )

        # 32-byte cryptographically secure random state and nonce
        state_str = secrets.token_urlsafe(32)
        nonce_str = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)

        oauth_state = LinkedInOAuthState(
            state=state_str,
            organization_id=org.id,
            user_id=user.id,
            nonce=nonce_str,
            is_used=False,
            expires_at=expires_at,
            created_at=now,
        )
        try:
            self.db.add(oauth_state)
            self.db.commit()
        except (ProgrammingError, OperationalError) as exc:
            self.db.rollback()
            logger.error("Database table missing when persisting LinkedInOAuthState: %s", exc)
            raise ValueError(
                "LinkedIn database tables are not initialized. "
                "Please run pending database migrations before connecting an account."
            ) from exc

        auth_url = self.client.get_authorization_url(state=state_str, nonce=nonce_str)
        return {
            "authorization_url": auth_url,
            "state": state_str,
        }

    def validate_and_consume_state(self, state: str) -> LinkedInOAuthState:
        """
        Validate and consume an OAuth state token.
        Enforces existence, expiry, and single-use replay protection.
        """
        if not state or not state.strip():
            raise ValueError("OAuth state parameter is missing.")

        oauth_state = (
            self.db.query(LinkedInOAuthState)
            .filter(LinkedInOAuthState.state == state.strip())
            .first()
        )

        if not oauth_state:
            logger.warning("Unrecognized OAuth state parameter: '%s'", state[:8] + "...")
            raise ValueError("Invalid or unrecognized OAuth state parameter.")

        if oauth_state.is_used:
            logger.warning("OAuth state replay attempt detected for state: '%s'", state[:8] + "...")
            raise ValueError("OAuth state has already been used (replay attack prevented).")

        now = datetime.now(timezone.utc)
        state_expires_at = _ensure_utc(oauth_state.expires_at)
        if state_expires_at and now > state_expires_at:
            logger.warning("Expired OAuth state attempted: '%s'", state[:8] + "...")
            oauth_state.is_used = True
            self.db.commit()
            raise ValueError("OAuth state has expired. Please initiate authorization again.")

        # Mark as consumed immediately to prevent replay
        oauth_state.is_used = True
        self.db.commit()
        return oauth_state

    async def handle_callback(
        self,
        state: str,
        code: Optional[str] = None,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> LinkedInConnection:
        """
        Process the LinkedIn OAuth callback.
        Enforces state validation, handles user cancellation, exchanges code for tokens,
        validates OpenID Connect ID token, encrypts tokens, and upserts the tenant connection.
        """
        # Validate state first (always enforces replay protection even on errors)
        oauth_state = self.validate_and_consume_state(state)

        # Handle provider-side errors or user cancellation
        if error:
            logger.info("LinkedIn authorization cancelled or rejected: %s (%s)", error, error_description)
            raise ValueError(f"LinkedIn authorization was cancelled or denied: {error_description or error}")

        if not code or not code.strip():
            raise ValueError("Authorization code is missing from LinkedIn callback.")

        # Exchange authorization code for tokens
        token_data = await self.client.exchange_code_for_tokens(code=code.strip())
        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 5184000)  # Standard LinkedIn 60-day default
        id_token = token_data.get("id_token")
        refresh_token = token_data.get("refresh_token")
        refresh_token_expires_in = token_data.get("refresh_token_expires_in")
        granted_scopes = token_data.get("scope", settings.LINKEDIN_SCOPES)

        # Validate ID token if returned
        member_id: Optional[str] = None
        member_name: Optional[str] = None
        member_email: Optional[str] = None
        profile_picture_url: Optional[str] = None

        if id_token:
            try:
                claims = await self.client.validate_id_token(
                    id_token=id_token,
                    nonce=oauth_state.nonce,
                )
                member_id = claims.get("sub")
                member_name = claims.get("name")
                member_email = claims.get("email")
                profile_picture_url = claims.get("picture")
            except Exception as exc:
                logger.warning("ID token validation failed: %s; attempting userinfo fallback.", exc)

        # Enrich or retrieve member identity via userinfo endpoint if needed
        if not member_id or not member_name or not member_email:
            try:
                userinfo = await self.client.get_userinfo(access_token)
                member_id = member_id or userinfo.get("sub")
                member_name = member_name or userinfo.get("name")
                member_email = member_email or userinfo.get("email")
                profile_picture_url = profile_picture_url or userinfo.get("picture")
            except Exception as exc:
                logger.warning("Supplemental LinkedIn userinfo retrieval failed: %s", exc)

        if not member_id:
            raise ValueError("Unable to determine LinkedIn member identity from ID token or userinfo.")

        # Encrypt tokens before persistence at rest
        encrypted_access = encrypt_token(access_token)
        if not encrypted_access:
            raise ValueError("Failed to encrypt LinkedIn access token.")

        encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

        now = datetime.now(timezone.utc)
        access_expires_at = now + timedelta(seconds=expires_in) if expires_in else None
        refresh_expires_at = (
            now + timedelta(seconds=refresh_token_expires_in)
            if refresh_token_expires_in
            else None
        )

        # Upsert connection bound strictly to the organization from oauth_state
        connection = (
            self.db.query(LinkedInConnection)
            .filter(LinkedInConnection.organization_id == oauth_state.organization_id)
            .first()
        )

        if connection:
            connection.user_id = oauth_state.user_id
            connection.linkedin_member_id = str(member_id)
            connection.member_name = member_name
            connection.member_email = member_email
            connection.profile_picture_url = profile_picture_url
            connection.encrypted_access_token = encrypted_access
            connection.access_token_expires_at = access_expires_at
            connection.encrypted_refresh_token = encrypted_refresh
            connection.refresh_token_expires_at = refresh_expires_at
            connection.scopes = granted_scopes
            connection.status = "connected"
            connection.connected_at = now
            connection.disconnected_at = None
            connection.updated_at = now
        else:
            connection = LinkedInConnection(
                organization_id=oauth_state.organization_id,
                user_id=oauth_state.user_id,
                linkedin_member_id=str(member_id),
                member_name=member_name,
                member_email=member_email,
                profile_picture_url=profile_picture_url,
                encrypted_access_token=encrypted_access,
                access_token_expires_at=access_expires_at,
                encrypted_refresh_token=encrypted_refresh,
                refresh_token_expires_at=refresh_expires_at,
                scopes=granted_scopes,
                status="connected",
                connected_at=now,
                disconnected_at=None,
                created_at=now,
                updated_at=now,
            )
            self.db.add(connection)

        self.db.commit()
        self.db.refresh(connection)
        logger.info(
            "Successfully connected LinkedIn account for organization %s (member_id: %s)",
            oauth_state.organization_id,
            member_id,
        )
        return connection

    def get_connection_status(self, org: Organization) -> Dict[str, Any]:
        """
        Retrieve redacted LinkedIn integration status for an organization.
        Strictly prevents token leakage in responses.
        """
        is_configured = self.client.is_configured()
        if not is_configured:
            return {
                "configured": False,
                "connected": False,
                "status": "not_configured",
                "member_id": None,
                "member_name": None,
                "member_email": None,
                "profile_picture_url": None,
                "connected_at": None,
                "expires_at": None,
                "scopes": [],
                "message": "LinkedIn integration credentials are not configured in backend settings.",
            }

        try:
            connection = (
                self.db.query(LinkedInConnection)
                .filter(LinkedInConnection.organization_id == org.id)
                .first()
            )
        except (ProgrammingError, OperationalError) as exc:
            self.db.rollback()
            logger.warning("LinkedIn database tables are not yet present in active database: %s", exc)
            return {
                "configured": is_configured,
                "connected": False,
                "status": "disconnected",
                "member_id": None,
                "member_name": None,
                "member_email": None,
                "profile_picture_url": None,
                "connected_at": None,
                "expires_at": None,
                "scopes": [],
                "message": "LinkedIn database schema pending migration. Database tables are not yet initialized.",
            }

        if not connection or connection.status != "connected":
            return {
                "configured": True,
                "connected": False,
                "status": "disconnected",
                "member_id": connection.linkedin_member_id if connection else None,
                "member_name": connection.member_name if connection else None,
                "member_email": connection.member_email if connection else None,
                "profile_picture_url": connection.profile_picture_url if connection else None,
                "connected_at": connection.connected_at if connection else None,
                "expires_at": connection.access_token_expires_at if connection else None,
                "scopes": connection.scopes.split(",") if connection and connection.scopes else [],
                "message": "No active LinkedIn connection. Connect your authorized account to begin.",
            }

        # Check token expiration
        now = datetime.now(timezone.utc)
        token_expires_at = _ensure_utc(connection.access_token_expires_at)
        is_expired = bool(
            token_expires_at
            and now > token_expires_at
        )

        if is_expired:
            return {
                "configured": True,
                "connected": False,
                "status": "expired",
                "member_id": connection.linkedin_member_id,
                "member_name": connection.member_name,
                "member_email": connection.member_email,
                "profile_picture_url": connection.profile_picture_url,
                "connected_at": connection.connected_at,
                "expires_at": connection.access_token_expires_at,
                "scopes": connection.scopes.split(","),
                "message": "LinkedIn access token has expired. Please re-authorize to renew access.",
            }

        return {
            "configured": True,
            "connected": True,
            "status": "connected",
            "member_id": connection.linkedin_member_id,
            "member_name": connection.member_name,
            "member_email": connection.member_email,
            "profile_picture_url": connection.profile_picture_url,
            "connected_at": connection.connected_at,
            "expires_at": connection.access_token_expires_at,
            "scopes": connection.scopes.split(","),
            "message": f"Connected as {connection.member_name or connection.linkedin_member_id}.",
        }

    def disconnect(self, org: Organization) -> bool:
        """
        Disconnect LinkedIn account for an organization.
        Marks connection disconnected, erases encrypted tokens, and updates timestamp.
        """
        try:
            connection = (
                self.db.query(LinkedInConnection)
                .filter(LinkedInConnection.organization_id == org.id)
                .first()
            )
        except (ProgrammingError, OperationalError) as exc:
            self.db.rollback()
            logger.warning("LinkedIn database tables are not yet present in active database: %s", exc)
            return True

        if not connection:
            return True

        connection.status = "disconnected"
        connection.encrypted_access_token = ""
        connection.encrypted_refresh_token = None
        connection.disconnected_at = datetime.now(timezone.utc)
        connection.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        logger.info("Disconnected LinkedIn account for organization %s", org.id)
        return True


    def get_capabilities(self, org: Organization) -> Dict[str, Any]:
        """
        Evaluates LinkedIn API capabilities against granted OAuth scopes and official LinkedIn API policies.
        Differentiates supported OpenID identity scopes from restricted messaging/invitation endpoints.
        """
        status_data = self.get_connection_status(org=org)
        granted_scopes = set(status_data.get("scopes") or [])
        connected = status_data.get("connected", False)

        has_profile = "profile" in granted_scopes or "openid" in granted_scopes
        has_email = "email" in granted_scopes
        has_org_social = "r_organization_social" in granted_scopes or "w_organization_social" in granted_scopes
        has_member_social = "w_member_social" in granted_scopes

        capabilities = {
            "read_profile": {
                "status": "available" if (connected and has_profile) else "restricted",
                "scope_required": "openid,profile",
                "scope_granted": has_profile,
                "description": "Read authenticated member name, profile picture, and unique ID via OpenID Connect.",
                "assisted_alternative": None,
            },
            "read_email": {
                "status": "available" if (connected and has_email) else "restricted",
                "scope_required": "email",
                "scope_granted": has_email,
                "description": "Read authenticated member primary email address via OpenID Connect.",
                "assisted_alternative": None,
            },
            "organization_page_info": {
                "status": "available" if (connected and has_org_social) else "restricted",
                "scope_required": "r_organization_social",
                "scope_granted": has_org_social,
                "description": "Read LinkedIn Company Page data and follower analytics. Requires LinkedIn Community Management API approval.",
                "assisted_alternative": "Manual company research via direct LinkedIn company page links.",
            },
            "publish_content": {
                "status": "available" if (connected and has_member_social) else "restricted",
                "scope_required": "w_member_social",
                "scope_granted": has_member_social,
                "description": "Publish status updates or articles to LinkedIn feed. Requires LinkedIn Share on LinkedIn product.",
                "assisted_alternative": "Draft copy provided for 1-click personal posting.",
            },
            "connection_invitations": {
                "status": "unsupported",
                "scope_required": "Partner API (Recruiter / Sales Navigator)",
                "scope_granted": False,
                "description": "Automated invitation dispatch is restricted by LinkedIn anti-spam policies to protect member accounts.",
                "assisted_alternative": "Personalized 300-character connection notes generated with 1-click copy & profile launch.",
            },
            "direct_messages": {
                "status": "unsupported",
                "scope_required": "Partner API (Enterprise Messaging)",
                "scope_granted": False,
                "description": "Direct 1-to-1 automated InMail requires enterprise LinkedIn partner contract. Standard developer apps are strictly disallowed.",
                "assisted_alternative": "Full follow-up messages pre-rendered with personalized booking URL for manual dispatch.",
            },
            "invitation_acceptance": {
                "status": "unsupported",
                "scope_required": "Enterprise Webhook",
                "scope_granted": False,
                "description": "Real-time webhook notifications for member connection acceptance are restricted to enterprise partner applications.",
                "assisted_alternative": "Manual 1-click confirmation tracking in campaign outreach queue.",
            },
        }

        return {
            "configured": status_data.get("configured", False),
            "connected": connected,
            "member_id": status_data.get("member_id"),
            "member_name": status_data.get("member_name"),
            "granted_scopes": list(granted_scopes),
            "capabilities": capabilities,
            "workflow_mode": "assisted",
            "booking_url": "https://cal.com/agilereceivables/30min",
            "connection_note_limit": 300,
        }

    def get_campaign_assisted_queue(self, org: Organization, campaign_id: uuid.UUID) -> Dict[str, Any]:
        """
        Retrieves enrolled campaign prospects with pre-rendered, personalized copy-ready
        connection notes (<=300 chars) and follow-up messages with booking URLs.
        """
        import uuid as uuid_mod
        from urllib.parse import quote_plus
        from app.models.campaign import Campaign, CampaignContact
        from app.models.crm import Contact, Company
        from app.models.outreach import Outreach

        campaign = (
            self.db.query(Campaign)
            .filter(Campaign.id == campaign_id, Campaign.organization_id == org.id)
            .first()
        )
        if not campaign:
            raise ValueError(f"Campaign '{campaign_id}' not found.")

        booking_url = "https://cal.com/agilereceivables/30min"

        from app.services.workflow_service import get_campaign_ordered_steps
        ordered_steps = get_campaign_ordered_steps(self.db, campaign)
        li_step = next((s for s in ordered_steps if getattr(s, "step_type", "") == "linkedin"), None)
        custom_template = getattr(li_step, "body_template", None) if li_step else None

        enrollments = (
            self.db.query(CampaignContact)
            .filter(CampaignContact.campaign_id == campaign_id)
            .order_by(CampaignContact.enrolled_at.asc())
            .all()
        )

        items = []
        pending_count = 0
        completed_count = 0

        for cc in enrollments:
            contact = self.db.query(Contact).filter(Contact.id == cc.contact_id).first()
            if not contact:
                continue
            company = self.db.query(Company).filter(Company.id == contact.company_id).first() if contact.company_id else None
            company_name = company.name if company else (getattr(contact, "company", None) or "your company")

            first_name = contact.first_name or "there"
            last_name = contact.last_name or ""
            full_name = f"{first_name} {last_name}".strip()

            from app.models.lead import Lead
            lead = self.db.query(Lead).filter(Lead.contact_id == contact.id, Lead.organization_id == org.id).first()
            profile_url = getattr(contact, "linkedin_profile_url", None) or getattr(contact, "linkedin_url", None)
            if not profile_url and lead:
                profile_url = getattr(lead, "linkedin_profile_url", None)

            has_profile_url = bool(profile_url)
            search_query = f"{full_name} {company_name}".strip()
            search_url = f"https://www.linkedin.com/search/results/all/?keywords={quote_plus(search_query)}"
            linkedin_url = profile_url if has_profile_url else search_url

            if custom_template and len(custom_template) <= 300:
                conn_note = custom_template.replace("{first_name}", first_name).replace("{company}", company_name).replace("{booking_link}", booking_url)
            else:
                conn_note = f"Hi {first_name}, noticed your leadership at {company_name}. We help revenue teams eliminate payment friction and accelerate collections. Would love to connect: {booking_url}"
            if len(conn_note) > 300:
                conn_note = conn_note[:297] + "..."

            followup = (
                f"Hi {first_name},\n\n"
                f"Thanks for connecting! I wanted to reach out regarding receivables automation for {company_name}. "
                f"We help eliminate overdue balances and streamline billing workflows.\n\n"
                f"Are you open to a brief 15-minute briefing this week? You can book directly: {booking_url}\n\n"
                f"Best regards,\nAgile Receivables Team"
            )

            outreach = (
                self.db.query(Outreach)
                .filter(Outreach.campaign_contact_id == cc.id, Outreach.channel == "linkedin")
                .first()
            )
            outreach_status = outreach.status if outreach else "pending"
            outreach_id = outreach.id if outreach else None
            sent_at = outreach.sent_at if outreach else None

            if outreach_status in ("sent", "delivered", "replied"):
                completed_count += 1
            else:
                pending_count += 1

            items.append({
                "campaign_contact_id": cc.id,
                "contact_id": contact.id,
                "lead_id": lead.id if lead else None,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "company_name": company_name,
                "job_title": contact.job_title,
                "linkedin_url": linkedin_url,
                "linkedin_profile_url": profile_url,
                "has_linkedin_profile_url": has_profile_url,
                "search_url": search_url,
                "connection_note": conn_note,
                "followup_message": followup,
                "booking_url": booking_url,
                "outreach_id": outreach_id,
                "outreach_status": outreach_status,
                "sent_at": sent_at,
            })

        return {
            "campaign_id": campaign_id,
            "total": len(items),
            "pending_count": pending_count,
            "completed_count": completed_count,
            "items": items,
        }

    def confirm_assisted_action(
        self,
        user: User,
        org: Organization,
        campaign_id: uuid.UUID,
        campaign_contact_id: uuid.UUID,
        action_type: str = "connection_request",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Records user's manual confirmation that a LinkedIn connection request or message was dispatched.
        Creates or updates Outreach record, transitions CampaignContact, and logs an OutreachEvent audit entry.
        """
        import uuid as uuid_mod
        from app.models.campaign import Campaign, CampaignContact
        from app.models.crm import Contact
        from app.models.outreach import Outreach, OutreachEvent

        campaign = (
            self.db.query(Campaign)
            .filter(Campaign.id == campaign_id, Campaign.organization_id == org.id)
            .first()
        )
        if not campaign:
            raise ValueError(f"Campaign '{campaign_id}' not found.")

        cc = (
            self.db.query(CampaignContact)
            .filter(CampaignContact.id == campaign_contact_id, CampaignContact.campaign_id == campaign_id)
            .first()
        )
        if not cc:
            raise ValueError(f"Campaign contact '{campaign_contact_id}' not found.")

        contact = self.db.query(Contact).filter(Contact.id == cc.contact_id).first()
        now = datetime.now(timezone.utc)

        outreach = (
            self.db.query(Outreach)
            .filter(Outreach.campaign_contact_id == cc.id, Outreach.channel == "linkedin")
            .first()
        )

        if not outreach:
            outreach = Outreach(
                organization_id=org.id,
                campaign_id=campaign_id,
                contact_id=cc.contact_id,
                campaign_contact_id=cc.id,
                channel="linkedin",
                status="sent",
                subject="LinkedIn Assisted Outreach",
                body=f"Assisted {action_type} dispatched via LinkedIn. {notes or ''}".strip(),
                provider="linkedin_assisted",
                provider_message_id=f"li_ast_{uuid_mod.uuid4().hex[:12]}",
                recipient=getattr(contact, "linkedin_url", None) or (f"{contact.first_name} {contact.last_name}" if contact else "Prospect"),
                sent_at=now,
            )
            self.db.add(outreach)
            self.db.flush()
        else:
            outreach.status = "sent"
            outreach.sent_at = now
            outreach.provider = "linkedin_assisted"

        cc.enrollment_status = "in_progress"
        cc.current_step = 1

        event = OutreachEvent(
            organization_id=org.id,
            outreach_id=outreach.id,
            event_type="sent",
            event_metadata={
                "mode": "assisted_manual",
                "action": action_type,
                "confirmed_by_user_id": str(user.id),
                "notes": notes,
            },
            occurred_at=now,
        )
        self.db.add(event)
        self.db.commit()

        return {
            "success": True,
            "outreach_id": outreach.id,
            "status": outreach.status,
            "confirmed_at": now,
            "message": f"Successfully recorded manual {action_type} for prospect.",
        }

    def update_prospect_linkedin_url(
        self,
        org: Organization,
        campaign_id: uuid.UUID,
        campaign_contact_id: uuid.UUID,
        profile_url: str,
    ) -> Dict[str, Any]:
        """
        Update the LinkedIn profile URL for an enrolled prospect from the assisted outreach workspace.
        Validates the URL, normalizes it, and syncs across Contact and associated Lead.
        """
        from app.core.normalization import normalize_linkedin_profile_url
        from app.models.campaign import CampaignContact
        from app.models.crm import Contact
        from app.models.lead import Lead

        normalized_url = normalize_linkedin_profile_url(profile_url)
        if not normalized_url:
            raise ValueError("A valid LinkedIn profile URL is required.")

        cc = (
            self.db.query(CampaignContact)
            .filter(CampaignContact.id == campaign_contact_id, CampaignContact.campaign_id == campaign_id)
            .first()
        )
        if not cc:
            raise ValueError(f"Campaign contact '{campaign_contact_id}' not found.")

        contact = self.db.query(Contact).filter(Contact.id == cc.contact_id, Contact.organization_id == org.id).first()
        if not contact:
            raise ValueError(f"Contact '{cc.contact_id}' not found.")

        contact.linkedin_profile_url = normalized_url

        lead = self.db.query(Lead).filter(Lead.contact_id == contact.id, Lead.organization_id == org.id).first()
        if lead:
            lead.linkedin_profile_url = normalized_url

        self.db.commit()

        return {
            "success": True,
            "campaign_contact_id": cc.id,
            "contact_id": contact.id,
            "linkedin_profile_url": normalized_url,
            "message": "Successfully updated LinkedIn profile URL.",
        }

