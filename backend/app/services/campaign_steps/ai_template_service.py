"""AI-assisted email template generation service using AWS Bedrock and Claude Sonnet 4.5."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.schemas.email_template import AIEmailGenerateRequest, AIEmailGenerateResponse

logger = logging.getLogger(__name__)


class AITemplateError(Exception):
    """Base exception for AI template operations."""
    pass


class AITemplateConfigurationError(AITemplateError):
    """Raised when AWS Bedrock or AI credentials are not configured."""
    pass


class AITemplateGenerationError(AITemplateError):
    """Raised when Bedrock fails to generate content."""
    pass


def _get_bedrock_client() -> Any:
    """
    Initializes boto3 Bedrock Runtime client using established credential-resolution conventions.
    Prioritizes dedicated AI credentials (AWS_ACCESS_KEY_ID_AI), falling back to standard AWS credentials.
    """
    key_id = settings.AWS_ACCESS_KEY_ID_AI or settings.AWS_ACCESS_KEY_ID
    secret = settings.AWS_SECRET_ACCESS_KEY_AI or settings.AWS_SECRET_ACCESS_KEY

    if not key_id or not secret or not settings.BEDROCK_REGION:
        raise AITemplateConfigurationError(
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


def _build_system_prompt() -> str:
    """Builds system guidance grounded in B2B sales/marketing best practices and supported personalization tokens."""
    return """You are an expert B2B sales and marketing email copywriter for Agile Sales & Marketing.
Generate compelling, high-converting cold outreach email copy.

CRITICAL PERSONALIZATION TOKEN RULES:
You MUST incorporate relevant variables from the approved set:
- {contact.first_name} : Prospect's first name
- {contact.last_name} : Prospect's last name
- {contact.company} : Prospect's company name
- {contact.job_title} : Prospect's title/role
- {sender_name} : Sender's representative name
- {sender_company_name} : Sender's company name
- {booking_link} : Canonical placeholder for scheduling a briefing / meeting

CRITICAL CALL-TO-ACTION AND BOOKING LINK RULE:
Every email MUST include a clear call-to-action requesting a meeting/briefing using the canonical token {booking_link} as the scheduling destination (e.g., 'You can book a convenient 15-minute briefing directly on my calendar: {booking_link}').
NEVER invent, hallucinate, or hardcode external booking URLs or websites—always use the exact canonical token {booking_link}.

CRITICAL CONSTRAINTS:
1. Do NOT invent new placeholder tokens outside this approved list.
2. The subject line must be punchy, relevant, and under 60 characters.
3. The email body should be concise (75 to 150 words), focused on value proposition, and end with the {booking_link} call-to-action.
4. Output MUST be valid JSON with strictly two keys: "subject" and "body".
No markdown wrapping, no conversational prefix or suffix.

JSON Schema:
{
  "subject": "String with subject line",
  "body": "String with email body including line breaks and variables"
}
"""


def _build_user_prompt(request: AIEmailGenerateRequest) -> str:
    """Constructs user prompt incorporating user objective, campaign context, audience, and tone."""
    parts = []
    if request.campaign_name:
        parts.append(f"Campaign Context: {request.campaign_name.strip()}")
    parts.append(f"Email Objective: {request.email_objective.strip()}")
    if request.target_audience:
        parts.append(f"Target Audience / Persona: {request.target_audience.strip()}")
    if request.tone:
        parts.append(f"Desired Tone: {request.tone.strip()}")
    if request.call_to_action:
        parts.append(f"Call to Action: {request.call_to_action.strip()}")

    parts.append(
        "\nGenerate the email subject line and email body according to these parameters. "
        "Ensure {contact.first_name}, {contact.company}, and the scheduling CTA {booking_link} are naturally integrated."
    )
    return "\n".join(parts)


def _parse_llm_json(raw_text: str) -> Dict[str, str]:
    """Extracts subject and body from LLM output, with defensive JSON extraction and text heuristics fallback."""
    text = raw_text.strip()

    # Strip markdown code blocks if wrapped
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # Attempt standard JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "subject" in data and "body" in data:
            return {"subject": str(data["subject"]).strip(), "body": str(data["body"]).strip()}
    except json.JSONDecodeError:
        pass

    # Fallback heuristic: search for "Subject:" line and remainder as body
    subject_match = re.search(r"^(?:Subject|subject):\s*(.+)$", text, flags=re.MULTILINE)
    if subject_match:
        subject = subject_match.group(1).strip()
        body = text[subject_match.end():].strip()
        body = re.sub(r"^(?:Body|body):\s*", "", body).strip()
        return {"subject": subject, "body": body}

    # Ultimate fallback: first line as subject, remainder as body
    lines = text.split("\n", 1)
    subject = lines[0].strip() if lines else "Connecting regarding {contact.company}"
    body = lines[1].strip() if len(lines) > 1 else text
    return {"subject": subject, "body": body}


def generate_email_template(
    request: AIEmailGenerateRequest,
    force_mock: bool = False,
) -> AIEmailGenerateResponse:
    """
    Generates an email subject and body using AWS Bedrock (Claude Sonnet 4.5).
    If force_mock is True, returns a deterministic high-quality mock response without calling AWS.
    """
    # 1. Deterministic Mock Mode for automated tests or explicitly mocked execution
    if force_mock:
        company_tag = "{contact.company}"
        first_name_tag = "{contact.first_name}"
        job_title_tag = "{contact.job_title}"
        tone = (request.tone or "professional").lower()

        if "casual" in tone:
            mock_subject = f"Quick question regarding {company_tag}"
            mock_body = (
                f"Hey {first_name_tag},\n\n"
                f"I came across your work as {job_title_tag} at {company_tag} and wanted to reach out.\n\n"
                f"We help teams tackle outreach efficiency without the usual friction. "
                f"{request.call_to_action or 'Would you be open to a 10-minute chat next Tuesday?'}\n\n"
                f"Feel free to grab time directly on my calendar here: {{booking_link}}\n\n"
                f"Best,\n{{sender_name}}\n{{sender_company_name}}"
            )
        else:
            mock_subject = f"Optimizing outreach strategy for {company_tag}"
            mock_body = (
                f"Hi {first_name_tag},\n\n"
                f"I noticed your operational role as {job_title_tag} at {company_tag}.\n\n"
                f"Our platform accelerates B2B sales coordination and campaign velocity while keeping sequences strictly compliant.\n\n"
                f"{request.call_to_action or 'Would you have 15 minutes this week for a brief briefing?'}\n\n"
                f"You can pick a convenient time directly on my calendar: {{booking_link}}\n\n"
                f"Best regards,\n{{sender_name}}\n{{sender_company_name}}"
            )

        return AIEmailGenerateResponse(
            subject=mock_subject,
            body=mock_body,
            model_used="us.anthropic.claude-sonnet-4-5-20250929-v1:0 (mock)",
            ai_provider="bedrock",
            is_mock=True,
        )

    # 2. Production Bedrock Invocation
    client = _get_bedrock_client()
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(request)

    try:
        response = client.converse(
            modelId=settings.BEDROCK_DEFAULT_MODEL_ID,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_prompt}],
                }
            ],
            system=[{"text": system_prompt}],
            inferenceConfig={
                "temperature": settings.BEDROCK_TEMPERATURE,
                "maxTokens": settings.BEDROCK_MAX_TOKENS,
            },
        )

        output_message = response.get("output", {}).get("message", {})
        content_blocks = output_message.get("content", [])
        raw_text = "".join(b.get("text", "") for b in content_blocks if "text" in b)

        if not raw_text.strip():
            raise AITemplateGenerationError("AWS Bedrock returned an empty response.")

        parsed = _parse_llm_json(raw_text)

        return AIEmailGenerateResponse(
            subject=parsed["subject"],
            body=parsed["body"],
            model_used=settings.BEDROCK_DEFAULT_MODEL_ID,
            ai_provider="bedrock",
            is_mock=False,
        )

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = e.response.get("Error", {}).get("Message", str(e))
        logger.error("AWS Bedrock ClientError (%s): %s", error_code, error_msg)
        raise AITemplateGenerationError(f"Bedrock service error ({error_code}): {error_msg}") from e
    except BotoCoreError as e:
        logger.error("AWS Bedrock BotoCoreError: %s", str(e))
        raise AITemplateGenerationError(f"AWS connection error: {str(e)}") from e
    except Exception as e:
        logger.error("Unexpected error in AI email generation: %s", str(e))
        raise AITemplateGenerationError(f"AI generation failed: {str(e)}") from e
