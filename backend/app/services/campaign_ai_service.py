"""
AI Campaign Draft Generator Service.

Generates complete, editable B2B multi-touch campaign workflows from short natural language descriptions.
Integrates with AWS Bedrock (Claude Sonnet 4.5) with strict workflow schema validation,
tenant channel entitlement checks, personalization token safety, and deterministic test mocking.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign import Campaign
from app.schemas.campaign_ai import (
    AICampaignDraftRequest,
    AICampaignDraftResponse,
    FilteredChannelReason,
)
from app.schemas.workflow import (
    KNOWN_TEMPLATE_VARIABLES,
    SUPPORTED_CONDITION_TYPES,
    SUPPORTED_WORKFLOW_NODE_TYPES,
    WorkflowConfig,
    WorkflowEdge,
    WorkflowNode,
    WorkflowValidationResult,
)
from app.services.campaign_steps.ai_template_service import (
    AITemplateConfigurationError,
    AITemplateGenerationError,
)
from app.services.campaign_steps.template_renderer import find_unresolved_placeholders
from app.services.entitlements_service import get_tenant_channel_capabilities
from app.services.workflow_service import save_campaign_workflow, validate_workflow

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class AICampaignDraftError(Exception):
    """Base exception for AI campaign draft generation."""
    pass


class AICampaignConfigurationError(AICampaignDraftError):
    """Raised when AI provider credentials or model settings are unconfigured."""
    pass


class AICampaignValidationError(AICampaignDraftError):
    """Raised when generated AI workflow graph fails domain validation."""
    pass


# ── Bedrock Runtime Helper ────────────────────────────────────────────────────

def _get_bedrock_client() -> Any:
    """Initializes Bedrock Runtime client using configured AI or standard AWS credentials."""
    key_id = settings.AWS_ACCESS_KEY_ID_AI or settings.AWS_ACCESS_KEY_ID
    secret = settings.AWS_SECRET_ACCESS_KEY_AI or settings.AWS_SECRET_ACCESS_KEY

    if not key_id or not secret or not settings.BEDROCK_REGION:
        raise AICampaignConfigurationError(
            "AWS Bedrock credentials are not configured in the application environment. "
            "Please configure AWS_ACCESS_KEY_ID_AI or AWS_ACCESS_KEY_ID."
        )

    boto_config = Config(
        read_timeout=settings.BEDROCK_READ_TIMEOUT,
        connect_timeout=settings.BEDROCK_CONNECT_TIMEOUT,
        retries={"max_attempts": 3, "mode": "standard"},
    )

    return boto3.client(
        "bedrock-runtime",
        region_name=settings.BEDROCK_REGION,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=boto_config,
    )


# ── Channel Entitlement Audit ─────────────────────────────────────────────────

def filter_requested_channels(
    db: Session,
    org_id: uuid.UUID,
    requested_channels: List[str],
) -> Tuple[List[str], List[FilteredChannelReason]]:
    """
    Audits requested channels against tenant entitlements, provider configuration,
    and platform capabilities. Ensures voice steps are only included when both unlocked and enabled.
    """
    capabilities = get_tenant_channel_capabilities(db, org_id)
    unlocked_channels: Set[str] = {
        c.channel for c in capabilities.channels if c.is_unlocked
    }
    # Email is always included on base tier
    unlocked_channels.add("email")

    allowed_channels: List[str] = []
    filtered_out: List[FilteredChannelReason] = []

    for raw_ch in requested_channels:
        ch = raw_ch.strip().lower()

        # 1. Unsupported channel types (e.g. LinkedIn, Twitter, Direct Ad)
        if ch not in SUPPORTED_WORKFLOW_NODE_TYPES:
            filtered_out.append(
                FilteredChannelReason(
                    channel=ch,
                    reason=f"Channel '{ch}' is not an automated workflow step type in this platform.",
                )
            )
            continue

        # 2. Voice specific check: Requires both entitlement unlock and RETELL_ENABLED / valid agent
        if ch == "voice":
            is_entitled = "voice" in unlocked_channels
            is_voice_enabled = bool(settings.RETELL_ENABLED or settings.is_retell_configured)
            if not is_entitled:
                filtered_out.append(
                    FilteredChannelReason(
                        channel=ch,
                        reason="AI Voice SDR calls require an administrative channel upgrade for this organization.",
                    )
                )
            elif not is_voice_enabled:
                filtered_out.append(
                    FilteredChannelReason(
                        channel=ch,
                        reason="AI Voice SDR calls are disabled in environment configuration (RETELL_ENABLED=False).",
                    )
                )
            else:
                allowed_channels.append(ch)
            continue

        # 3. SMS check
        if ch == "sms":
            if "sms" not in unlocked_channels:
                filtered_out.append(
                    FilteredChannelReason(
                        channel=ch,
                        reason="SMS outreach requires an administrative channel upgrade for this organization.",
                    )
                )
            else:
                allowed_channels.append(ch)
            continue

        # 4. Physical Mail check
        if ch == "physical_mail":
            if "physical_mail" not in unlocked_channels:
                filtered_out.append(
                    FilteredChannelReason(
                        channel=ch,
                        reason="Physical direct mail requires an administrative channel upgrade for this organization.",
                    )
                )
            else:
                allowed_channels.append(ch)
            continue

        # 5. Email and standard step types
        if ch in unlocked_channels:
            allowed_channels.append(ch)
        else:
            filtered_out.append(
                FilteredChannelReason(
                    channel=ch,
                    reason=f"Channel '{ch}' is locked or requires an entitlement upgrade.",
                )
            )

    # Guarantee at least email is enabled
    if not allowed_channels:
        allowed_channels = ["email"]

    return list(dict.fromkeys(allowed_channels)), filtered_out


# ── System Prompt Builder ─────────────────────────────────────────────────────

def _build_system_prompt(allowed_channels: List[str]) -> str:
    """Builds Claude Sonnet system prompt with strict schema constraints."""
    channels_str = ", ".join(allowed_channels)
    supported_conditions_str = ", ".join(sorted(list(SUPPORTED_CONDITION_TYPES.keys())))

    return f"""You are an elite B2B sales automation architect for Agile Sales & Marketing.
Your task is to generate an executable multi-touch campaign workflow based on user specifications.

ALLOWED CHANNELS FOR THIS CAMPAIGN:
{channels_str}
You MUST NOT output steps for channels outside this permitted list.

SUPPORTED WORKFLOW NODE TYPES:
- start : Root trigger node (exactly one required)
- email : Email outreach (requires 'subject' and 'body')
- wait : Delay before next step (requires 'duration' positive integer and 'unit': 'days' or 'hours')
- condition : Branching node based on prospect engagement (requires 'condition_type')
- voice : Retell AI voice SDR call (ONLY if 'voice' is in allowed channels)
- sms : Mobile text outreach (ONLY if 'sms' is in allowed channels)
- physical_mail : Poplar direct mail postcard/letter (ONLY if 'physical_mail' is in allowed channels)

SUPPORTED CONDITION TYPES (condition_type):
{supported_conditions_str}

CRITICAL PERSONALIZATION TOKENS:
Only use approved variables:
- {{contact.first_name}} : Prospect first name
- {{contact.last_name}} : Prospect last name
- {{contact.company}} : Prospect company name
- {{contact.job_title}} : Prospect job title
- {{sender_name}} : Sender name
- {{booking_link}} : Canonical scheduling link placeholder

CRITICAL CTA & BOOKING LINK RULE:
Every email or SMS requesting a meeting MUST use {{booking_link}} as the scheduling destination.
NEVER invent, hallucinate, or hardcode external URLs (such as calendly.com, https://...). Always use {{booking_link}}.

CAMPAIGN STRUCTURE REQUIREMENTS:
1. Exactly one 'start' node.
2. Step 1 should be an initial outreach step (e.g. Email).
3. Insert appropriate 'wait' steps between outreach touches (e.g. 3 days).
4. Include conditional branches to separate positive interest from non-responses:
   - 'email_replied' or 'meeting_requested': Positive engagement branch.
   - 'email_not_replied': Sequence progression branch.
   - 'contact_opted_out': Sequence halt / exclusion branch.
5. Provide meaningful, conversion-focused subject lines and email bodies. Keep email and message copy concise, punchy, and under 150 words per touch.

OUTPUT FORMAT:
Return strictly a valid JSON object with the following top-level keys:
- "campaign_name": String (concise, professional campaign title)
- "summary": String (1-2 sentence overview of sequence strategy)
- "workflow": Object containing:
  - "nodes": Array of WorkflowNode objects (id, type, title, config, position: {{x, y}})
  - "edges": Array of WorkflowEdge objects (id, source, target, label)

No markdown wrapping, no conversational prefix or suffix. Return strictly valid, parseable JSON.
"""


def _build_user_prompt(
    request: AICampaignDraftRequest,
    allowed_channels: List[str],
) -> str:
    """Builds prompt parameters from user request."""
    return f"""Campaign Context & Description:
{request.description.strip()}

Target Audience / Persona:
{request.target_audience.strip()}

Primary Objective:
{request.objective.strip()}

Tone:
{request.tone or 'consultative'}

Sequence Timing:
- Suggested Duration: {request.campaign_duration_days or 14} days
- Follow-up Interval: {request.followup_interval_days or 3} days between touches

Active Allowed Channels:
{', '.join(allowed_channels)}

Sequence Scope:
Generate a focused, clean sequence of 5 to 8 total nodes (start node, 2-3 outreach touches separated by wait steps, and 1-2 conditional engagement checks). Keep copy punchy and under 100 words per message.

Generate the complete workflow JSON now."""


# ── Deterministic Mock Generator ──────────────────────────────────────────────

def _generate_mock_draft(
    request: AICampaignDraftRequest,
    allowed_channels: List[str],
) -> Dict[str, Any]:
    """
    Generates a deterministic, compliant campaign workflow draft for testing
    or fallback when Bedrock is in mock mode.
    """
    interval = request.followup_interval_days or 3
    has_voice = "voice" in allowed_channels
    has_sms = "sms" in allowed_channels
    has_mail = "physical_mail" in allowed_channels

    nodes: List[WorkflowNode] = []
    edges: List[WorkflowEdge] = []

    # 1. Start Node
    nodes.append(
        WorkflowNode(
            id="start-node",
            type="start",
            title="Campaign Trigger",
            config={},
            position={"x": 250, "y": 40},
        )
    )

    # 2. Step 1: Initial Email Outreach
    step1_id = "step-email-1"
    nodes.append(
        WorkflowNode(
            id=step1_id,
            type="email",
            title="Step 1: Introduction & Value Proposition",
            config={
                "step_number": 1,
                "subject": f"Accelerating pipeline results for {{contact.company}}",
                "body": (
                    f"Hi {{contact.first_name}},\n\n"
                    f"I noticed your focus as {{contact.job_title}} at {{contact.company}}.\n\n"
                    f"We help organizations achieve their {request.objective.lower()} by streamlining sales and marketing alignment.\n\n"
                    f"Would you be open to a 15-minute briefing this week? You can pick a convenient time on my calendar: {{booking_link}}\n\n"
                    f"Best regards,\n{{sender_name}}"
                ),
                "delay_days": 0,
                "delay_hours": 0,
                "is_active": True,
            },
            position={"x": 250, "y": 160},
        )
    )
    edges.append(
        WorkflowEdge(id="edge-start-step1", source="start-node", target=step1_id, label="Start")
    )

    # 3. Wait Step
    wait1_id = "wait-step-1"
    nodes.append(
        WorkflowNode(
            id=wait1_id,
            type="wait",
            title=f"Wait {interval} Days",
            config={"duration": interval, "unit": "days"},
            position={"x": 250, "y": 280},
        )
    )
    edges.append(
        WorkflowEdge(id="edge-step1-wait1", source=step1_id, target=wait1_id, label="After Send")
    )

    # 4. Condition: Reply Check
    cond_reply_id = "cond-reply-check"
    nodes.append(
        WorkflowNode(
            id=cond_reply_id,
            type="condition",
            title="Check: Prospect Replied?",
            config={"condition_type": "email_replied"},
            position={"x": 250, "y": 400},
        )
    )
    edges.append(
        WorkflowEdge(id="edge-wait1-cond", source=wait1_id, target=cond_reply_id, label="Evaluate")
    )

    # 5. Positive Branch: Meeting Requested / Replied
    positive_id = "step-positive-meeting"
    nodes.append(
        WorkflowNode(
            id=positive_id,
            type="email",
            title="Positive Response: Meeting Booking Details",
            config={
                "step_number": 2,
                "subject": f"Re: Meeting details for {{contact.company}}",
                "body": (
                    f"Hi {{contact.first_name}},\n\n"
                    f"Great connecting! Here is my direct scheduling link to lock in a time: {{booking_link}}\n\n"
                    f"Looking forward to speaking.\n\n"
                    f"Best regards,\n{{sender_name}}"
                ),
                "is_active": True,
            },
            position={"x": 100, "y": 520},
        )
    )
    edges.append(
        WorkflowEdge(
            id="edge-cond-positive",
            source=cond_reply_id,
            target=positive_id,
            label="Replied / Interested",
        )
    )

    # 6. Negative / No Reply Branch: Follow-up touch
    step2_y = 520
    if has_voice:
        step2_id = "step-voice-2"
        step2_node = WorkflowNode(
            id=step2_id,
            type="voice",
            title="Step 2: AI Voice SDR Call",
            config={
                "agent_id": settings.RETELL_AGENT_ID or "agent_sdr_default",
                "prompt_context": f"Follow-up regarding {request.objective} for {{contact.company}}",
            },
            position={"x": 400, "y": step2_y},
        )
    elif has_sms:
        step2_id = "step-sms-2"
        step2_node = WorkflowNode(
            id=step2_id,
            type="sms",
            title="Step 2: SMS Follow-Up",
            config={
                "body": f"Hi {{contact.first_name}}, following up on my email regarding {{contact.company}}. Quick briefing link: {{booking_link}}",
            },
            position={"x": 400, "y": step2_y},
        )
    elif has_mail:
        step2_id = "step-mail-2"
        step2_node = WorkflowNode(
            id=step2_id,
            type="physical_mail",
            title="Step 2: Direct Mail Postcard",
            config={
                "campaign_id": settings.POPLAR_DEFAULT_CAMPAIGN_ID or "cmp_default",
                "creative_id": settings.POPLAR_DEFAULT_CREATIVE_ID,
            },
            position={"x": 400, "y": step2_y},
        )
    else:
        step2_id = "step-email-2"
        step2_node = WorkflowNode(
            id=step2_id,
            type="email",
            title="Step 2: Follow-up Case Study",
            config={
                "step_number": 3,
                "subject": f"Resource for {{contact.company}}: {request.objective}",
                "body": (
                    f"Hi {{contact.first_name}},\n\n"
                    f"Following up on my previous note. We recently helped a peer team achieve measurable pipeline lift.\n\n"
                    f"You can grab 10 minutes on my calendar if this aligns with your priorities: {{booking_link}}\n\n"
                    f"Best regards,\n{{sender_name}}"
                ),
                "is_active": True,
            },
            position={"x": 400, "y": step2_y},
        )

    nodes.append(step2_node)
    edges.append(
        WorkflowEdge(
            id="edge-cond-noreply",
            source=cond_reply_id,
            target=step2_id,
            label="No Reply",
        )
    )

    # 7. Opt-Out Safety Exit Condition
    cond_optout_id = "cond-optout-check"
    nodes.append(
        WorkflowNode(
            id=cond_optout_id,
            type="condition",
            title="Safety Exit: Opt-Out Check",
            config={"condition_type": "contact_opted_out"},
            position={"x": 400, "y": step2_y + 120},
        )
    )
    edges.append(
        WorkflowEdge(
            id="edge-step2-optout",
            source=step2_id,
            target=cond_optout_id,
            label="Opt-Out Filter",
        )
    )

    clean_name = f"{request.target_audience.split(',')[0].strip()} - {request.objective.split('.')[0].strip()}"
    if len(clean_name) > 60:
        clean_name = clean_name[:57] + "..."

    return {
        "campaign_name": clean_name or "AI-Generated Outbound Campaign",
        "summary": (
            f"Multi-touch cadence targeting {request.target_audience} with an initial touch, "
            f"positive-response routing, and automated follow-up across {', '.join(allowed_channels)}."
        ),
        "workflow": {
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump() for e in edges],
        },
    }


# ── AI Campaign Generator Service ─────────────────────────────────────────────

class AICampaignGeneratorService:
    """
    Orchestrates AI campaign draft generation with AWS Bedrock, tenant channel
    capability gating, schema validation, and safe draft persistence.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_campaign_draft(
        self,
        org_id: uuid.UUID,
        request: AICampaignDraftRequest,
        force_mock: bool = False,
    ) -> AICampaignDraftResponse:
        """
        Generates an editable campaign draft from a short natural language description.

        Enforces:
        1. Tenant channel entitlement gating (voice steps require unlocked entitlement + RETELL_ENABLED).
        2. Prompt construction with anti-hallucination rules for booking URLs.
        3. Bedrock Converse invocation with Claude Sonnet 4.5.
        4. Strict WorkflowConfig deserialization and domain validation.
        5. Optional draft persistence in database (status="draft").
        """
        # 1. Channel Entitlement & Configuration Audit
        allowed_channels, filtered_out = filter_requested_channels(
            db=self.db,
            org_id=org_id,
            requested_channels=request.channels,
        )

        # 2. Generate Content (Deterministic Mock Mode or Live Bedrock)
        if force_mock:
            raw_data = _generate_mock_draft(request, allowed_channels)
            model_used = "us.anthropic.claude-sonnet-4-5-20250929-v1:0 (mock)"
            is_mock = True
        else:
            client = _get_bedrock_client()
            system_prompt = _build_system_prompt(allowed_channels)
            user_prompt = _build_user_prompt(request, allowed_channels)

            try:
                response = client.converse(
                    modelId=settings.BEDROCK_DEFAULT_MODEL_ID,
                    messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                    system=[{"text": system_prompt}],
                    inferenceConfig={
                        "temperature": settings.BEDROCK_TEMPERATURE,
                        "maxTokens": settings.BEDROCK_MAX_TOKENS,
                    },
                )
                output_message = response.get("output", {}).get("message", {})
                content_blocks = output_message.get("content", [])
                raw_text = "".join(b.get("text", "") for b in content_blocks if "text" in b).strip()

                if not raw_text:
                    raise AICampaignGenerationError("AWS Bedrock returned an empty response.")

                # Clean markdown blocks if present
                if raw_text.startswith("```"):
                    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
                    raw_text = re.sub(r"\s*```$", "", raw_text).strip()

                raw_data = json.loads(raw_text)
                model_used = settings.BEDROCK_DEFAULT_MODEL_ID
                is_mock = False

            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Failed to parse Bedrock JSON for campaign draft: %s", e)
                raise AICampaignValidationError(f"AI generated invalid JSON structure: {e}") from e
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                error_msg = e.response.get("Error", {}).get("Message", str(e))
                logger.error("Bedrock ClientError (%s): %s", error_code, error_msg)
                raise AICampaignGenerationError(f"Bedrock service error ({error_code}): {error_msg}") from e
            except BotoCoreError as e:
                logger.error("Bedrock BotoCoreError: %s", str(e))
                raise AICampaignGenerationError(f"AWS connection error: {e}") from e

        # 3. Deserialize WorkflowConfig
        wf_data = raw_data.get("workflow", {})
        try:
            nodes = [WorkflowNode(**n) for n in wf_data.get("nodes", [])]
            edges = [WorkflowEdge(**e) for e in wf_data.get("edges", [])]
            workflow_config = WorkflowConfig(nodes=nodes, edges=edges)
        except Exception as exc:
            logger.error("Failed to construct WorkflowConfig from AI payload: %s", exc)
            raise AICampaignValidationError(f"Invalid workflow graph schema: {exc}") from exc

        # 4. Strict Real-World Workflow Validation
        validation = validate_workflow(workflow_config)

        # 5. Sanitize and Strip Hallucinated External URLs
        # Replace any literal http/https URLs in email/sms steps with canonical {booking_link}
        for node in workflow_config.nodes:
            if node.type in ("email", "sms"):
                cfg = node.config or {}
                for field_key in ("subject", "body"):
                    val = cfg.get(field_key)
                    if val and isinstance(val, str):
                        # Detect hallucinated calendly or external links
                        sanitized = re.sub(
                            r"https?://(?:www\.)?(?:calendly|cal\.com|zoom|meet)[^\s)]+",
                            "{booking_link}",
                            val,
                            flags=re.IGNORECASE,
                        )
                        cfg[field_key] = sanitized

        # Re-run validation after link sanitization
        validation = validate_workflow(workflow_config)

        # 6. Save as Draft if Requested
        saved_campaign_id: Optional[uuid.UUID] = None
        campaign_name = str(raw_data.get("campaign_name") or f"{request.target_audience} Outreach").strip()
        summary = str(raw_data.get("summary") or request.description).strip()

        if request.save_as_draft:
            campaign = Campaign(
                id=uuid.uuid4(),
                organization_id=org_id,
                name=campaign_name,
                type=request.campaign_type or "sales_outbound",
                status="draft",  # Strictly draft status, never active
                description=request.description,
            )
            self.db.add(campaign)
            self.db.flush()

            # Synchronize workflow config and steps safely
            save_campaign_workflow(
                db=self.db,
                org_id=org_id,
                campaign_id=campaign.id,
                workflow_config=workflow_config,
                description=request.description,
            )
            self.db.commit()
            saved_campaign_id = campaign.id

        return AICampaignDraftResponse(
            campaign_id=saved_campaign_id,
            campaign_name=campaign_name,
            objective=request.objective,
            target_audience=request.target_audience,
            summary=summary,
            channels_used=allowed_channels,
            channels_filtered_out=filtered_out,
            workflow_config=workflow_config,
            validation=validation,
            model_used=model_used,
            ai_provider="bedrock",
            is_mock=is_mock,
        )
