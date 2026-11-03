"""Physical Mail campaign orchestration service for Poplar direct mail operations."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.crm import Contact, Company
from app.models.lead import Lead
from app.models.outreach import Outreach, OutreachEvent
from app.models.tenant import Organization
from app.services.physical_mail.address_validator import validate_usps_address
from app.services.physical_mail.poplar_client import (
    PoplarAPIError,
    PoplarAuthenticationError,
    PoplarClient,
    PoplarError,
    PoplarNotFoundError,
    PoplarPermissionError,
    PoplarRateLimitError,
    PoplarRecipient,
    PoplarTimeoutError,
    PoplarValidationError,
    VALID_POPLAR_PURPOSES,
    VALID_POPLAR_SUB_PURPOSES,
    get_poplar_client,
)

logger = logging.getLogger(__name__)

# Default estimated unit cost ($1.15 covers full-color print, stock, and USPS First Class postage)
DEFAULT_UNIT_COST = 1.15

# Supported mailpiece specifications
VALID_MAILPIECE_SIZES = {"4x6", "6x9", "6x11"}
VALID_FORMATS = {"postcard", "bw_envelope", "color_envelope", "bifold", "trifold"}
VALID_POSTAGE_CLASSES = {"usps_standard", "usps_first_class"}
VALID_PAPER_TYPES = {"premium_coated", "premium_uncoated"}

SUPPORTED_MAILPIECE_OPTIONS = {
    "sizes": [
        {"id": "4x6", "label": "4x6 Postcard", "description": "Standard postcard size, ideal for concise reminders"},
        {"id": "6x9", "label": "6x9 Postcard", "description": "Medium oversized postcard for impactful visual presentation"},
        {"id": "6x11", "label": "6x11 Postcard", "description": "Maximum impact postcard size for high-conversion offers"},
    ],
    "formats": [
        {"id": "postcard", "label": "Postcard (No Envelope - Flat Card)", "description": "Direct mail flat postcard without an envelope"},
        {"id": "bw_envelope", "label": "Black & White Letter in Envelope", "description": "Professional 8.5x11 black & white letter with #10 security envelope"},
        {"id": "color_envelope", "label": "Full-Color Letter in Envelope", "description": "Vibrant 8.5x11 full-color letter with double window envelope"},
        {"id": "bifold", "label": "Bifold Self-Mailer", "description": "Folded self-mailer offering 4 distinct panels for storytelling"},
        {"id": "trifold", "label": "Trifold Self-Mailer", "description": "Compact folded brochure with 6 printable panels"},
    ],
    "postage_classes": [
        {"id": "usps_first_class", "label": "USPS First Class", "delivery_time": "3–5 business days", "description": "Fastest delivery with address forwarding service"},
        {"id": "usps_standard", "label": "USPS Standard (Marketing Mail)", "delivery_time": "5–15 business days", "description": "Economical bulk postage rate for planned schedules"},
    ],
    "paper_types": [
        {"id": "premium_coated", "label": "Premium Coated (Gloss)", "finish": "UV gloss finish", "description": "High-shine UV gloss protective finish for crisp photo prints"},
        {"id": "premium_uncoated", "label": "Premium Uncoated (Matte)", "finish": "Matte natural feel", "description": "Smooth non-reflective matte cardstock with tactile feel"},
    ],
    "cost_estimates": {
        "4x6:usps_standard": 0.70,
        "4x6:usps_first_class": 0.85,
        "6x9:usps_standard": 0.95,
        "6x9:usps_first_class": 1.15,
        "6x11:usps_standard": 1.10,
        "6x11:usps_first_class": 1.35,
        "postcard:usps_standard": 0.95,
        "postcard:usps_first_class": 1.15,
        "bw_envelope:usps_standard": 0.90,
        "bw_envelope:usps_first_class": 1.10,
        "color_envelope:usps_standard": 1.05,
        "color_envelope:usps_first_class": 1.30,
        "bifold:usps_standard": 1.20,
        "bifold:usps_first_class": 1.45,
        "trifold:usps_standard": 1.25,
        "trifold:usps_first_class": 1.55,
    },
}

# Estimated cost table by combination
MAILPIECE_COST_ESTIMATES = {
    ("4x6", "usps_first_class"): 0.85,
    ("4x6", "usps_standard"): 0.70,
    ("6x9", "usps_first_class"): 1.15,
    ("6x9", "usps_standard"): 0.95,
    ("6x11", "usps_first_class"): 1.35,
    ("6x11", "usps_standard"): 1.10,
    ("postcard", "usps_first_class"): 1.15,
    ("postcard", "usps_standard"): 0.95,
    ("bw_envelope", "usps_first_class"): 1.10,
    ("bw_envelope", "usps_standard"): 0.90,
    ("color_envelope", "usps_first_class"): 1.30,
    ("color_envelope", "usps_standard"): 1.05,
    ("bifold", "usps_first_class"): 1.45,
    ("bifold", "usps_standard"): 1.20,
    ("trifold", "usps_first_class"): 1.55,
    ("trifold", "usps_standard"): 1.25,
}


DIMENSIONAL_SPECIFICATIONS = {
    "4x6": {
        "name": "4x6 Postcard",
        "trim_inches": "4.00 x 6.00",
        "bleed_inches": "4.25 x 6.25",
        "dimensions_px_300dpi": [1275, 1875],
        "safe_zone_inches": "3.75 x 5.75",
        "supported_formats": ["PDF", "PNG", "JPEG"],
        "max_file_size_mb": 25,
        "recommendation": "Use high-resolution 300 DPI PDF or PNG with 0.125 inch bleed on all sides.",
    },
    "6x9": {
        "name": "6x9 Postcard",
        "trim_inches": "6.00 x 9.00",
        "bleed_inches": "6.25 x 9.25",
        "dimensions_px_300dpi": [1875, 2775],
        "safe_zone_inches": "5.75 x 8.75",
        "supported_formats": ["PDF", "PNG", "JPEG"],
        "max_file_size_mb": 25,
        "recommendation": "Ideal for prominent marketing offers. Ensure text remains within the safe zone.",
    },
    "6x11": {
        "name": "6x11 Panoramic Postcard",
        "trim_inches": "6.00 x 11.00",
        "bleed_inches": "6.25 x 11.25",
        "dimensions_px_300dpi": [1875, 3375],
        "safe_zone_inches": "5.75 x 10.75",
        "supported_formats": ["PDF", "PNG", "JPEG"],
        "max_file_size_mb": 25,
        "recommendation": "Maximum postcard size allowed by USPS without flats pricing surcharge.",
    },
    "postcard": {
        "name": "Standard Postcard (Flat Card)",
        "trim_inches": "4.00 x 6.00 to 6.00 x 11.00",
        "bleed_inches": "0.125 inch bleed on all sides",
        "dimensions_px_300dpi": [1875, 2775],
        "safe_zone_inches": "0.25 inch inside trim line",
        "supported_formats": ["PDF", "PNG", "JPEG"],
        "max_file_size_mb": 25,
        "recommendation": "Single-sheet flat cardstock without an envelope. High-resolution 300 DPI PDF or PNG.",
    },
    "bw_envelope": {
        "name": "Letter in B&W Envelope",
        "trim_inches": "8.50 x 11.00",
        "bleed_inches": "8.75 x 11.25",
        "dimensions_px_300dpi": [2550, 3300],
        "safe_zone_inches": "8.00 x 10.50",
        "supported_formats": ["PDF"],
        "max_file_size_mb": 25,
        "recommendation": "Standard single or multi-page letter in #10 security envelope. PDF format required.",
    },
    "color_envelope": {
        "name": "Full-Color Letter in Envelope",
        "trim_inches": "8.50 x 11.00",
        "bleed_inches": "8.75 x 11.25",
        "dimensions_px_300dpi": [2550, 3300],
        "safe_zone_inches": "8.00 x 10.50",
        "supported_formats": ["PDF"],
        "max_file_size_mb": 25,
        "recommendation": "Full-color letter in #10 double-window envelope. Address block placed in top-left window zone.",
    },
    "bifold": {
        "name": "Bifold Self-Mailer",
        "trim_inches": "8.50 x 11.00 folded to 5.50 x 8.50",
        "bleed_inches": "8.75 x 11.25",
        "dimensions_px_300dpi": [2550, 3300],
        "safe_zone_inches": "5.00 x 8.00 per panel",
        "supported_formats": ["PDF"],
        "max_file_size_mb": 25,
        "recommendation": "Folded self-mailer with 4 printable panels. Requires wafer tab sealing per USPS DMM.",
    },
    "trifold": {
        "name": "Trifold Self-Mailer",
        "trim_inches": "8.50 x 11.00 folded to 3.66 x 8.50",
        "bleed_inches": "8.75 x 11.25",
        "dimensions_px_300dpi": [2550, 3300],
        "safe_zone_inches": "3.25 x 8.00 per panel",
        "supported_formats": ["PDF"],
        "max_file_size_mb": 25,
        "recommendation": "6-panel compact self-mailer. Perfect for multi-part financial notices or service overviews.",
    },
}


def validate_creative_asset(
    file_name: str,
    file_size_bytes: Optional[int] = None,
    content_type: Optional[str] = None,
    mailpiece_size: str = "4x6",
) -> Dict[str, Any]:
    """Validates an uploaded or linked creative asset against Poplar specifications."""
    spec = DIMENSIONAL_SPECIFICATIONS.get(mailpiece_size) or DIMENSIONAL_SPECIFICATIONS["4x6"]
    errors: List[str] = []
    warnings: List[str] = []

    if not file_name or not file_name.strip():
        errors.append("File name or artwork asset identifier is required.")
        return {"is_valid": False, "errors": errors, "warnings": warnings, "spec": spec}

    clean_name = file_name.strip()
    ext = clean_name.split(".")[-1].lower() if "." in clean_name else ""
    allowed_exts = [f.lower() for f in spec["supported_formats"]]
    if ext not in allowed_exts and not (ext == "jpg" and "jpeg" in allowed_exts):
        errors.append(f"File extension '.{ext}' is not supported for {spec['name']}. Allowed: {', '.join(spec['supported_formats'])}.")

    if file_size_bytes is not None:
        max_bytes = spec["max_file_size_mb"] * 1024 * 1024
        if file_size_bytes > max_bytes:
            errors.append(f"File size ({round(file_size_bytes / (1024 * 1024), 2)} MB) exceeds Poplar maximum of {spec['max_file_size_mb']} MB.")

    if ext in ("png", "jpg", "jpeg") and ("Letter" in spec["name"] or "Mailer" in spec["name"]):
        warnings.append("Letters and Self-Mailers require PDF format for multi-panel address positioning.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "file_name": clean_name,
        "spec": spec,
    }

# In-memory approval token registry for idempotency during campaign submissions
_EXECUTED_APPROVAL_TOKENS: set[str] = set()


# ── Domain Exceptions ─────────────────────────────────────────────────────────

class PhysicalMailError(Exception):
    """Base exception for physical mail operations."""
    pass


class UnapprovedCampaignError(PhysicalMailError):
    """Raised when submission is attempted without explicit user approval."""
    pass


class DuplicateSubmissionError(PhysicalMailError):
    """Raised when duplicate submission is attempted with an already-used approval token."""
    pass


class CampaignNotFoundError(PhysicalMailError):
    """Raised when campaign is not found or belongs to another tenant."""
    pass


class RecipientNotFoundError(PhysicalMailError):
    """Raised when target recipient contact or lead is not found."""
    pass


class PoplarPersistenceError(PhysicalMailError):
    """Raised when a remote Poplar campaign was created but local database persistence failed."""
    def __init__(self, message: str, poplar_campaign_id: str, local_campaign_id: uuid.UUID) -> None:
        super().__init__(message)
        self.poplar_campaign_id = poplar_campaign_id
        self.local_campaign_id = local_campaign_id


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class RecipientAuditItem:
    recipient_id: uuid.UUID
    recipient_type: str  # "contact" or "lead"
    full_name: str
    company_name: Optional[str]
    is_valid: bool
    errors: List[str]
    cleaned_address: Optional[Dict[str, str]] = None


@dataclass
class MailValidationReport:
    campaign_id: uuid.UUID
    total_recipients: int
    valid_count: int
    invalid_count: int
    valid_recipients: List[RecipientAuditItem] = field(default_factory=list)
    invalid_recipients: List[RecipientAuditItem] = field(default_factory=list)


@dataclass
class MailPreviewResult:
    campaign_id: uuid.UUID
    poplar_campaign_id: str
    poplar_creative_id: Optional[str]
    unit_cost: float
    total_recipients: int
    valid_count: int
    invalid_count: int
    estimated_total_cost: float
    sample_preview: Optional[Dict[str, Any]]
    invalid_recipients: List[Dict[str, Any]]
    approval_required: bool = True


@dataclass
class SingleMailingOutcome:
    recipient_id: uuid.UUID
    outreach_id: uuid.UUID
    success: bool
    status: str
    mailing_id: Optional[str] = None
    proof_url: Optional[str] = None
    error: Optional[str] = None
    simulated: bool = False


@dataclass
class CampaignSubmissionResult:
    campaign_id: uuid.UUID
    total_processed: int
    total_submitted: int
    total_failed: int
    estimated_cost: float
    outcomes: List[SingleMailingOutcome] = field(default_factory=list)


# ── Physical Mail Service ─────────────────────────────────────────────────────

class PhysicalMailService:
    """
    Manages physical direct mail campaigns, address pre-flight audits,
    cost calculations, explicit approval gates, and 1-to-1 Poplar submissions.
    """

    def __init__(self, db: Session, client: Optional[PoplarClient] = None) -> None:
        self.db = db
        self.client = client


    def list_poplar_campaigns(self) -> List[Dict[str, Any]]:
        """
        Retrieves list of existing campaigns configured in Poplar via read-only GET /v1/campaigns.
        """
        client = self._get_active_client()
        return client.list_campaigns()

    def list_account_creatives(self, campaign_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries available creatives across the Poplar account."""
        client = self._get_active_client()
        return client.list_account_creatives(campaign_id=campaign_id)

    def _get_active_client(self) -> PoplarClient:
        if self.client is not None:
            return self.client
        return get_poplar_client()

    def _extract_recipient_details(self, entity: Union[Contact, Lead, Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize address attributes across Contact, Lead, or dictionary."""
        if isinstance(entity, dict):
            return {
                "id": entity.get("id"),
                "full_name": entity.get("full_name") or f"{entity.get('first_name', '')} {entity.get('last_name', '')}".strip(),
                "first_name": entity.get("first_name"),
                "last_name": entity.get("last_name"),
                "company": entity.get("company") or entity.get("company_name"),
                "email": entity.get("email"),
                "address_1": entity.get("address_1") or entity.get("address_line_1"),
                "address_2": entity.get("address_2") or entity.get("address_line_2"),
                "city": entity.get("city"),
                "state": entity.get("state"),
                "postal_code": entity.get("postal_code") or entity.get("zip"),
                "country": entity.get("country") or "US",
            }
        
        # Entity is Contact or Lead model
        first = getattr(entity, "first_name", None) or ""
        last = getattr(entity, "last_name", None) or ""
        full_name = f"{first} {last}".strip()
        company = getattr(entity, "company_name", None)
        if not company and hasattr(entity, "company") and getattr(entity, "company"):
            company = getattr(entity.company, "name", None)

        return {
            "id": entity.id,
            "full_name": full_name or None,
            "first_name": first or None,
            "last_name": last or None,
            "company": company,
            "email": getattr(entity, "email", None),
            "address_1": getattr(entity, "address_line_1", None),
            "address_2": getattr(entity, "address_line_2", None),
            "city": getattr(entity, "city", None),
            "state": getattr(entity, "state", None),
            "postal_code": getattr(entity, "postal_code", None),
            "country": getattr(entity, "country", None) or "US",
        }

    def validate_campaign_recipients(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        recipient_ids: Optional[List[uuid.UUID]] = None,
    ) -> MailValidationReport:
        """
        Runs pre-flight address validation on all enrolled recipients for a campaign.
        Enforces tenant isolation and itemizes all invalid addresses.
        """
        campaign = self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        ).scalar_one_or_none()
        if not campaign:
            raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found for this organization.")

        # Query enrollments
        query = select(CampaignContact).where(CampaignContact.campaign_id == campaign_id)
        if recipient_ids:
            query = query.where(CampaignContact.contact_id.in_(recipient_ids))
        enrollments = self.db.execute(query).scalars().all()

        valid_items: List[RecipientAuditItem] = []
        invalid_items: List[RecipientAuditItem] = []

        for enroll in enrollments:
            contact = self.db.execute(
                select(Contact).where(Contact.id == enroll.contact_id, Contact.organization_id == org_id)
            ).scalar_one_or_none()
            if not contact:
                continue

            extracted = self._extract_recipient_details(contact)
            val_res = validate_usps_address(
                address_1=extracted["address_1"],
                address_2=extracted["address_2"],
                city=extracted["city"],
                state=extracted["state"],
                postal_code=extracted["postal_code"],
                country=extracted["country"],
                full_name=extracted["full_name"],
                company=extracted["company"],
            )

            item = RecipientAuditItem(
                recipient_id=contact.id,
                recipient_type="contact",
                full_name=extracted["full_name"] or "Unknown",
                company_name=extracted["company"],
                is_valid=val_res.is_valid,
                errors=val_res.errors,
                cleaned_address=val_res.cleaned_address,
            )
            if val_res.is_valid:
                valid_items.append(item)
            else:
                invalid_items.append(item)

        return MailValidationReport(
            campaign_id=campaign_id,
            total_recipients=len(valid_items) + len(invalid_items),
            valid_count=len(valid_items),
            invalid_count=len(invalid_items),
            valid_recipients=valid_items,
            invalid_recipients=invalid_items,
        )


    def validate_mailpiece_configuration(
        self,
        mailpiece_size: str,
        format_type: str,
        paper_type: str,
        postage_class: str,
        design_url: Optional[str] = None,
    ) -> Tuple[bool, List[str], float]:
        """
        Validates mailpiece options, returns (is_valid, validation_errors, unit_cost).
        """
        errors = []
        size = (mailpiece_size or "").strip().lower()
        fmt = (format_type or "").strip().lower()
        paper = (paper_type or "").strip().lower()
        postage = (postage_class or "").strip().lower()

        if size not in VALID_MAILPIECE_SIZES:
            errors.append(f"Invalid mailpiece size '{mailpiece_size}'. Supported: {', '.join(sorted(VALID_MAILPIECE_SIZES))}")
        if fmt not in VALID_FORMATS:
            errors.append(f"Invalid format '{format_type}'. Supported: {', '.join(sorted(VALID_FORMATS))}")
        if paper not in VALID_PAPER_TYPES:
            errors.append(f"Invalid paper type '{paper_type}'. Supported: {', '.join(sorted(VALID_PAPER_TYPES))}")
        if postage not in VALID_POSTAGE_CLASSES:
            errors.append(f"Invalid postage class '{postage_class}'. Supported: {', '.join(sorted(VALID_POSTAGE_CLASSES))}")

        # Derive unit cost:
        # For postcards, dimensional size dictates print and postage cost.
        # For letters and self-mailers, format & envelope style dictates cost.
        if fmt == "postcard":
            cost = (
                MAILPIECE_COST_ESTIMATES.get((size, postage))
                or MAILPIECE_COST_ESTIMATES.get((fmt, postage))
                or DEFAULT_UNIT_COST
            )
        else:
            cost = (
                MAILPIECE_COST_ESTIMATES.get((fmt, postage))
                or MAILPIECE_COST_ESTIMATES.get((size, postage))
                or DEFAULT_UNIT_COST
            )
        return len(errors) == 0, errors, cost

    def configure_or_create_poplar_campaign(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        mailpiece_size: str,
        format_type: str,
        paper_type: str,
        postage_class: str,
        design_url: Optional[str] = None,
        design_name: Optional[str] = None,
        poplar_campaign_id: Optional[str] = None,
        creative_id: Optional[str] = None,
        recipient_ids: Optional[List[uuid.UUID]] = None,
        workflow_mode: str = "connect",
        new_campaign_name: Optional[str] = None,
        purpose: str = "retention",
        sub_purpose: str = "reactivation",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Configures physical mail options and connects or creates a corresponding Campaign resource in Poplar.
        Safe operation: Does not purchase postage or dispatch mail.
        """
        campaign = self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        ).scalar_one_or_none()
        if not campaign:
            raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found for this organization.")

        is_valid, errors, unit_cost = self.validate_mailpiece_configuration(
            mailpiece_size=mailpiece_size,
            format_type=format_type,
            paper_type=paper_type,
            postage_class=postage_class,
            design_url=design_url,
        )
        if not is_valid:
            raise PoplarValidationError(f"Invalid mailpiece configuration: {', '.join(errors)}")

        client = self._get_active_client()
        existing_wf = dict(campaign.workflow_config or {})
        existing_poplar = existing_wf.get("poplar", {})
        target_creative_id = (creative_id or existing_poplar.get("creative_id") or "").strip() or None

        mode = (workflow_mode or "connect").strip().lower()

        if mode == "create":
            name = (new_campaign_name or "").strip()
            if not name:
                raise PoplarValidationError("Poplar campaign name cannot be blank.")

            clean_purpose = (purpose or "retention").strip().lower()
            clean_sub_purpose = (sub_purpose or "reactivation").strip().lower()

            if clean_purpose not in VALID_POPLAR_PURPOSES:
                raise PoplarValidationError(
                    f"Invalid Poplar campaign purpose '{purpose}'. Accepted values: {', '.join(sorted(VALID_POPLAR_PURPOSES))}."
                )
            if clean_sub_purpose not in VALID_POPLAR_SUB_PURPOSES:
                raise PoplarValidationError(
                    f"Invalid Poplar campaign sub-purpose '{sub_purpose}'. Accepted values: {', '.join(sorted(VALID_POPLAR_SUB_PURPOSES))}."
                )

            try:
                create_res = client.create_campaign(
                    name=name,
                    purpose=clean_purpose,
                    sub_purpose=clean_sub_purpose,
                    description=(description or "").strip() or None,
                )
            except PoplarError:
                raise
            except Exception as exc:
                logger.warning("Poplar remote campaign creation failed: %s", exc)
                raise PoplarValidationError(f"Failed to create Poplar campaign: {exc}") from exc

            if not isinstance(create_res, dict) or not create_res.get("id"):
                raise PoplarValidationError("Poplar did not return a valid campaign ID upon creation.")

            created_campaign_id = str(create_res.get("id")).strip()

            # Verify newly created resource in Poplar using read-only GET /v1/campaign/:id
            try:
                poplar_data = client.get_campaign(created_campaign_id)
                if not isinstance(poplar_data, dict) or not poplar_data.get("id"):
                    raise PoplarValidationError(
                        f"Newly created Poplar campaign '{created_campaign_id}' could not be verified (invalid response from Poplar)."
                    )
                resolved_campaign_id = str(poplar_data.get("id")).strip()
                if resolved_campaign_id.lower() != created_campaign_id.lower():
                    raise PoplarValidationError(
                        f"Poplar verification mismatch: created ID '{created_campaign_id}' but retrieved '{resolved_campaign_id}'."
                    )
                poplar_name = poplar_data.get("name") or name
                poplar_response_status = "created_remote"
            except PoplarValidationError:
                raise
            except Exception as exc:
                logger.warning("Could not verify newly created Poplar campaign %s: %s", created_campaign_id, exc)
                raise PoplarValidationError(
                    f"Failed to verify newly created Poplar campaign '{created_campaign_id}': {exc}"
                ) from exc
        else:
            # mode == "connect" (default)
            target_poplar_id = (poplar_campaign_id or existing_poplar.get("campaign_id") or "").strip() or None
            if not target_poplar_id:
                raise PoplarValidationError(
                    "Poplar campaign ID is required. Please select or supply an existing Poplar campaign."
                )

            # Verify existing resource in Poplar using read-only GET /v1/campaign/:id
            try:
                poplar_data = client.get_campaign(target_poplar_id)
                if not isinstance(poplar_data, dict) or not poplar_data.get("id"):
                    raise PoplarValidationError(
                        f"Poplar campaign '{target_poplar_id}' could not be verified (invalid response from Poplar)."
                    )
                resolved_campaign_id = str(poplar_data.get("id")).strip()
                if resolved_campaign_id.lower() != target_poplar_id.strip().lower():
                    raise PoplarValidationError(
                        f"Poplar verification mismatch: requested ID '{target_poplar_id}' but received '{resolved_campaign_id}'."
                    )
                poplar_name = poplar_data.get("name") or campaign.name
                poplar_response_status = "linked_existing"
            except PoplarNotFoundError as exc:
                raise PoplarValidationError(
                    f"Poplar campaign '{target_poplar_id}' does not exist in your Poplar account."
                ) from exc
            except PoplarValidationError:
                raise
            except Exception as exc:
                logger.warning("Could not verify existing Poplar campaign %s: %s", target_poplar_id, exc)
                raise PoplarValidationError(
                    f"Failed to verify Poplar campaign '{target_poplar_id}': {exc}"
                ) from exc

        # Update workflow_config on campaign
        poplar_config = {
            "campaign_id": resolved_campaign_id,
            "creative_id": target_creative_id,
            "name": poplar_name,
            "status": poplar_response_status,
            "configured_at": datetime.now(timezone.utc).isoformat(),
            "mailpiece": {
                "size": mailpiece_size,
                "format": format_type,
                "paper": paper_type,
                "postage": postage_class,
                "unit_cost": unit_cost,
            },
            "design": {
                "url": design_url,
                "name": design_name or "Custom Artwork",
            },
        }

        # Update channels if not present
        channels = set(existing_wf.get("channels") or [])
        channels.add("physical_mail")
        existing_wf["channels"] = list(channels)
        existing_wf["poplar"] = poplar_config

        campaign.workflow_config = existing_wf
        try:
            self.db.commit()
            self.db.refresh(campaign)
        except Exception as commit_exc:
            self.db.rollback()
            logger.error(
                "Database commit failed saving Poplar config for campaign %s (poplar_id=%s): %s",
                campaign_id,
                resolved_campaign_id,
                commit_exc,
            )
            if mode == "create":
                raise PoplarPersistenceError(
                    f"Remote Poplar campaign was created successfully with ID '{resolved_campaign_id}', but saving to local database failed: {commit_exc}. You can connect this campaign using 'Connect Existing' with ID: {resolved_campaign_id}.",
                    poplar_campaign_id=resolved_campaign_id,
                    local_campaign_id=campaign_id,
                ) from commit_exc
            raise


        # Preflight validation report on current recipients
        val_report = self.validate_campaign_recipients(org_id=org_id, campaign_id=campaign_id, recipient_ids=recipient_ids)

        return {
            "campaign_id": campaign_id,
            "poplar_campaign_id": resolved_campaign_id,
            "creative_id": target_creative_id,
            "poplar_status": poplar_response_status,
            "poplar_name": poplar_name,
            "mailpiece": poplar_config["mailpiece"],
            "design": poplar_config["design"],
            "unit_cost": unit_cost,
            "estimated_total_cost": round(val_report.valid_count * unit_cost, 2),
            "recipient_summary": {
                "total": val_report.total_recipients,
                "valid": val_report.valid_count,
                "invalid": val_report.invalid_count,
            },
        }

    def get_campaign_physical_mail_config(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Returns the saved physical mail configuration and retrieves remote Poplar resource details."""
        campaign = self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        ).scalar_one_or_none()
        if not campaign:
            raise CampaignNotFoundError(f"Campaign '{campaign_id}' not found for this organization.")

        wf = campaign.workflow_config or {}
        poplar_config = wf.get("poplar", {})
        poplar_campaign_id = poplar_config.get("campaign_id")

        remote_resource = None
        if poplar_campaign_id and not str(poplar_campaign_id).startswith("cmp_poplar_"):
            try:
                client = self._get_active_client()
                remote_resource = client.get_campaign(poplar_campaign_id)
            except Exception as exc:
                logger.debug("Failed fetching remote Poplar campaign %s: %s", poplar_campaign_id, exc)

        return {
            "campaign_id": campaign_id,
            "configured": bool(poplar_config),
            "poplar_campaign_id": poplar_campaign_id,
            "config": poplar_config,
            "remote_resource": remote_resource,
        }

    def preview_campaign_mail(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        unit_cost: float = DEFAULT_UNIT_COST,
        poplar_campaign_id: Optional[str] = None,
        poplar_creative_id: Optional[str] = None,
    ) -> MailPreviewResult:
        """
        Generates personalized mail preview and estimated total production cost.
        """
        report = self.validate_campaign_recipients(org_id=org_id, campaign_id=campaign_id)
        campaign = self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        ).scalar_one_or_none()
        wf = (campaign.workflow_config or {}) if campaign else {}
        poplar_cfg = wf.get("poplar", {})

        resolved_campaign_id = (
            poplar_campaign_id
            or poplar_cfg.get("campaign_id")
            or settings.POPLAR_DEFAULT_CAMPAIGN_ID
            or "cmp_agile_default"
        )
        resolved_creative_id = poplar_creative_id or settings.POPLAR_DEFAULT_CREATIVE_ID

        if unit_cost == DEFAULT_UNIT_COST and poplar_cfg.get("mailpiece", {}).get("unit_cost"):
            unit_cost = float(poplar_cfg["mailpiece"]["unit_cost"])

        estimated_total_cost = round(report.valid_count * unit_cost, 2)

        sample_preview = None
        if report.valid_recipients:
            sample = report.valid_recipients[0]
            sample_preview = {
                "recipient": sample.cleaned_address,
                "merge_tags": {
                    "full_name": sample.full_name,
                    "company": sample.company_name or "",
                },
                "estimated_delivery_days": "4-6 business days",
            }

        invalid_summary = [
            {
                "recipient_id": str(item.recipient_id),
                "full_name": item.full_name,
                "errors": item.errors,
            }
            for item in report.invalid_recipients
        ]

        return MailPreviewResult(
            campaign_id=campaign_id,
            poplar_campaign_id=resolved_campaign_id,
            poplar_creative_id=resolved_creative_id,
            unit_cost=unit_cost,
            total_recipients=report.total_recipients,
            valid_count=report.valid_count,
            invalid_count=report.invalid_count,
            estimated_total_cost=estimated_total_cost,
            sample_preview=sample_preview,
            invalid_recipients=invalid_summary,
            approval_required=True,
        )

    def submit_approved_campaign(
        self,
        org_id: uuid.UUID,
        campaign_id: uuid.UUID,
        approved: bool,
        approval_token: str,
        poplar_campaign_id: Optional[str] = None,
        poplar_creative_id: Optional[str] = None,
        recipient_ids: Optional[List[uuid.UUID]] = None,
        force_mock: bool = False,
    ) -> CampaignSubmissionResult:
        """
        Submits physical mail for all valid recipients in the campaign.
        Strictly enforces:
        1. Explicit approval (`approved=True`)
        2. Idempotency on `approval_token`
        3. Fail-closed test mode unless `settings.POPLAR_ALLOW_LIVE_SENDING=True`
        4. 1-to-1 submission loop with per-recipient error trapping (partial failures handled)
        """
        # 1. Explicit Approval Gate
        if not approved:
            raise UnapprovedCampaignError(
                "Physical mail campaign requires explicit approval before dispatch. "
                "Verify addresses and cost preview, then submit with approved=True."
            )

        token_key = f"{org_id}:{approval_token.strip()}"
        if token_key in _EXECUTED_APPROVAL_TOKENS:
            raise DuplicateSubmissionError(
                f"Campaign submission with approval token '{approval_token}' has already been processed."
            )

        # 2. Validation report
        report = self.validate_campaign_recipients(
            org_id=org_id,
            campaign_id=campaign_id,
            recipient_ids=recipient_ids,
        )
        campaign = self.db.execute(
            select(Campaign).where(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        ).scalar_one_or_none()
        wf = (campaign.workflow_config or {}) if campaign else {}
        poplar_cfg = wf.get("poplar", {})

        resolved_campaign_id = (
            poplar_campaign_id
            or poplar_cfg.get("campaign_id")
            or settings.POPLAR_DEFAULT_CAMPAIGN_ID
            or "cmp_agile_default"
        )
        resolved_creative_id = poplar_creative_id or settings.POPLAR_DEFAULT_CREATIVE_ID

        # Determine if real live API calls are permitted
        should_live_send = (
            settings.POPLAR_ENABLED
            and settings.POPLAR_ALLOW_LIVE_SENDING
            and not force_mock
        )

        outcomes: List[SingleMailingOutcome] = []
        total_submitted = 0
        total_failed = 0

        # Mark approval token as executing to prevent concurrent double-clicks
        _EXECUTED_APPROVAL_TOKENS.add(token_key)

        for item in report.valid_recipients:
            addr = item.cleaned_address or {}
            # Locate or create Outreach record with channel='physical_mail'
            outreach = self.db.execute(
                select(Outreach).where(
                    Outreach.organization_id == org_id,
                    Outreach.campaign_id == campaign_id,
                    Outreach.contact_id == item.recipient_id,
                    Outreach.channel == "physical_mail",
                )
            ).scalar_one_or_none()

            if not outreach:
                # Find campaign_contact_id
                enroll = self.db.execute(
                    select(CampaignContact).where(
                        CampaignContact.campaign_id == campaign_id,
                        CampaignContact.contact_id == item.recipient_id,
                    )
                ).scalar_one_or_none()

                outreach = Outreach(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    campaign_id=campaign_id,
                    contact_id=item.recipient_id,
                    campaign_contact_id=enroll.id if enroll else None,
                    channel="physical_mail",
                    status="draft",
                    recipient=f"{addr.get('address_1')}, {addr.get('city')}, {addr.get('state')} {addr.get('postal_code')}",
                )
                self.db.add(outreach)
                self.db.flush()

            # Prevent double-send if already completed or in-flight
            if outreach.status in ("sending", "sent"):
                outcomes.append(
                    SingleMailingOutcome(
                        recipient_id=item.recipient_id,
                        outreach_id=outreach.id,
                        success=True,
                        status=outreach.status,
                        mailing_id=outreach.provider_message_id,
                    )
                )
                total_submitted += 1
                continue

            poplar_recipient = PoplarRecipient(
                address_1=addr.get("address_1", ""),
                address_2=addr.get("address_2"),
                city=addr.get("city", ""),
                state=addr.get("state", ""),
                postal_code=addr.get("postal_code", ""),
                full_name=item.full_name,
                company=item.company_name,
                identifier=str(outreach.id),
            )
            merge_tags = {
                "full_name": item.full_name,
                "company": item.company_name or "",
            }

            try:
                if should_live_send:
                    client = self._get_active_client()
                    result = client.create_mailing(
                        campaign_id=resolved_campaign_id,
                        recipient=poplar_recipient,
                        merge_tags=merge_tags,
                        creative_id=resolved_creative_id,
                    )
                    mailing_id = result.id
                    proof_url = result.proof_url
                    outreach.status = "sending"
                    outreach.provider_message_id = mailing_id
                    is_simulated = False
                else:
                    # Safe mock mode (fail-closed)
                    mock_hex = uuid.uuid4().hex[:12]
                    mailing_id = f"mlg_mock_{mock_hex}"
                    proof_url = None
                    outreach.status = "sending"
                    outreach.provider_message_id = mailing_id
                    is_simulated = True

                self.db.add(
                    OutreachEvent(
                        organization_id=org_id,
                        outreach_id=outreach.id,
                        event_type="sending",
                        event_metadata={"mailing_id": mailing_id, "simulated": is_simulated},
                        occurred_at=datetime.now(timezone.utc),
                    )
                )
                self.db.commit()

                outcomes.append(
                    SingleMailingOutcome(
                        recipient_id=item.recipient_id,
                        outreach_id=outreach.id,
                        success=True,
                        status="sending",
                        mailing_id=mailing_id,
                        proof_url=proof_url,
                        simulated=is_simulated,
                    )
                )
                total_submitted += 1

            except PoplarError as exc:
                logger.warning("Poplar mailing failed for recipient %s: %s", item.recipient_id, exc)
                outreach.status = "failed"
                self.db.add(
                    OutreachEvent(
                        organization_id=org_id,
                        outreach_id=outreach.id,
                        event_type="failed",
                        event_metadata={"error": str(exc)},
                        occurred_at=datetime.now(timezone.utc),
                    )
                )
                self.db.commit()

                outcomes.append(
                    SingleMailingOutcome(
                        recipient_id=item.recipient_id,
                        outreach_id=outreach.id,
                        success=False,
                        status="failed",
                        error=str(exc),
                    )
                )
                total_failed += 1

        # Also account for invalid recipients as failed items in the report
        for inv in report.invalid_recipients:
            total_failed += 1
            outcomes.append(
                SingleMailingOutcome(
                    recipient_id=inv.recipient_id,
                    outreach_id=uuid.uuid4(),
                    success=False,
                    status="invalid_address",
                    error="; ".join(inv.errors),
                )
            )

        return CampaignSubmissionResult(
            campaign_id=campaign_id,
            total_processed=report.total_recipients,
            total_submitted=total_submitted,
            total_failed=total_failed,
            estimated_cost=round(total_submitted * DEFAULT_UNIT_COST, 2),
            outcomes=outcomes,
        )


def send_single_physical_mail_outreach(
    db: Session,
    org_id: uuid.UUID,
    outreach_id: uuid.UUID,
    raise_on_failure: bool = False,
    force_mock: bool = False,
) -> Outreach:
    """Dispatches an individual physical mail outreach item."""
    outreach = db.execute(
        select(Outreach).where(Outreach.id == outreach_id, Outreach.organization_id == org_id)
    ).scalar_one_or_none()
    if not outreach:
        raise RecipientNotFoundError(f"Outreach '{outreach_id}' not found.")

    contact = outreach.contact
    if not contact:
        outreach.status = "failed"
        db.commit()
        return outreach

    service = PhysicalMailService(db=db)
    extracted = service._extract_recipient_details(contact)
    val = validate_usps_address(
        address_1=extracted["address_1"],
        address_2=extracted["address_2"],
        city=extracted["city"],
        state=extracted["state"],
        postal_code=extracted["postal_code"],
        country=extracted["country"],
        full_name=extracted["full_name"],
        company=extracted["company"],
    )
    if not val.is_valid:
        outreach.status = "failed"
        db.add(
            OutreachEvent(
                organization_id=org_id,
                outreach_id=outreach.id,
                event_type="failed",
                event_metadata={"error": "; ".join(val.errors)},
                occurred_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return outreach

    should_live = settings.POPLAR_ENABLED and settings.POPLAR_ALLOW_LIVE_SENDING and not force_mock
    if should_live:
        client = get_poplar_client()
        res = client.create_mailing(
            campaign_id=settings.POPLAR_DEFAULT_CAMPAIGN_ID or "cmp_agile_default",
            recipient=PoplarRecipient(
                address_1=val.cleaned_address["address_1"],
                address_2=val.cleaned_address.get("address_2"),
                city=val.cleaned_address["city"],
                state=val.cleaned_address["state"],
                postal_code=val.cleaned_address["postal_code"],
                full_name=extracted["full_name"],
                company=extracted["company"],
                identifier=str(outreach.id),
            ),
        )
        outreach.status = "sending"
        outreach.provider_message_id = res.id
    else:
        outreach.status = "sending"
        outreach.provider_message_id = f"mlg_mock_{uuid.uuid4().hex[:12]}"

    db.add(
        OutreachEvent(
            organization_id=org_id,
            outreach_id=outreach.id,
            event_type="sending",
            event_metadata={"mailing_id": outreach.provider_message_id},
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return outreach
