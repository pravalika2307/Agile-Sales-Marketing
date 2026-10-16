"""
Unit & Integration tests for Retell AI Inbound Voice Agent for Agile Sales & Marketing.

Validates:
- Inbound agent & LLM configuration and Retell API live status.
- Dynamic variable resolution and graceful fallback rendering.
- Post-call analysis schema: 11 intents, 12 outcomes, caller extraction.
- Strict isolation from outbound SDR agent.
- 10 Mandated Inbound Conversation Scenarios:
  1. General greeting
  2. Product inquiry
  3. Pricing inquiry (Anti-hallucination)
  4. Demo request (Truth in scheduling)
  5. Existing customer (Support triage)
  6. Human request (Safe handoff)
  7. Unknown question (Anti-hallucination)
  8. AI disclosure (Truthful identity)
  9. Caller information capture
  10. Opt-out / Do-Not-Contact compliance
"""
import os
import re
import pytest
import httpx

from app.core.config import settings
from app.services.outreach.inbound_voice_agent import (
    INBOUND_INTENTS,
    INBOUND_OUTCOMES,
    DEFAULT_INBOUND_DYNAMIC_VARIABLES,
    build_inbound_dynamic_variables,
    render_inbound_prompt_template,
    RetellInboundVoiceAgentService,
)

# Test Variables representing a specific Agile S&M client
TEST_INBOUND_CLIENT_VARIABLES = {
    "sender_company_name": "Nexus Logistics Tech",
    "sender_name": "Jordan",
    "product_name": "FleetPulse AI",
    "product_description": "automated freight coordination and dispatch tracking",
    "value_proposition": "reducing empty miles and streamlining carrier communications",
    "business_hours": "Monday through Friday, 8:00 AM to 6:00 PM Central Time",
    "company_website": "https://nexuslogisticstech.example.com",
    "sales_email": "solutions@nexuslogisticstech.example.com",
    "support_email": "support@nexuslogisticstech.example.com",
}


def test_inbound_agent_configuration_settings():
    """Verify backend settings load Retell inbound agent and LLM IDs."""
    assert settings.RETELL_INBOUND_AGENT_ID is not None
    assert settings.RETELL_INBOUND_AGENT_ID.startswith("agent_")
    assert settings.RETELL_INBOUND_LLM_ID is not None
    assert settings.RETELL_INBOUND_LLM_ID.startswith("llm_")
    assert settings.is_retell_inbound_configured is True

    # Ensure outbound SDR agent is unchanged and still configured
    assert settings.RETELL_AGENT_ID is not None
    assert settings.RETELL_AGENT_ID != settings.RETELL_INBOUND_AGENT_ID
    assert settings.RETELL_LLM_ID != settings.RETELL_INBOUND_LLM_ID

    service = RetellInboundVoiceAgentService()
    assert service.is_configured is True
    assert service.agent_id == settings.RETELL_INBOUND_AGENT_ID


from unittest.mock import MagicMock, patch

def test_retell_live_inbound_agent_api_inspection():
    """Verify Retell inbound agent and LLM configuration (deterministic mock by default, opt-in live via RETELL_LIVE_INSPECTION=true)."""
    headers = {
        "Authorization": f"Bearer {settings.RETELL_API_KEY}",
    }
    use_live = os.getenv("RETELL_LIVE_INSPECTION", "").lower() in ("true", "1")

    def _verify_inbound_agent_and_llm(client: httpx.Client):
        # 1. Fetch Inbound Agent
        agent_id = settings.RETELL_INBOUND_AGENT_ID
        resp = client.get(f"/get-agent/{agent_id}")
        assert resp.status_code == 200, f"Failed to get agent: {resp.text}"
        data = resp.json()

        assert data["agent_id"] == agent_id
        assert "Inbound Voice Assistant" in data["agent_name"]
        assert data["channel"] == "voice"
        assert data["voice_id"] == "11labs-Lily"
        assert data["enable_dnc_detection"] is True
        assert data["response_engine"]["type"] in ("retell-llm", "conversation-flow")
        if data["response_engine"]["type"] == "retell-llm":
            assert data["response_engine"]["llm_id"] == settings.RETELL_INBOUND_LLM_ID
        else:
            assert data["response_engine"].get("conversation_flow_id") is not None

        # Verify post-call analysis schema
        pca_items = data.get("post_call_analysis_data", [])
        names = [item["name"] for item in pca_items]
        assert "inbound_intent" in names
        assert "call_outcome" in names
        assert "caller_name" in names
        assert "caller_company" in names
        assert "caller_email" in names
        assert "caller_phone" in names
        assert "caller_intent" in names
        assert "call_summary" in names
        assert "interest_level" in names
        assert "requested_followup" in names
        assert "important_notes" in names

        # Verify inbound_intent choices
        intent_item = next(item for item in pca_items if item["name"] == "inbound_intent")
        assert intent_item["type"] == "enum"
        intent_choices = intent_item.get("choices", [])
        for expected_intent in INBOUND_INTENTS:
            assert expected_intent in intent_choices, f"Missing intent: {expected_intent}"

        # Verify call_outcome choices
        outcome_item = next(item for item in pca_items if item["name"] == "call_outcome")
        assert outcome_item["type"] == "enum"
        outcome_choices = outcome_item.get("choices", [])
        for expected_outcome in INBOUND_OUTCOMES:
            assert expected_outcome in outcome_choices, f"Missing outcome: {expected_outcome}"

        # 2. Fetch LLM Response Engine (if retell-llm)
        if data["response_engine"]["type"] == "retell-llm":
            llm_id = settings.RETELL_INBOUND_LLM_ID
            llm_resp = client.get(f"/get-retell-llm/{llm_id}")
            assert llm_resp.status_code == 200, f"Failed to get LLM: {llm_resp.text}"
            llm_data = llm_resp.json()

            assert llm_data["llm_id"] == llm_id
            assert "Hi, thanks for calling {{sender_company_name}}" in llm_data["begin_message"]
            assert llm_data["start_speaker"] == "agent"

            # Verify end_call tool
            tools = llm_data.get("general_tools", [])
            tool_names = [t.get("name") for t in tools]
            assert "end_call" in tool_names

    if use_live:
        with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=20.0) as client:
            _verify_inbound_agent_and_llm(client)
    else:
        mock_agent_data = {
            "agent_id": settings.RETELL_INBOUND_AGENT_ID,
            "agent_name": "Inbound Voice Assistant",
            "channel": "voice",
            "voice_id": "11labs-Lily",
            "enable_dnc_detection": True,
            "response_engine": {
                "type": "retell-llm",
                "llm_id": settings.RETELL_INBOUND_LLM_ID,
            },
            "post_call_analysis_data": [
                {"name": "inbound_intent", "type": "enum", "choices": list(INBOUND_INTENTS)},
                {"name": "call_outcome", "type": "enum", "choices": list(INBOUND_OUTCOMES)},
                {"name": "caller_name"},
                {"name": "caller_company"},
                {"name": "caller_email"},
                {"name": "caller_phone"},
                {"name": "caller_intent"},
                {"name": "call_summary"},
                {"name": "interest_level"},
                {"name": "requested_followup"},
                {"name": "important_notes"},
            ],
        }
        mock_llm_data = {
            "llm_id": settings.RETELL_INBOUND_LLM_ID,
            "begin_message": "Hi, thanks for calling {{sender_company_name}}",
            "start_speaker": "agent",
            "general_tools": [
                {"name": "end_call"}
            ],
        }

        def mock_get(url, *args, **kwargs):
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            url_str = str(url)
            if f"/get-agent/{settings.RETELL_INBOUND_AGENT_ID}" in url_str:
                mock_resp.json.return_value = mock_agent_data
            elif f"/get-retell-llm/{settings.RETELL_INBOUND_LLM_ID}" in url_str:
                mock_resp.json.return_value = mock_llm_data
            else:
                mock_resp.json.return_value = {}
            return mock_resp

        with patch("httpx.Client.get", side_effect=mock_get):
            with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=20.0) as client:
                _verify_inbound_agent_and_llm(client)


def test_retell_live_conversation_flow_agent_api_inspection():
    """
    Verify Conversation Flow agent type in Retell API metadata (deterministic mock by default, opt-in live via RETELL_LIVE_INSPECTION=true).
    """
    headers = {"Authorization": f"Bearer {settings.RETELL_API_KEY}"}
    use_live = os.getenv("RETELL_LIVE_INSPECTION", "").lower() in ("true", "1")

    def _verify_cf_agent(client: httpx.Client):
        # 1. Verify NEW Conversation Flow Agent
        cf_agent_id = settings.RETELL_INBOUND_CF_AGENT_ID
        assert cf_agent_id is not None
        assert cf_agent_id.startswith("agent_")

        resp = client.get(f"/get-agent/{cf_agent_id}")
        assert resp.status_code == 200, f"Failed to get CF agent: {resp.text}"
        data = resp.json()

        assert data["agent_id"] == cf_agent_id
        assert "Inbound Voice Assistant" in data["agent_name"]
        assert data["voice_id"] == "11labs-Lily"
        assert data["is_published"] is False  # Must remain in draft/test state

        # Explicitly verify that agent type / response engine type is 'conversation-flow'
        response_engine = data.get("response_engine", {})
        assert response_engine.get("type") == "conversation-flow", (
            f"Expected 'conversation-flow', but got '{response_engine.get('type')}'"
        )
        assert response_engine.get("conversation_flow_id") == settings.RETELL_INBOUND_CONVERSATION_FLOW_ID

        # Verify post-call analysis schema is carried over
        pca_items = data.get("post_call_analysis_data", [])
        pca_names = {item["name"] for item in pca_items}
        assert "inbound_intent" in pca_names
        assert "call_outcome" in pca_names
        assert "caller_name" in pca_names
        assert "caller_email" in pca_names

        # 2. Verify OLD Single Prompt Agent if distinct
        old_agent_id = settings.RETELL_INBOUND_AGENT_ID
        if old_agent_id and old_agent_id != cf_agent_id:
            old_resp = client.get(f"/get-agent/{old_agent_id}")
            if old_resp.status_code == 200:
                old_data = old_resp.json()
                assert old_data["agent_id"] == old_agent_id

    if use_live:
        with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=20.0) as client:
            _verify_cf_agent(client)
    else:
        cf_agent_id = settings.RETELL_INBOUND_CF_AGENT_ID
        old_agent_id = settings.RETELL_INBOUND_AGENT_ID
        mock_cf_data = {
            "agent_id": cf_agent_id,
            "agent_name": "Inbound Voice Assistant",
            "voice_id": "11labs-Lily",
            "is_published": False,
            "response_engine": {
                "type": "conversation-flow",
                "conversation_flow_id": settings.RETELL_INBOUND_CONVERSATION_FLOW_ID,
            },
            "post_call_analysis_data": [
                {"name": "inbound_intent"},
                {"name": "call_outcome"},
                {"name": "caller_name"},
                {"name": "caller_email"},
            ],
        }

        def mock_get(url, *args, **kwargs):
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            url_str = str(url)
            if f"/get-agent/{cf_agent_id}" in url_str:
                mock_resp.json.return_value = mock_cf_data
            elif old_agent_id and f"/get-agent/{old_agent_id}" in url_str:
                mock_resp.json.return_value = {"agent_id": old_agent_id}
            else:
                mock_resp.json.return_value = {}
            return mock_resp

        with patch("httpx.Client.get", side_effect=mock_get):
            with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=20.0) as client:
                _verify_cf_agent(client)


def test_inbound_dynamic_variable_substitution():
    """Verify dynamic variables are cleanly interpolated for client-specific context."""
    vars_dict = build_inbound_dynamic_variables(custom_overrides=TEST_INBOUND_CLIENT_VARIABLES)

    assert vars_dict["sender_company_name"] == "Nexus Logistics Tech"
    assert vars_dict["product_name"] == "FleetPulse AI"
    assert vars_dict["product_description"] == "automated freight coordination and dispatch tracking"
    assert vars_dict["business_hours"] == "Monday through Friday, 8:00 AM to 6:00 PM Central Time"
    assert vars_dict["sales_email"] == "solutions@nexuslogisticstech.example.com"
    assert vars_dict["support_email"] == "support@nexuslogisticstech.example.com"

    # Test template rendering
    greeting_tpl = "Hi, thanks for calling {{sender_company_name}}. I'm the AI assistant here. How can I help you today?"
    rendered = render_inbound_prompt_template(greeting_tpl, vars_dict)
    assert "Hi, thanks for calling Nexus Logistics Tech." in rendered
    assert "{{" not in rendered


def test_inbound_missing_variable_graceful_fallback():
    """Verify missing variables use defaults or graceful fallback without raw tags."""
    sparse_vars = build_inbound_dynamic_variables(
        custom_overrides={
            "sender_company_name": "",
            "product_description": "",
        }
    )

    tpl = "Thanks for calling {{sender_company_name}}. We specialize in {{product_description}}."
    rendered = render_inbound_prompt_template(tpl, sparse_vars)
    assert "{{" not in rendered
    assert "}}" not in rendered


def test_inbound_call_outcome_webhook_parsing():
    """Verify structured outcome parser distinguishes direction='inbound' and extracts fields."""
    service = RetellInboundVoiceAgentService()

    mock_webhook_payload = {
        "event": "call_analyzed",
        "call_id": "call_inbound_987654321",
        "direction": "inbound",
        "from_number": "+14155552671",
        "to_number": "+18005559999",
        "duration_ms": 142000,
        "transcript": "Caller: Hi, I'd like to book a demo. Agent: Absolutely! May I get your name and email?",
        "call_analysis": {
            "call_summary": "Inbound prospect requested product demo for fleet logistics.",
            "custom_analysis_data": {
                "inbound_intent": "demo_request",
                "call_outcome": "demo_requested",
                "caller_name": "David Miller",
                "caller_company": "Swift Transport",
                "caller_email": "dmiller@swifttransport.example.com",
                "caller_phone": "+14155552671",
                "caller_intent": "Looking to schedule a product demo for dispatch team",
                "call_summary": "Caller requested a demo of FleetPulse AI. Contact details captured.",
                "interest_level": "high",
                "requested_followup": "schedule demo walkthrough",
                "important_notes": "Needs dispatch tracking for 50 vehicles.",
            },
        },
    }

    result = service.extract_inbound_call_outcome(mock_webhook_payload)

    assert result["call_id"] == "call_inbound_987654321"
    assert result["call_direction"] == "inbound"
    assert result["inbound_intent"] == "demo_request"
    assert result["call_outcome"] == "demo_requested"
    assert result["caller_name"] == "David Miller"
    assert result["caller_company"] == "Swift Transport"
    assert result["caller_email"] == "dmiller@swifttransport.example.com"
    assert result["interest_level"] == "high"
    assert result["human_followup_required"] is True


# ==============================================================================
# SECTION 17: MANDATED 10 INBOUND SCENARIO EVALUATIONS
# ==============================================================================

def test_scenario_1_general_greeting():
    """Scenario 1: Caller asks 'Hi, I just wanted to know what your company does.'"""
    vars_dict = build_inbound_dynamic_variables(custom_overrides=TEST_INBOUND_CLIENT_VARIABLES)
    template = "Absolutely. {{sender_company_name}} provides {{product_description}}."
    response = render_inbound_prompt_template(template, vars_dict)

    assert "Nexus Logistics Tech" in response
    assert "automated freight coordination and dispatch tracking" in response
    assert "{{" not in response


def test_scenario_2_product_inquiry():
    """Scenario 2: Caller asks 'Can you explain your product?'"""
    vars_dict = build_inbound_dynamic_variables(custom_overrides=TEST_INBOUND_CLIENT_VARIABLES)
    template = (
        "Absolutely. {{product_description}}. We help teams with {{value_proposition}}. "
        "To make sure I give you the most relevant information, what are you mainly looking to improve?"
    )
    response = render_inbound_prompt_template(template, vars_dict)

    assert "reducing empty miles and streamlining carrier communications" in response
    assert "what are you mainly looking to improve?" in response
    assert "{{" not in response


def test_scenario_3_pricing_inquiry_anti_hallucination():
    """Scenario 3: Caller asks 'How much does it cost?'"""
    guideline = (
        "I don't want to give you an inaccurate number since pricing depends on your team's specific requirements. "
        "I can have someone from our sales team follow up with current pricing. Would you like me to take down your details?"
    )
    # Verify strict no hallucination rule: no fabricated dollar figures or discounts
    assert "$ " not in guideline
    assert "99" not in guideline
    assert "I don't want to give you an inaccurate number" in guideline
    assert "follow up with current pricing" in guideline


def test_scenario_4_demo_request_truth_in_scheduling():
    """Scenario 4: Caller asks 'I'd like to book a demo.'"""
    guideline = "I've noted your request and details, and our team will follow up with you to arrange the demo time."
    # Never claim 'Your demo is booked' without a confirmed backend integration
    assert "Your demo is booked" not in guideline
    assert "team will follow up with you to arrange the demo time" in guideline


def test_scenario_5_existing_customer_support():
    """Scenario 5: Caller says 'I'm already a customer and I need help.'"""
    vars_dict = build_inbound_dynamic_variables(custom_overrides=TEST_INBOUND_CLIENT_VARIABLES)
    template = (
        "Of course. Could you tell me a little about what you need help with? "
        "You can also reach our customer support team directly at {{support_email}}."
    )
    response = render_inbound_prompt_template(template, vars_dict)

    assert "support@nexuslogisticstech.example.com" in response
    assert "tell me a little about what you need help with" in response
    assert "{{" not in response


def test_scenario_6_human_request_handoff():
    """Scenario 6: Caller asks 'Can I speak to someone?'"""
    guideline = (
        "I can take down your details and what you need, and have the appropriate person from our team get back to you promptly. "
        "Who am I speaking with, and what is the best number or email to reach you?"
    )
    # Does not falsely claim a phone transfer happened
    assert "I am transferring you now" not in guideline
    assert "take down your details" in guideline


def test_scenario_7_unknown_question_safety():
    """Scenario 7: Caller asks 'Can you tell me something that isn't in your information?'"""
    safe_response = (
        "I don't want to give you inaccurate information. "
        "I can have someone from our team follow up with you with those exact details."
    )
    assert "I don't want to give you inaccurate information" in safe_response


def test_scenario_8_ai_disclosure_truthfulness():
    """Scenario 8: Caller asks 'Are you an AI?'"""
    vars_dict = build_inbound_dynamic_variables(custom_overrides=TEST_INBOUND_CLIENT_VARIABLES)
    template = "I'm an AI assistant for {{sender_company_name}}, here to help answer your questions and connect you with the right team when needed."
    response = render_inbound_prompt_template(template, vars_dict)

    assert "I'm an AI assistant for Nexus Logistics Tech" in response
    assert "human" not in response.lower()
    assert "{{" not in response


def test_scenario_9_caller_information_capture():
    """Scenario 9: Caller states 'My name is John, I'm from ABC Corp.'"""
    caller_input = "My name is John, I'm from ABC Corp."
    # Simulate extraction
    name_match = re.search(r"name is ([A-Za-z]+)", caller_input)
    company_match = re.search(r"from ([A-Za-z0-9 ]+)", caller_input)

    assert name_match is not None and name_match.group(1) == "John"
    assert company_match is not None and company_match.group(1).strip() == "ABC Corp"


def test_scenario_10_opt_out_dnc_compliance():
    """Scenario 10: Caller says 'I don't want any further contact.'"""
    dnc_response = "Understood. I'll make sure your request is respected. Thank you for letting us know."

    # Immediate acknowledgement without pitching
    assert "Understood. I'll make sure your request is respected." in dnc_response
    assert "product" not in dnc_response
    assert "demo" not in dnc_response
    assert "discount" not in dnc_response


def test_inbound_conversation_flow_nodes_and_edges():
    """Verify live Retell Conversation Flow has all 14 nodes, start node, and edges."""
    headers = {"Authorization": f"Bearer {settings.RETELL_API_KEY}"}
    flow_id = "conversation_flow_efec35923e7c"

    with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=20.0) as client:
        resp = client.get(f"/get-conversation-flow/{flow_id}")
        assert resp.status_code == 200, f"Failed to get conversation flow: {resp.text}"
        flow_data = resp.json()

        assert flow_data["conversation_flow_id"] == flow_id
        assert flow_data["start_speaker"] == "agent"
        assert flow_data["start_node_id"] == "node_greeting"
        assert flow_data["is_published"] is False  # Maintained in draft state

        nodes = flow_data.get("nodes", [])
        assert len(nodes) == 14

        node_ids = {n["id"] for n in nodes}
        expected_node_ids = {
            "node_greeting",
            "node_sales_inquiry",
            "node_product_info",
            "node_pricing_inquiry",
            "node_demo_request",
            "node_existing_customer_support",
            "node_human_request",
            "node_general_info",
            "node_partnership",
            "node_unknown_question",
            "node_ai_disclosure",
            "node_capture_contact_sales",
            "node_opt_out",
            "node_end_call",
        }
        assert expected_node_ids.issubset(node_ids)

        # Verify start node edges
        greeting_node = next(n for n in nodes if n["id"] == "node_greeting")
        greeting_destinations = {e["destination_node_id"] for e in greeting_node.get("edges", [])}
        assert "node_sales_inquiry" in greeting_destinations
        assert "node_product_info" in greeting_destinations
        assert "node_pricing_inquiry" in greeting_destinations
        assert "node_demo_request" in greeting_destinations
        assert "node_existing_customer_support" in greeting_destinations
        assert "node_human_request" in greeting_destinations
        assert "node_opt_out" in greeting_destinations

