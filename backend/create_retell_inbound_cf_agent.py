"""
Create a NEW Retell Inbound Voice Agent with Agent Type: Conversation Flow.

This creates a genuinely new agent while preserving the existing single-prompt agent
(agent_546bf2dd0fbc7377911d528156) as a reference.
"""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

RETELL_API_KEY = os.getenv("RETELL_API_KEY", "key_f8a196d2fdba0276593d95448b7e")
BASE_URL = "https://api.retellai.com"
CONVERSATION_FLOW_ID = "conversation_flow_efec35923e7c"

INBOUND_POST_CALL_ANALYSIS_DATA = [
    {
        "name": "inbound_intent",
        "type": "enum",
        "description": "Primary intent of the incoming caller.",
        "choices": [
            "sales_inquiry",
            "product_information",
            "pricing_inquiry",
            "demo_request",
            "existing_customer",
            "support_request",
            "partnership",
            "callback_request",
            "general_information",
            "human_assistance",
            "other",
        ],
    },
    {
        "name": "call_outcome",
        "type": "enum",
        "description": "Final outcome and required follow-up categorization for the call.",
        "choices": [
            "sales_inquiry",
            "demo_requested",
            "pricing_inquiry",
            "product_information",
            "support_request",
            "existing_customer",
            "callback_requested",
            "human_followup_required",
            "information_provided",
            "no_action_required",
            "do_not_contact",
            "other",
        ],
    },
    {
        "name": "caller_name",
        "type": "string",
        "description": "Full name of the caller if provided during the conversation.",
    },
    {
        "name": "caller_company",
        "type": "string",
        "description": "Company or organization the caller represents if provided.",
    },
    {
        "name": "caller_email",
        "type": "string",
        "description": "Email address provided by the caller for follow-up.",
    },
    {
        "name": "caller_phone",
        "type": "string",
        "description": "Phone number provided or confirmed by the caller for follow-up.",
    },
    {
        "name": "caller_intent",
        "type": "string",
        "description": "Concise summary of why the caller contacted the business.",
    },
    {
        "name": "call_summary",
        "type": "string",
        "description": "Comprehensive summary of the inbound call conversation and caller needs.",
    },
    {
        "name": "interest_level",
        "type": "string",
        "description": "Caller interest level: 'high', 'medium', 'low', 'none', or 'existing_customer'.",
    },
    {
        "name": "requested_followup",
        "type": "string",
        "description": "Specific follow-up action requested by caller (e.g., 'send pricing', 'schedule demo', 'support callback').",
    },
    {
        "name": "important_notes",
        "type": "string",
        "description": "Key observations, requirements, objections, or urgency notes from the call.",
    },
]


def create_inbound_cf_agent():
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "agent_name": "Agile S&M Inbound Voice Assistant - Conversation Flow",
        "response_engine": {
            "type": "conversation-flow",
            "conversation_flow_id": CONVERSATION_FLOW_ID,
            "version": 0,
        },
        "voice_id": "11labs-Lily",
        "voice_temperature": 1.0,
        "voice_speed": 1.0,
        "volume": 1.0,
        "enable_backchannel": True,
        "backchannel_frequency": 0.8,
        "backchannel_words": ["okay", "got it", "makes sense", "understood"],
        "interruption_sensitivity": 0.85,
        "responsiveness": 1.0,
        "enable_dynamic_responsiveness": True,
        "begin_message_delay_ms": 600,
        "end_call_after_silence_ms": 25000,
        "max_call_duration_ms": 600000,
        "enable_dnc_detection": True,
        "stt_mode": "accurate",
        "post_call_analysis_data": INBOUND_POST_CALL_ANALYSIS_DATA,
    }

    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        print("[1/2] Creating NEW Inbound Agent with Conversation Flow response engine...")
        resp = client.post("/create-agent", json=payload)
        if resp.status_code not in (200, 201):
            print(f"Failed to create agent: {resp.status_code} - {resp.text}")
            return None

        agent_data = resp.json()
        new_agent_id = agent_data["agent_id"]
        print(f"  --> Agent created successfully! Agent ID: {new_agent_id}")

        print("\n[2/2] Fetching and verifying agent metadata from Retell API...")
        get_resp = client.get(f"/get-agent/{new_agent_id}")
        if get_resp.status_code != 200:
            print(f"Failed to fetch created agent: {get_resp.status_code} - {get_resp.text}")
            return None

        verified_data = get_resp.json()
        engine_type = verified_data.get("response_engine", {}).get("type")
        flow_id = verified_data.get("response_engine", {}).get("conversation_flow_id")

        print("  --> Verification Details:")
        print(f"      Agent ID:             {verified_data.get('agent_id')}")
        print(f"      Agent Name:           {verified_data.get('agent_name')}")
        print(f"      Response Engine Type: {engine_type}")
        print(f"      Conversation Flow ID: {flow_id}")
        print(f"      Voice ID:             {verified_data.get('voice_id')}")
        print(f"      Is Published:         {verified_data.get('is_published')} (Draft)")

        if engine_type == "conversation-flow":
            print("\nSUCCESS: Agent type explicitly verified as Conversation Flow!")
            return verified_data
        else:
            print(f"\nERROR: Expected 'conversation-flow' but got '{engine_type}'")
            return None


if __name__ == "__main__":
    agent = create_inbound_cf_agent()
    if agent:
        print(json.dumps({
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("agent_name"),
            "response_engine_type": agent.get("response_engine", {}).get("type"),
            "conversation_flow_id": agent.get("response_engine", {}).get("conversation_flow_id"),
            "voice_id": agent.get("voice_id"),
            "is_published": agent.get("is_published"),
        }, indent=2))
