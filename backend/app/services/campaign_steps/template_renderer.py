"""Template rendering engine for campaign email step content (Step 9)."""
from __future__ import annotations

import html
import re
from typing import List, Optional

from app.models.crm import Company, Contact

DEFAULT_SENDER_NAME = "Agile Sales & Marketing"

# Regex matching double braces {{var}} and single braces {var}
# with optional leading/trailing whitespace inside braces.
PLACEHOLDER_PATTERN = re.compile(
    r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}|\{\s*([a-zA-Z0-9_.]+)\s*\}"
)


def find_unresolved_placeholders(text: Optional[str]) -> List[str]:
    """
    Returns a deduplicated list of all placeholder strings remaining in the text.
    For example: ['{contact.company}', '{{bonus_code}}'].
    """
    if not text:
        return []
    placeholders: List[str] = []
    for match in PLACEHOLDER_PATTERN.finditer(text):
        token = match.group(0)
        if token not in placeholders:
            placeholders.append(token)
    return placeholders


def ensure_booking_cta(
    body: Optional[str],
    booking_link_or_url: Optional[str] = None,
) -> Optional[str]:
    """
    Ensures that every email body contains a 'Book a Meeting' CTA.
    If the body already contains '{booking_link}', '{{booking_link}}', or the configured
    booking destination URL, it returns the body unmodified (preventing duplicate CTAs).
    Otherwise, appends a clean, formatted CTA block before sign-off or at the end.
    """
    if body is None:
        return None
    if not body.strip():
        return body

    target_link = (booking_link_or_url or "{booking_link}").strip()

    # 1. Check if canonical token {booking_link} or {booking_url} is already present
    if re.search(r"\{\{\s*booking_(?:link|url)\s*\}\}|\{\s*booking_(?:link|url)\s*\}", body, flags=re.IGNORECASE):
        return body

    # 2. Check if the concrete URL is already present in the body
    if booking_link_or_url and booking_link_or_url != "{booking_link}":
        if booking_link_or_url.lower() in body.lower():
            return body

    # 3. Check for existing "Book a Meeting" anchor or labeled URL
    if re.search(r"book\s+(?:a\s+)?meeting[:\s]+https?://", body, flags=re.IGNORECASE):
        return body

    # Clean CTA block to append
    cta_block = f"\n\nBook a Meeting: {target_link}\n"

    # Insert before common closing sign-offs if present
    signoff_match = re.search(
        r"(\n\s*(?:Best regards|Warm regards|Regards|Sincerely|Thanks|Thank you|Best|Cheers)[\s,])",
        body,
        flags=re.IGNORECASE,
    )
    if signoff_match:
        idx = signoff_match.start()
        return body[:idx].rstrip() + cta_block + body[idx:].lstrip("\n")
    else:
        return body.rstrip() + cta_block


def render_email_html(
    plain_text_body: Optional[str],
    booking_url: Optional[str] = None,
) -> str:
    """
    Constructs a responsive, cleanly styled HTML email from the plain-text body:
    - Safely HTML-escapes all user content against injection attacks.
    - Formats the 'Book a Meeting' CTA as a prominent, clickable button / link.
    - Preserves plain-text line breaks, paragraphs, and formatting.
    """
    if not plain_text_body:
        return ""

    clean_booking_url = (booking_url or "").strip()
    escaped_booking_url = html.escape(clean_booking_url, quote=True) if clean_booking_url else None

    lines = plain_text_body.strip().split("\n")
    html_paragraphs: List[str] = []
    current_para: List[str] = []

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            if current_para:
                html_paragraphs.append("<br>".join(current_para))
                current_para = []
        else:
            escaped_line = html.escape(trimmed)

            # Check if this line is the dedicated Book a Meeting CTA line
            if escaped_booking_url and re.search(r"book\s+(?:a\s+)?meeting", trimmed, flags=re.IGNORECASE):
                cta_button = (
                    f'<p style="margin: 16px 0;">'
                    f'<a href="{escaped_booking_url}" '
                    f'style="display: inline-block; padding: 10px 20px; background-color: #2563eb; '
                    f'color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; '
                    f'font-size: 14px;" target="_blank" rel="noopener noreferrer">'
                    f'Book a Meeting</a></p>'
                )
                current_para.append(cta_button)
            elif escaped_booking_url and clean_booking_url in trimmed:
                # Replace the raw URL with a clickable hyperlink
                escaped_raw = html.escape(clean_booking_url)
                linked = escaped_line.replace(
                    escaped_raw,
                    f'<a href="{escaped_booking_url}" style="color: #2563eb; text-decoration: underline;" '
                    f'target="_blank" rel="noopener noreferrer">Book a Meeting</a>',
                )
                current_para.append(linked)
            else:
                current_para.append(escaped_line)

    if current_para:
        html_paragraphs.append("<br>".join(current_para))

    body_content = "\n".join(
        f'<p style="margin: 0 0 14px 0;">{p}</p>' if not p.startswith("<p") else p
        for p in html_paragraphs
    )

    return (
        '<!DOCTYPE html>\n'
        '<html>\n'
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>\n'
        '<body style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; '
        'font-size: 14px; line-height: 1.6; color: #1e293b; background-color: #ffffff; margin: 0; padding: 20px;">\n'
        f'<div style="max-width: 600px; margin: 0 auto;">\n{body_content}\n</div>\n'
        '</body>\n'
        '</html>'
    )


def render_template(
    template: Optional[str],
    contact: Optional[Contact],
    company: Optional[Company] = None,
    sender_name: Optional[str] = None,
    sender_company_name: Optional[str] = None,
    booking_link: Optional[str] = None,
    enforce_booking_cta: bool = False,
) -> Optional[str]:
    """
    Renders an email template by substituting safe predefined variables:
    Nested syntax:
      {contact.first_name}, {contact.last_name}, {contact.full_name},
      {contact.email}, {contact.company}, {contact.company_name},
      {contact.job_title}, {contact.phone}
    Flat syntax:
      {first_name}, {last_name}, {full_name}, {email},
      {company}, {company_name}, {job_title}, {phone}, {sender_name},
      {sender_company_name}, {booking_link}, {booking_url}

    Supports both single braces {var} and double braces {{var}} with optional whitespace.
    Safe fallbacks are applied when variables are missing.
    Unknown variables remain unmodified in the template string for validation guards.
    No dynamic code evaluation or eval is performed.
    """
    if template is None:
        return None
    if not template:
        return ""

    # Enforce booking CTA if requested (Requirement 2)
    result = template
    if enforce_booking_cta:
        result = ensure_booking_cta(result, booking_link or "{booking_link}")

    # Resolve company from contact relationship if not passed explicitly, enforcing tenant isolation
    resolved_company = company
    if resolved_company is None and contact is not None:
        cand = getattr(contact, "company", None)
        if cand is not None:
            contact_org = getattr(contact, "organization_id", None)
            comp_org = getattr(cand, "organization_id", None)
            if contact_org is None or comp_org is None or contact_org == comp_org:
                resolved_company = cand

    first_name = (contact.first_name or "").strip() if contact and contact.first_name else ""
    last_name = (contact.last_name or "").strip() if contact and contact.last_name else ""
    full_name_parts = [p for p in (first_name, last_name) if p]
    full_name = " ".join(full_name_parts)
    email = (contact.email or "").strip() if contact and contact.email else ""
    job_title = (
        (contact.job_title or "").strip()
        if contact and hasattr(contact, "job_title") and contact.job_title
        else ""
    )
    phone = (
        (contact.phone or "").strip()
        if contact and hasattr(contact, "phone") and contact.phone
        else ""
    )
    company_name = (
        (resolved_company.name or "").strip()
        if resolved_company and resolved_company.name
        else ""
    )

    effective_sender = (
        sender_name.strip()
        if sender_name and sender_name.strip()
        else DEFAULT_SENDER_NAME
    )
    effective_sender_company = (
        sender_company_name.strip()
        if sender_company_name and sender_company_name.strip()
        else DEFAULT_SENDER_NAME
    )

    replacements = {
        # Nested syntax (Requirement 1)
        "contact.first_name": first_name,
        "contact.last_name": last_name,
        "contact.full_name": full_name,
        "contact.email": email,
        "contact.company": company_name,
        "contact.company_name": company_name,
        "contact.job_title": job_title,
        "contact.phone": phone,
        # Flat syntax (Requirement 2)
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "company": company_name,
        "company_name": company_name,
        "job_title": job_title,
        "phone": phone,
        # Sender variables (both dot and underscore syntax)
        "sender_name": effective_sender,
        "sender.name": effective_sender,
        "sender_company_name": effective_sender_company,
        "sender.company_name": effective_sender_company,
        "sender_company": effective_sender_company,
        "sender.company": effective_sender_company,
    }

    # Add booking link replacements if provided (Requirement 1 & 4)
    if booking_link and booking_link.strip():
        clean_booking = booking_link.strip()
        replacements["booking_link"] = clean_booking
        replacements["booking_url"] = clean_booking

    # Safe contextual fallbacks before substitution (Requirement 5):
    # 1. If first_name is empty, fallback greetings like "Hi {contact.first_name}," -> "Hi there,"
    if not first_name:
        result = re.sub(
            r"\b(Hi|Hello|Hey)\s+\{\{?\s*(?:contact\.)?first_name\s*\}?\}",
            r"\1 there",
            result,
            flags=re.IGNORECASE,
        )

    # 2. If company_name is empty, omit company-specific phrase:
    # e.g. "Strategic briefing for {contact.company}" -> "Strategic briefing"
    # Note: Only clean when not surrounded by quotes (preserves tests like from '{{company_name}}')
    if not company_name:
        result = re.sub(
            r"\s+(?:at|for|with)\s+\{\{?\s*(?:contact\.)?compan(?:y|y_name)\s*\}?\}(?=[^'\"\w]|$)",
            "",
            result,
            flags=re.IGNORECASE,
        )

    # 3. Substitute all matching placeholders
    def replace_var(match: re.Match[str]) -> str:
        var_name = (match.group(1) or match.group(2)).strip().lower()
        if var_name in replacements:
            return replacements[var_name]
        return match.group(0)

    result = PLACEHOLDER_PATTERN.sub(replace_var, result)
    return result
