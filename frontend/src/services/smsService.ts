/**
 * Client service for Twilio SMS integration, phone validation, and segment preview.
 */

export interface SMSConfigStatus {
  configured: boolean;
  enabled: boolean;
  live_sending_allowed: boolean;
  provider: string;
  from_number_configured: boolean;
  mode: string;
  message: string;
}

export interface PhoneValidationResult {
  is_valid: boolean;
  raw_phone: string;
  formatted_phone: string;
  error_message?: string | null;
}

export interface SMSPreviewResult {
  rendered_body: string;
  character_count: number;
  segment_count: number;
  encoding: "GSM-7" | "UCS-2";
  remaining_in_segment: number;
  max_per_segment: number;
  unresolved_placeholders: string[];
  phone_validation: PhoneValidationResult;
  consent_eligible: boolean;
  consent_reason?: string | null;
}

// GSM 7-bit character sets
const GSM_7BIT_BASIC =
  "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?" +
  "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ`¿abcdefghijklmnopqrstuvwxyzäöñüà";
const GSM_7BIT_EXTENDED = "|^€{}[~]\\\f";
const GSM_7BIT_SET = new Set((GSM_7BIT_BASIC + GSM_7BIT_EXTENDED).split(""));

/**
 * Client-side calculation of SMS character count and segments
 */
export function estimateSMSSegments(body: string): {
  characterCount: number;
  segmentCount: number;
  encoding: "GSM-7" | "UCS-2";
  remainingInSegment: number;
  maxPerSegment: number;
} {
  if (!body) {
    return {
      characterCount: 0,
      segmentCount: 0,
      encoding: "GSM-7",
      remainingInSegment: 160,
      maxPerSegment: 160,
    };
  }

  const isGsm = body.split("").every((ch) => GSM_7BIT_SET.has(ch));

  if (isGsm) {
    const charCount = body
      .split("")
      .reduce((sum, ch) => sum + (GSM_7BIT_EXTENDED.includes(ch) ? 2 : 1), 0);

    if (charCount <= 160) {
      return {
        characterCount: charCount,
        segmentCount: charCount > 0 ? 1 : 0,
        encoding: "GSM-7",
        remainingInSegment: 160 - charCount,
        maxPerSegment: 160,
      };
    } else {
      const segmentCount = Math.ceil(charCount / 153);
      const usedInLast = charCount % 153 || 153;
      return {
        characterCount: charCount,
        segmentCount,
        encoding: "GSM-7",
        remainingInSegment: 153 - usedInLast,
        maxPerSegment: 153,
      };
    }
  } else {
    const charCount = body.length;
    if (charCount <= 70) {
      return {
        characterCount: charCount,
        segmentCount: charCount > 0 ? 1 : 0,
        encoding: "UCS-2",
        remainingInSegment: 70 - charCount,
        maxPerSegment: 70,
      };
    } else {
      const segmentCount = Math.ceil(charCount / 67);
      const usedInLast = charCount % 67 || 67;
      return {
        characterCount: charCount,
        segmentCount,
        encoding: "UCS-2",
        remainingInSegment: 67 - usedInLast,
        maxPerSegment: 67,
      };
    }
  }
}

/**
 * Check backend Twilio SMS configuration status
 */
export async function fetchSMSConfigStatus(): Promise<SMSConfigStatus> {
  const res = await fetch("/api/sms/config-status", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch SMS configuration status: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Validate and format recipient phone number to E.164
 */
export async function validatePhoneNumber(phone: string): Promise<PhoneValidationResult> {
  const res = await fetch("/api/sms/validate-phone", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) {
    throw new Error(`Failed to validate phone: HTTP ${res.status}`);
  }
  return res.json();
}

/**
 * Preview rendered SMS message with personalization and segment calculations
 */
export async function previewSMSMessage(params: {
  body: string;
  contactId?: string;
  leadId?: string;
  sampleData?: Record<string, any>;
}): Promise<SMSPreviewResult> {
  const res = await fetch("/api/sms/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      body: params.body,
      contact_id: params.contactId || undefined,
      lead_id: params.leadId || undefined,
      sample_data: params.sampleData,
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to preview SMS: HTTP ${res.status}`);
  }
  return res.json();
}
