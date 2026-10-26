"""Pydantic schemas for Voice Telephony, Retell AI status, and agent discovery."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class VoiceAgentSummaryResponse(BaseModel):
    """Summary of a Retell voice agent for listing and selection."""
    agent_id: str
    agent_name: str
    channel: str = "voice"
    voice_id: Optional[str] = None
    response_engine_type: Optional[str] = None
    llm_id: Optional[str] = None
    user_modified_timestamp: Optional[int] = None
    is_configured_sdr: bool = False
    is_configured_inbound: bool = False

    model_config = ConfigDict(from_attributes=True)


class VoiceAgentDetailResponse(BaseModel):
    """Detailed configuration of a single Retell voice agent."""
    agent_id: str
    agent_name: str
    channel: str = "voice"
    voice_id: Optional[str] = None
    voice_model: Optional[str] = None
    language: Optional[str] = None
    responsiveness: Optional[float] = None
    interruption_sensitivity: Optional[float] = None
    enable_backchannel: Optional[bool] = None
    ambient_sound: Optional[str] = None
    response_engine: Dict[str, Any] = Field(default_factory=dict)
    post_call_analysis_data: List[Dict[str, Any]] = Field(default_factory=list)
    is_configured_sdr: bool = False
    is_configured_inbound: bool = False

    model_config = ConfigDict(from_attributes=True)


class VoiceAgentsResponse(BaseModel):
    """API response model for GET /api/v1/voice/agents."""
    configured: bool
    connected: bool
    count: int
    items: List[VoiceAgentSummaryResponse] = Field(default_factory=list)
    configured_outbound_agent_id: Optional[str] = None
    configured_inbound_agent_id: Optional[str] = None
    error: Optional[str] = None
    message: str


class VoiceStatusResponse(BaseModel):
    """API response model for GET /api/v1/voice/status."""
    configured: bool
    connected: bool
    provider: str = "retell"
    base_url: str = "https://api.retellai.com"
    outbound_agent_id: Optional[str] = None
    inbound_agent_id: Optional[str] = None
    outbound_from_number: Optional[str] = None
    outbound_agent_valid: Optional[bool] = None
    inbound_agent_valid: Optional[bool] = None
    agent_count: Optional[int] = None
    error: Optional[str] = None
    message: str


class SimulateMockCallCompletionRequest(BaseModel):
    """Request payload to deterministically complete a simulated voice call."""
    outreach_id: Optional[uuid.UUID] = Field(None, description="Outreach ID of in-flight mock call")
    call_id: Optional[str] = Field(None, description="Mock call ID beginning with 'call_mock_'")
    outcome: str = Field(
        default="INTERESTED",
        description="Simulated outcome: INTERESTED, QUALIFIED, MEETING_REQUESTED, NOT_INTERESTED, NO_ANSWER, UNAVAILABLE, DO_NOT_CONTACT",
    )
    meeting_requested: bool = False
    callback_requested: bool = False
    qualification_score: int = 85
    call_summary: Optional[str] = None
    disconnection_reason: Optional[str] = None


class SimulateMockCallCompletionResponse(BaseModel):
    """Response returned upon mock voice call completion."""
    status: str
    call_id: str
    outreach_id: Optional[str] = None
    call_status: str
    outreach_status: str
    call_outcome: str
    simulated: bool = True
    duplicate: bool = False
    followup_email_created: bool = False
    followup_email_id: Optional[str] = None
    followup_status: Optional[str] = None
    followup_reason: Optional[str] = None
    message: str

