"""Workflow schemas for visual campaign workflow builder."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


SUPPORTED_WORKFLOW_NODE_TYPES = {"start", "email", "wait", "voice", "sms", "condition"}
KNOWN_TEMPLATE_VARIABLES = {
    "contact.first_name",
    "contact.last_name",
    "contact.full_name",
    "contact.email",
    "contact.company",
    "contact.company_name",
    "contact.job_title",
    "contact.phone",
    "first_name",
    "last_name",
    "full_name",
    "email",
    "company",
    "company_name",
    "job_title",
    "phone",
    "sender_name",
    "sender_company_name",
    "sender.name",
    "sender.company_name",
    "sender.company",
    "sender_company",
    "booking_link",
    "booking_url",
}

SUPPORTED_CONDITION_TYPES = {
    "email_replied": "Email: Contact Replied (Halt Sequence)",
    "email_not_replied": "Email: No Reply After Delay (Proceed to Next Step)",
    "email_opened": "Email: Contact Opened Email",
    "meeting_requested": "Voice Call Resulted in Meeting Requested",
    "interested": "Voice Call: Interested and Requests Details",
    "not_interested": "Voice Call: Prospect Not Interested",
    "call_failed": "Voice Call: Failed or Unanswered",
    "call_unclear": "Voice Call: Incomplete Analysis",
    "call_completed": "Voice Call Ended / Completed",
    "contact_opted_out": "Contact Requested Opt-Out / Do Not Contact",
    "email_bounced": "Delivery: Email Bounced (Halt Sequence)",
}


class WorkflowNode(BaseModel):
    """Visual workflow graph node."""
    id: str
    type: str = Field(..., description="start, email, wait, voice, sms, condition")
    title: str = Field(..., description="User-facing step title")
    config: Dict[str, Any] = Field(default_factory=dict)
    position: Optional[Dict[str, float]] = None


class WorkflowEdge(BaseModel):
    """Connection between two workflow nodes."""
    id: str
    source: str
    target: str
    label: Optional[str] = None


class WorkflowConfig(BaseModel):
    """Complete workflow graph model."""
    nodes: List[WorkflowNode] = Field(default_factory=list)
    edges: List[WorkflowEdge] = Field(default_factory=list)


class WorkflowValidationResult(BaseModel):
    """Validation report for workflow graph before saving or activation."""
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    supported_step_types: List[str] = Field(
        default_factory=lambda: ["email", "sms", "wait", "voice", "condition"]
    )
    unavailable_step_types: List[str] = Field(
        default_factory=lambda: ["linkedin", "social_publish"]
    )


class WorkflowSaveRequest(BaseModel):
    """Request payload to save workflow configuration."""
    workflow_config: WorkflowConfig
    description: Optional[str] = None


class WorkflowSaveResponse(BaseModel):
    """Response after saving workflow configuration."""
    campaign_id: uuid.UUID
    workflow_config: WorkflowConfig
    validation: WorkflowValidationResult
    description: Optional[str] = None


class TemplatePreviewRequest(BaseModel):
    """Request payload to preview an email template with persisted contact data."""
    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    contact_id: Optional[uuid.UUID] = None
    sender_name: Optional[str] = None
    sender_company_name: Optional[str] = None
    use_sample: bool = False


class TemplatePreviewResponse(BaseModel):
    """Rendered template result with preview contact and placeholder diagnostics."""
    rendered_subject: Optional[str] = None
    rendered_body: Optional[str] = None
    rendered_html: Optional[str] = None
    booking_url: Optional[str] = None
    unresolved_placeholders: List[str] = Field(default_factory=list)
    contact_used: Optional[Dict[str, Any]] = None
    validation_errors: List[str] = Field(default_factory=list)
    safe_fallbacks_applied: List[str] = Field(default_factory=list)
    is_sample: bool = False
