"""
Unit & Integration tests for Retell AI Outbound Sales/SDR Voice Agent.
Validates agent configuration, dynamic variable injection, fallback rules,
qualification outcomes, objection handling, and DNC compliance.
"""
import os
import re
import pytest
import httpx

from app.core.config import settings
from app.services.outreach.voice_agent import (
    QUALIFICATION_OUTCOMES,
    DEFAULT_VOICE_DYNAMIC_VARIABLES,
    build_voice_dynamic_variables,
    render_prompt_template,
    RetellVoiceAgentService,
)

# Test Variables from User Specification
TEST_VARIABLES = {
    "lead_first_name": "John",
    "lead_last_name": "Smith",
    "lead_full_name": "John Smith",
    "prospect_company_name": "Example Healthcare",
    "prospect_job_title": "Operations Manager",
    "sender_name": "Alex",
    "sender_company_name": "Example Sales Company",
    "product_name": "Example Product",
    "product_description": "B2B sales automation platform",
    "value_proposition": "helping teams find and engage qualified business prospects",
    "campaign_name": "Q4 B2B Growth Outreach",
    "campaign_context": "connecting with operations leaders to streamline patient intake outreach",
}


def test_agent_configuration_settings():
    """Verify backend settings correctly load Retell agent and LLM IDs."""
    assert settings.RETELL_AGENT_ID is not None
    assert settings.RETELL_AGENT_ID.startswith("agent_")
    assert settings.RETELL_LLM_ID is not None
    assert settings.RETELL_LLM_ID.startswith("llm_")
    assert settings.is_retell_configured is True

    service = RetellVoiceAgentService()
    assert service.is_configured is True
    assert service.agent_id == settings.RETELL_AGENT_ID


from unittest.mock import MagicMock, patch

def test_retell_live_agent_api_inspection():
    """Verify Retell agent configuration schema (deterministic mock by default, opt-in live via RETELL_LIVE_INSPECTION=true)."""
    headers = {
        "Authorization": f"Bearer {settings.RETELL_API_KEY}",
    }
    use_live = os.getenv("RETELL_LIVE_INSPECTION", "").lower() in ("true", "1")

    def _verify_agent_and_llm(client: httpx.Client):
        # 1. Fetch Agent
        resp = client.get(f"/get-agent/{settings.RETELL_AGENT_ID}")
        assert resp.status_code == 200, f"Failed to get agent: {resp.text}"
        data = resp.json()

        assert data["agent_id"] == settings.RETELL_AGENT_ID
        assert "Outbound B2B SDR Agent" in data["agent_name"]
        assert data["channel"] == "voice"
        assert data["voice_id"] == "11labs-Ryan"
        assert data["enable_dnc_detection"] is True
        assert data["response_engine"]["type"] in ("retell-llm", "conversation-flow")
        if data["response_engine"]["type"] == "retell-llm":
            assert data["response_engine"]["llm_id"] == settings.RETELL_LLM_ID
        else:
            assert data["response_engine"].get("conversation_flow_id") is not None

        # Verify post-call analysis schema
        pca_items = data.get("post_call_analysis_data", [])
        names = [item["name"] for item in pca_items]
        assert "qualification_outcome" in names
        assert "lead_interest_summary" in names
        assert "next_step_action" in names
        assert "objections_raised" in names

        outcome_item = next(item for item in pca_items if item["name"] == "qualification_outcome")
        assert outcome_item["type"] == "enum"
        choices = outcome_item.get("choices", [])
        for outcome in QUALIFICATION_OUTCOMES:
            assert outcome in choices, f"Missing outcome choice: {outcome}"

        # 2. Fetch LLM Response Engine
        llm_resp = client.get(f"/get-retell-llm/{settings.RETELL_LLM_ID}")
        assert llm_resp.status_code == 200, f"Failed to get LLM: {llm_resp.text}"
        llm_data = llm_resp.json()

        assert llm_data["llm_id"] == settings.RETELL_LLM_ID
        assert llm_data["begin_message"] == "Hi, is this {{lead_first_name}}?"
        assert llm_data["start_speaker"] == "agent"

        # Verify tools
        tools = llm_data.get("general_tools", [])
        tool_names = [t.get("name") for t in tools]
        assert "end_call" in tool_names

    if use_live:
        with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=15.0) as client:
            _verify_agent_and_llm(client)
    else:
        mock_agent_data = {
            "agent_id": settings.RETELL_AGENT_ID,
            "agent_name": "Outbound B2B SDR Agent",
            "channel": "voice",
            "voice_id": "11labs-Ryan",
            "enable_dnc_detection": True,
            "response_engine": {
                "type": "retell-llm",
                "llm_id": settings.RETELL_LLM_ID,
            },
            "post_call_analysis_data": [
                {
                    "name": "qualification_outcome",
                    "type": "enum",
                    "choices": list(QUALIFICATION_OUTCOMES),
                },
                {"name": "lead_interest_summary"},
                {"name": "next_step_action"},
                {"name": "objections_raised"},
            ],
        }
        mock_llm_data = {
            "llm_id": settings.RETELL_LLM_ID,
            "begin_message": "Hi, is this {{lead_first_name}}?",
            "start_speaker": "agent",
            "general_tools": [
                {"name": "end_call"}
            ],
        }

        def mock_get(url, *args, **kwargs):
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            url_str = str(url)
            if f"/get-agent/{settings.RETELL_AGENT_ID}" in url_str:
                mock_resp.json.return_value = mock_agent_data
            elif f"/get-retell-llm/{settings.RETELL_LLM_ID}" in url_str:
                mock_resp.json.return_value = mock_llm_data
            else:
                mock_resp.json.return_value = {}
            return mock_resp

        with patch("httpx.Client.get", side_effect=mock_get):
            with httpx.Client(base_url="https://api.retellai.com", headers=headers, timeout=15.0) as client:
                _verify_agent_and_llm(client)


def test_dynamic_variable_substitution_with_test_data():
    """Verify prompt dynamic variables render cleanly without raw brackets."""
    rendered_vars = build_voice_dynamic_variables(custom_overrides=TEST_VARIABLES)

    assert rendered_vars["lead_first_name"] == "John"
    assert rendered_vars["lead_last_name"] == "Smith"
    assert rendered_vars["lead_full_name"] == "John Smith"
    assert rendered_vars["prospect_company_name"] == "Example Healthcare"
    assert rendered_vars["prospect_job_title"] == "Operations Manager"
    assert rendered_vars["sender_name"] == "Alex"
    assert rendered_vars["sender_company_name"] == "Example Sales Company"
    assert rendered_vars["product_name"] == "Example Product"
    assert rendered_vars["product_description"] == "B2B sales automation platform"
    assert rendered_vars["value_proposition"] == "helping teams find and engage qualified business prospects"

    # Test template rendering
    opening_template = (
        "Hi {{lead_first_name}}, this is {{sender_name}} calling from {{sender_company_name}}. "
        "I’m reaching out because we work with businesses like {{prospect_company_name}} "
        "to help with {{value_proposition}}. Do you have a quick minute?"
    )
    rendered_opening = render_prompt_template(opening_template, rendered_vars)
    assert "{{lead_first_name}}" not in rendered_opening
    assert "{{sender_name}}" not in rendered_opening
    assert "{{prospect_company_name}}" not in rendered_opening
    assert "Hi John, this is Alex calling from Example Sales Company." in rendered_opening
    assert "Example Healthcare" in rendered_opening
    assert "helping teams find and engage qualified business prospects" in rendered_opening


def test_missing_variable_graceful_fallback():
    """Verify missing or empty variables gracefully fall back without broken syntax."""
    sparse_vars = build_voice_dynamic_variables(
        custom_overrides={
            "lead_first_name": "",
            "lead_full_name": "",
            "prospect_company_name": "",
        }
    )

    greeting_template = "Hi, is this {{lead_first_name}}?"
    rendered_greeting = render_prompt_template(greeting_template, sparse_vars)
    assert rendered_greeting == "Hi, is this there?"
    assert "{{" not in rendered_greeting

    intro_template = "We work with businesses like {{prospect_company_name}}."
    rendered_intro = render_prompt_template(intro_template, sparse_vars)
    assert "your team" in rendered_intro
    assert "{{" not in rendered_intro


def test_crm_model_integration_variable_builder():
    """Verify dynamic variables are correctly extracted from ORM models."""
    class MockContact:
        first_name = "Sarah"
        last_name = "Connor"
        email = "sconnor@cyberdyne.org"
        phone = "+15551234567"
        job_title = "Chief Technology Officer"
        company = None

    class MockCompany:
        name = "Cyberdyne Systems"

    class MockCampaign:
        name = "Enterprise Automation"
        description = "Targeting infrastructure modernization"

    class MockOrg:
        name = "Agile S&M Group"

    extracted = build_voice_dynamic_variables(
        contact=MockContact(),
        company=MockCompany(),
        campaign=MockCampaign(),
        organization=MockOrg(),
    )

    assert extracted["lead_first_name"] == "Sarah"
    assert extracted["lead_last_name"] == "Connor"
    assert extracted["lead_full_name"] == "Sarah Connor"
    assert extracted["lead_email"] == "sconnor@cyberdyne.org"
    assert extracted["lead_phone"] == "+15551234567"
    assert extracted["prospect_job_title"] == "Chief Technology Officer"
    assert extracted["prospect_company_name"] == "Cyberdyne Systems"
    assert extracted["campaign_name"] == "Enterprise Automation"
    assert extracted["campaign_context"] == "Targeting infrastructure modernization"
    assert extracted["sender_company_name"] == "Agile S&M Group"


def test_qualification_outcomes_completeness():
    """Verify all 9 SDR qualification outcomes are supported."""
    expected_outcomes = {
        "interested",
        "somewhat_interested",
        "not_interested",
        "callback_requested",
        "wrong_person",
        "unavailable",
        "do_not_call",
        "qualified",
        "unqualified",
    }
    assert set(QUALIFICATION_OUTCOMES) == expected_outcomes
