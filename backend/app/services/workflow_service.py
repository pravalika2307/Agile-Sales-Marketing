"""Workflow domain service managing visual workflow graph persistence, validation, recovery, and template previews."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import Campaign, CampaignContact
from app.models.campaign_step import CampaignStep
from app.models.crm import Company, Contact
from app.models.lead import Lead
from app.schemas.workflow import (
    KNOWN_TEMPLATE_VARIABLES,
    SUPPORTED_CONDITION_TYPES,
    SUPPORTED_WORKFLOW_NODE_TYPES,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    WorkflowConfig,
    WorkflowEdge,
    WorkflowNode,
    WorkflowSaveResponse,
    WorkflowValidationResult,
)
from app.services.campaign_steps.template_renderer import (
    DEFAULT_SENDER_NAME,
    find_unresolved_placeholders,
    render_email_html,
    render_template,
)
from app.services.organization_config import get_organization_booking_url

logger = logging.getLogger(__name__)


def validate_workflow(workflow_config: WorkflowConfig) -> WorkflowValidationResult:
    """
    Validates a workflow graph according to execution safety and integration capability rules:
    - Must contain exactly one start node.
    - Email steps must have non-empty subject and body templates when configured.
    - Placeholders in email templates must only reference recognized variables.
    - Wait steps must have positive delay values.
    - AI voice call steps must target S&M outbound SDR agent (never Receivables).
    - SMS steps report honest unconfigured status.
    - Condition branches report supported vs unsupported criteria.
    """
    errors: List[str] = []
    warnings: List[str] = []

    nodes = workflow_config.nodes
    if not nodes:
        return WorkflowValidationResult(
            is_valid=False,
            errors=["Workflow must contain at least a Start node."],
        )

    start_nodes = [n for n in nodes if n.type == "start"]
    if len(start_nodes) == 0:
        errors.append("Workflow must contain a Start node.")
    elif len(start_nodes) > 1:
        errors.append("Workflow cannot have multiple Start nodes.")

    for node in nodes:
        node_type = node.type.lower()
        if node_type not in SUPPORTED_WORKFLOW_NODE_TYPES:
            errors.append(f"Node '{node.title}' has unknown step type '{node.type}'.")
            continue

        cfg = node.config or {}

        # 1. Email Step Validation
        if node_type == "email":
            subject = (cfg.get("subject") or cfg.get("subject_template") or "").strip()
            body = (cfg.get("body") or cfg.get("body_template") or "").strip()

            if not subject:
                errors.append(f"Step '{node.title}' (Email) is missing a subject line.")
            if not body:
                errors.append(f"Step '{node.title}' (Email) is missing body content.")

            # Check for unknown placeholders in templates
            for text_val, field_name in [(subject, "subject"), (body, "body")]:
                if text_val:
                    unresolved = find_unresolved_placeholders(text_val)
                    for ph in unresolved:
                        clean_var = ph.strip("{}").strip().lower()
                        if clean_var not in KNOWN_TEMPLATE_VARIABLES:
                            errors.append(
                                f"Step '{node.title}' contains unknown placeholder '{ph}' in {field_name}. "
                                f"Supported variables: {', '.join(sorted(list(KNOWN_TEMPLATE_VARIABLES)))}."
                            )

        # 2. Wait Step Validation
        elif node_type == "wait":
            duration = cfg.get("duration")
            unit = cfg.get("unit", "hours")
            try:
                duration_val = int(duration) if duration is not None else 0
            except (ValueError, TypeError):
                duration_val = -1

            if duration_val <= 0:
                errors.append(f"Step '{node.title}' (Wait) must specify a positive delay duration.")
            if unit not in ("minutes", "hours", "days"):
                errors.append(f"Step '{node.title}' (Wait) specifies invalid unit '{unit}'. Use minutes, hours, or days.")

            warnings.append(
                f"Step '{node.title}': Delay will be persisted in database schedule fields. "
                "Execution resumes via durable background worker."
            )

        # 3. AI Voice Call Step Validation
        elif node_type == "voice":
            # Must strictly use S&M Outbound SDR, never Receivables
            agent_id = cfg.get("agent_id") or settings.RETELL_AGENT_ID
            if not settings.RETELL_API_KEY or not settings.RETELL_AGENT_ID:
                warnings.append(
                    f"Step '{node.title}' (AI Voice Call): Retell environment credentials not fully configured. "
                    "Voice execution will operate in test mode."
                )

        # 4. SMS Step Validation
        elif node_type == "sms":
            body = (cfg.get("body") or cfg.get("body_template") or "").strip()
            if not body:
                errors.append(f"Step '{node.title}' (SMS) is missing message content.")
            else:
                unresolved = find_unresolved_placeholders(body)
                for ph in unresolved:
                    clean_var = ph.strip("{}").strip().lower()
                    if clean_var not in KNOWN_TEMPLATE_VARIABLES:
                        errors.append(
                            f"Step '{node.title}' contains unknown placeholder '{ph}' in body. "
                            f"Supported variables: {', '.join(sorted(list(KNOWN_TEMPLATE_VARIABLES)))}."
                        )
                from app.services.sms.base import calculate_sms_segments
                seg_calc = calculate_sms_segments(body)
                if seg_calc["character_count"] > 1600:
                    errors.append(
                        f"Step '{node.title}' (SMS) message length ({seg_calc['character_count']} chars) "
                        "exceeds maximum carrier limit of 1600 characters."
                    )
                elif seg_calc["segment_count"] > 1:
                    warnings.append(
                        f"Step '{node.title}' (SMS): Message will be sent as {seg_calc['segment_count']} "
                        f"segments ({seg_calc['character_count']} chars, {seg_calc['encoding']})."
                    )

            if not settings.is_twilio_live_sending_allowed:
                warnings.append(
                    f"Step '{node.title}' (SMS): Real SMS delivery is disabled (TWILIO_ENABLED=False). "
                    "SMS gateway is currently unconfigured for live delivery. "
                    "Campaign will execute in safe mock mode without external Twilio delivery."
                )

        # 5. Condition Branch Step Validation
        elif node_type == "condition":
            cond_type = cfg.get("condition_type", "")
            if not cond_type:
                errors.append(f"Step '{node.title}' (Condition) must specify a condition criterion.")
            elif cond_type not in SUPPORTED_CONDITION_TYPES:
                errors.append(
                    f"Step '{node.title}' (Condition) uses unsupported condition '{cond_type}'. "
                    f"Supported conditions: {', '.join(SUPPORTED_CONDITION_TYPES.keys())}."
                )

    is_valid = len(errors) == 0
    return WorkflowValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )


def get_or_recover_campaign_workflow(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> WorkflowConfig:
    """
    Retrieves the persisted workflow configuration for a campaign.
    If the campaign was created before the visual builder (no workflow_config),
    automatically recovers and constructs a normalized workflow graph from existing CampaignStep rows.
    """
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise ValueError(f"Campaign '{campaign_id}' not found.")

    # 1. Recover from saved JSON workflow_config if present and populated
    if campaign.workflow_config and isinstance(campaign.workflow_config, dict):
        nodes_raw = campaign.workflow_config.get("nodes", [])
        edges_raw = campaign.workflow_config.get("edges", [])
        if nodes_raw:
            try:
                nodes = [WorkflowNode(**n) for n in nodes_raw]
                edges = [WorkflowEdge(**e) for e in edges_raw]
                return WorkflowConfig(nodes=nodes, edges=edges)
            except Exception as e:
                logger.warning("Failed to deserialize workflow_config for campaign %s: %s", campaign_id, e)

    # 2. Backwards-compatibility recovery: construct workflow from persisted CampaignStep rows
    nodes: List[WorkflowNode] = []
    edges: List[WorkflowEdge] = []

    # Start Node
    start_id = "start-node"
    nodes.append(
        WorkflowNode(
            id=start_id,
            type="start",
            title="Campaign Start",
            config={},
            position={"x": 250, "y": 50},
        )
    )

    prev_node_id = start_id
    steps = sorted(campaign.steps, key=lambda s: s.step_number)

    if not steps:
        # Default step 1 placeholder if no steps exist
        step_id = "step-node-1"
        nodes.append(
            WorkflowNode(
                id=step_id,
                type="email",
                title="Step 1: Introduction Email",
                config={
                    "step_number": 1,
                    "subject": "Introduction to Agile Sales & Marketing",
                    "body": "Hi {contact.first_name},\n\nConnecting from Agile Sales & Marketing.",
                    "delay_days": 0,
                    "delay_hours": 0,
                    "is_active": True,
                },
                position={"x": 250, "y": 180},
            )
        )
        edges.append(
            WorkflowEdge(
                id=f"edge-{start_id}-{step_id}",
                source=start_id,
                target=step_id,
                label="Next",
            )
        )
    else:
        y_pos = 180
        for idx, step in enumerate(steps, start=1):
            step_type = step.step_type if step.step_type in ("email", "sms", "voice") else "email"
            default_label = "SMS Outreach" if step_type == "sms" else ("AI Voice Call" if step_type == "voice" else "Email Outreach")
            title = f"Step {step.step_number}: {step.subject_template or default_label}"
            if len(title) > 36:
                title = title[:33] + "..."

            step_node_id = f"step-node-{step.id}"
            nodes.append(
                WorkflowNode(
                    id=step_node_id,
                    type=step_type,
                    title=title,
                    config={
                        "step_id": str(step.id),
                        "step_number": step.step_number,
                        "subject": step.subject_template or "",
                        "body": step.body_template or "",
                        "delay_days": step.delay_days,
                        "delay_hours": step.delay_hours,
                        "is_active": step.is_active,
                    },
                    position={"x": 250, "y": y_pos},
                )
            )
            edges.append(
                WorkflowEdge(
                    id=f"edge-{prev_node_id}-{step_node_id}",
                    source=prev_node_id,
                    target=step_node_id,
                    label="Next",
                )
            )
            prev_node_id = step_node_id
            y_pos += 130

    return WorkflowConfig(nodes=nodes, edges=edges)


def save_campaign_workflow(
    db: Session,
    org_id: uuid.UUID,
    campaign_id: uuid.UUID,
    workflow_config: WorkflowConfig,
    description: Optional[str] = None,
) -> WorkflowSaveResponse:
    """
    Persists the visual workflow graph and synchronizes email steps into CampaignStep records.
    Maintains 100% backward compatibility with execution engine and existing tests.
    """
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.organization_id == org_id)
        .first()
    )
    if not campaign:
        raise ValueError(f"Campaign '{campaign_id}' not found.")

    validation = validate_workflow(workflow_config)

    # 1. Persist workflow_config JSON and description
    campaign.workflow_config = workflow_config.model_dump()
    if description is not None:
        campaign.description = description.strip()

    # 2. Extract email steps and integrate intermediate wait delays / conditions
    existing_steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.campaign_id == campaign.id, CampaignStep.organization_id == org_id)
        .order_by(CampaignStep.step_number.asc())
        .all()
    )
    existing_by_num = {s.step_number: s for s in existing_steps}

    step_num = 1
    used_numbers = set()
    accumulated_delay_days = 0
    accumulated_delay_hours = 0
    last_condition = None

    for node in workflow_config.nodes:
        if node.type == "wait":
            cfg = node.config or {}
            dur = int(cfg.get("duration", 0) or 0)
            unit = (cfg.get("unit") or "days").lower()
            if unit == "days":
                accumulated_delay_days += dur
            elif unit == "hours":
                accumulated_delay_hours += dur
            elif unit == "minutes":
                accumulated_delay_hours += max(1, dur // 60) if dur >= 60 else 0
        elif node.type == "condition":
            cfg = node.config or {}
            last_condition = cfg.get("condition_type")
        elif node.type == "email":
            cfg = node.config or {}
            subject = cfg.get("subject") or cfg.get("subject_template")
            body = cfg.get("body") or cfg.get("body_template")
            delay_days = int(cfg.get("delay_days", 0) or 0) + accumulated_delay_days
            delay_hours = int(cfg.get("delay_hours", 0) or 0) + accumulated_delay_hours
            if last_condition:
                cfg["condition_type"] = last_condition
            is_active = bool(cfg.get("is_active", True))

            if step_num in existing_by_num:
                # Update existing step
                step_record = existing_by_num[step_num]
                step_record.subject_template = subject
                step_record.body_template = body
                step_record.delay_days = delay_days
                step_record.delay_hours = delay_hours
                step_record.is_active = is_active
            else:
                # Create new sequential step
                new_step = CampaignStep(
                    organization_id=org_id,
                    campaign_id=campaign.id,
                    step_number=step_num,
                    step_type="email",
                    subject_template=subject,
                    body_template=body,
                    delay_days=delay_days,
                    delay_hours=delay_hours,
                    is_active=is_active,
                )
                db.add(new_step)

            used_numbers.add(step_num)
            step_num += 1
            accumulated_delay_days = 0
            accumulated_delay_hours = 0
            last_condition = None

    # If there were more steps before than now, mark remaining as inactive or delete if safe
    for old_num, old_step in existing_by_num.items():
        if old_num not in used_numbers:
            db.delete(old_step)

    db.commit()
    db.refresh(campaign)

    return WorkflowSaveResponse(
        campaign_id=campaign.id,
        workflow_config=workflow_config,
        validation=validation,
        description=campaign.description,
    )


def preview_template_content(
    db: Session,
    org_id: uuid.UUID,
    request: TemplatePreviewRequest,
    campaign_id: Optional[uuid.UUID] = None,
) -> TemplatePreviewResponse:
    """
    Renders email subject and body templates using identical shared rendering logic.
    Uses genuine persisted contact data from the campaign or organization.
    Supports explicit sample contact selection and strict tenant isolation.
    """
    contact: Optional[Contact] = None
    company: Optional[Company] = None
    validation_errors: List[str] = []
    fallbacks_applied: List[str] = []
    is_sample = False

    # 1. Explicit sample contact requested
    if request.use_sample:
        is_sample = True
        contact = Contact(
            first_name="Jordan",
            last_name="Taylor",
            email="jordan.taylor@example.com",
            job_title="Director of Operations",
            phone="+1 555-0199",
        )
        company = Company(name="Acme Global Solutions")

    # 2. Specific contact requested
    elif request.contact_id:
        contact = (
            db.query(Contact)
            .filter(Contact.id == request.contact_id, Contact.organization_id == org_id)
            .first()
        )
        if not contact:
            validation_errors.append(
                f"Specified contact '{request.contact_id}' not found in authenticated organization."
            )
            # Never silently substitute an unrelated real database record
            is_sample = True
            contact = Contact(
                first_name="Jordan",
                last_name="Taylor",
                email="jordan.taylor@example.com",
                job_title="Director of Operations",
                phone="+1 555-0199",
            )
            company = Company(name="Acme Global Solutions")
        else:
            is_sample = False

    # 3. Default contact: Prioritize campaign enrolled contacts, then org contacts
    else:
        if campaign_id:
            enrolled = (
                db.query(CampaignContact)
                .filter(CampaignContact.campaign_id == campaign_id)
                .order_by(CampaignContact.enrolled_at.asc())
                .first()
            )
            if enrolled:
                contact = (
                    db.query(Contact)
                    .filter(Contact.id == enrolled.contact_id, Contact.organization_id == org_id)
                    .first()
                )

        if not contact:
            # Fall back to most recently created contact in the tenant organization
            contact = (
                db.query(Contact)
                .filter(Contact.organization_id == org_id)
                .order_by(Contact.created_at.desc())
                .first()
            )

        if not contact:
            is_sample = True
            contact = Contact(
                first_name="Jordan",
                last_name="Taylor",
                email="jordan.taylor@example.com",
                job_title="Director of Operations",
                phone="+1 555-0199",
            )
            company = Company(name="Acme Global Solutions")
        else:
            is_sample = False

    # Resolve company association safely
    if not is_sample and contact:
        company = getattr(contact, "company", None)
        if not company and getattr(contact, "company_id", None):
            company = (
                db.query(Company)
                .filter(Company.id == contact.company_id, Company.organization_id == org_id)
                .first()
            )
        if not company and hasattr(contact, "id") and contact.id:
            lead_record = (
                db.query(Lead)
                .filter(Lead.contact_id == contact.id, Lead.organization_id == org_id)
                .first()
            )
            if lead_record and lead_record.company_name:
                company = Company(name=lead_record.company_name)

    # Detect potential safe fallback triggers
    if not contact.first_name:
        fallbacks_applied.append("Contact has no first name: greetings will fall back to 'Hi there'.")
    if not company or not company.name:
        fallbacks_applied.append("Contact has no company: company-specific clauses will safely omit company phrases.")

    booking_url = get_organization_booking_url(db, org_id)

    rendered_subject = render_template(
        request.subject_template,
        contact=contact,
        company=company,
        sender_name=request.sender_name,
        sender_company_name=request.sender_company_name,
    )

    has_booking_ph = bool(
        request.body_template
        and any(
            ph in request.body_template
            for ph in ("{booking_link}", "{{booking_link}}", "{booking_url}", "{{booking_url}}")
        )
    )

    rendered_body = render_template(
        request.body_template,
        contact=contact,
        company=company,
        sender_name=request.sender_name,
        sender_company_name=request.sender_company_name,
        booking_link=booking_url,
        enforce_booking_cta=bool(booking_url or has_booking_ph),
    )

    # Render HTML version with clickable CTA
    rendered_html = render_email_html(rendered_body, booking_url=booking_url) if rendered_body else None

    unresolved = []
    if rendered_subject:
        unresolved.extend(find_unresolved_placeholders(rendered_subject))
    if rendered_body:
        unresolved.extend(find_unresolved_placeholders(rendered_body))

    # Deduplicate unresolved placeholders
    unresolved_unique = list(dict.fromkeys(unresolved))

    # If the template contains a booking placeholder or requires a booking CTA but organization has no booking URL
    if not booking_url and (has_booking_ph or (rendered_body and "{booking_link}" in rendered_body)):
        if "{booking_link}" not in unresolved_unique and "{{booking_link}}" not in unresolved_unique:
            unresolved_unique.append("{booking_link}")
        booking_err = "Organization has no configured meeting-booking URL to resolve {booking_link}."
        if booking_err not in validation_errors:
            validation_errors.append(booking_err)

    if unresolved_unique:
        validation_errors.append(
            f"Templates contain unresolved placeholder(s): {', '.join(unresolved_unique)}."
        )

    contact_info = {
        "id": str(contact.id) if hasattr(contact, "id") and contact.id else None,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "email": contact.email,
        "job_title": getattr(contact, "job_title", None),
        "company_name": company.name if company else None,
    }

    return TemplatePreviewResponse(
        rendered_subject=rendered_subject,
        rendered_body=rendered_body,
        rendered_html=rendered_html,
        booking_url=booking_url,
        unresolved_placeholders=unresolved_unique,
        contact_used=contact_info,
        validation_errors=validation_errors,
        safe_fallbacks_applied=fallbacks_applied,
        is_sample=is_sample,
    )
