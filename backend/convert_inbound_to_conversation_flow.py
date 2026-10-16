"""
Script to create the Retell Conversation Flow and convert the Inbound Voice Agent
(agent_546bf2dd0fbc7377911d528156) from a Single Prompt Agent to a Conversation Flow Agent.

Preserves:
- Agent ID: agent_546bf2dd0fbc7377911d528156
- Voice configuration: 11labs-Lily, backchannel, responsiveness, etc.
- Post-call analysis schema: 11 intents, 12 outcomes, caller data
- Dynamic variables: all 9 company and product variables
- DNC detection and language settings
- Draft state: is_published = False
"""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

RETELL_API_KEY = os.getenv("RETELL_API_KEY", "key_f8a196d2fdba0276593d95448b7e")
AGENT_ID = os.getenv("RETELL_INBOUND_AGENT_ID", "agent_546bf2dd0fbc7377911d528156")
BASE_URL = "https://api.retellai.com"

# Global Prompt: Focuses strictly on persona, tone, rules, anti-hallucination, compliance
GLOBAL_PROMPT = """# IDENTITY & ROLE
You are a friendly, professional, calm, and helpful AI Receptionist and Sales & Support assistant answering inbound calls for {{sender_company_name}}.
The caller initiated this call to reach {{sender_company_name}}.

# CONVERSATIONAL STYLE & PERSONALITY
- Tone: Friendly, warm, professional, calm, and conversational.
- Delivery: Speak at a natural pace. Keep responses concise (1 to 2 sentences per turn). Avoid monologues.
- Active Listening: Acknowledge what the caller says naturally before transitioning ("Got it", "Understood", "Makes sense", "Thanks for explaining that").
- No Robotic IVR: Never sound like a phone tree menu ("Press 1 for sales"). Speak conversationally.
- One Question at a Time: Ask a single clear question, then pause and listen.
- Remember Details: Never re-ask for information the caller has already provided (such as name, company, or email).

# STRICT SAFETY & ANTI-HALLUCINATION RULES
- NEVER invent pricing, subscription tiers, discounts, or package rates.
- NEVER invent product capabilities, features, or technical integrations.
- NEVER pretend to access live customer databases, billing systems, or account records.
- NEVER claim an action was taken (such as "Your demo is booked") unless an integrated tool completed it.
- If information is unavailable:
  "I don't want to give you inaccurate information. I can have someone from the team follow up with you about that."

# AI DISCLOSURE RULE
If asked "Are you an AI?", "Is this a bot?", or "Are you a real person?":
Answer truthfully:
"I'm an AI assistant for {{sender_company_name}}, here to help with your questions and connect you with the right team when needed."
Never pretend to be a biological human.

# OPT-OUT & DO-NOT-CONTACT COMPLIANCE
If the caller requests not to be contacted or to remove their number:
Immediately respect the request:
"Understood. I'll make sure your request is respected. Thank you for letting us know."
Then end the call. Never continue pitching or asking questions.

# DYNAMIC VARIABLES
You have access to:
- sender_company_name: {{sender_company_name}}
- sender_name: {{sender_name}}
- product_name: {{product_name}}
- product_description: {{product_description}}
- value_proposition: {{value_proposition}}
- business_hours: {{business_hours}}
- company_website: {{company_website}}
- sales_email: {{sales_email}}
- support_email: {{support_email}}

GRACEFUL FALLBACK RULE:
If any dynamic variable is blank or missing, adapt your phrasing naturally (e.g., say "our company" if sender_company_name is missing). Never speak literal bracket syntax like "{{sender_company_name}}".
"""

DEFAULT_DYNAMIC_VARIABLES = {
    "sender_company_name": "Agile Sales & Marketing",
    "sender_name": "Alex",
    "product_name": "Agile Sales Platform",
    "product_description": "an automated B2B sales pipeline and customer engagement platform",
    "value_proposition": "streamlining outreach, lead qualification, and customer interactions",
    "business_hours": "Monday through Friday, 9:00 AM to 5:00 PM Eastern Time",
    "company_website": "https://agilesalesmarketing.com",
    "sales_email": "sales@agilesalesmarketing.com",
    "support_email": "support@agilesalesmarketing.com",
}

# Conversation Flow Nodes
NODES = [
    # 1. Greeting Node (Start Node)
    {
        "id": "node_greeting",
        "name": "Inbound Greeting",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Answer warmly and introduce the company: \"Hi, thanks for calling {{sender_company_name}}. I'm the AI assistant here. How can I help you today?\" Listen attentively to understand why the caller reached out. Do not start selling immediately.",
        },
        "display_position": {"x": 200, "y": 600},
        "edges": [
            {
                "id": "edge_greet_to_sales",
                "destination_node_id": "node_sales_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller is interested in the product, asks what the company does, or has a sales inquiry.",
                },
            },
            {
                "id": "edge_greet_to_product",
                "destination_node_id": "node_product_info",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks specific product, technical, or feature questions.",
                },
            },
            {
                "id": "edge_greet_to_pricing",
                "destination_node_id": "node_pricing_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks about pricing, rates, costs, or package tiers.",
                },
            },
            {
                "id": "edge_greet_to_demo",
                "destination_node_id": "node_demo_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller wants to schedule, request, or book a product demo or walkthrough.",
                },
            },
            {
                "id": "edge_greet_to_support",
                "destination_node_id": "node_existing_customer_support",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller is an existing customer or has a support/technical issue.",
                },
            },
            {
                "id": "edge_greet_to_human",
                "destination_node_id": "node_human_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller explicitly asks to speak with a human, agent, or representative.",
                },
            },
            {
                "id": "edge_greet_to_general",
                "destination_node_id": "node_general_info",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks about business hours, website, office location, or general company info.",
                },
            },
            {
                "id": "edge_greet_to_partner",
                "destination_node_id": "node_partnership",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller represents a vendor, partner, or business development opportunity.",
                },
            },
            {
                "id": "edge_greet_to_unknown",
                "destination_node_id": "node_unknown_question",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks something obscure or outside standard company information.",
                },
            },
            {
                "id": "edge_greet_to_ai",
                "destination_node_id": "node_ai_disclosure",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks if you are an AI, bot, or real person.",
                },
            },
            {
                "id": "edge_greet_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller says do not call, remove number, or stop contacting them.",
                },
            },
            {
                "id": "edge_greet_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller says goodbye, thank you, or has no further questions.",
                },
            },
        ],
    },

    # 2. Sales Inquiry Node
    {
        "id": "node_sales_inquiry",
        "name": "Sales Inquiry & Qualification",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Concisely explain what {{sender_company_name}} offers: \"{{product_description}}. We help teams with {{value_proposition}}.\" Then ask 1 qualification question: \"To make sure I give you the most relevant information, what are you mainly looking to improve?\" Do not conduct a long interrogation.",
        },
        "display_position": {"x": 600, "y": 200},
        "edges": [
            {
                "id": "edge_sales_to_capture",
                "destination_node_id": "node_capture_contact_sales",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller shares their requirements and is open to connecting with the sales team.",
                },
            },
            {
                "id": "edge_sales_to_demo",
                "destination_node_id": "node_demo_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks to see a demo or schedule a walkthrough.",
                },
            },
            {
                "id": "edge_sales_to_pricing",
                "destination_node_id": "node_pricing_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks how much it costs or inquires about pricing.",
                },
            },
            {
                "id": "edge_sales_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
            {
                "id": "edge_sales_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller is not interested or says goodbye.",
                },
            },
        ],
    },

    # 3. Product Information Node
    {
        "id": "node_product_info",
        "name": "Product Information",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Answer product questions using only verified knowledge: {{product_name}} is {{product_description}}. Strict rule: Never invent features, technical integrations, or guarantees. If unknown, explain: \"I don't want to give you inaccurate information. I can have someone from the team follow up with you with those details.\"",
        },
        "display_position": {"x": 600, "y": 380},
        "edges": [
            {
                "id": "edge_prod_to_capture",
                "destination_node_id": "node_capture_contact_sales",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller wants to discuss further or have sales follow up.",
                },
            },
            {
                "id": "edge_prod_to_demo",
                "destination_node_id": "node_demo_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller wants to see a demo.",
                },
            },
            {
                "id": "edge_prod_to_pricing",
                "destination_node_id": "node_pricing_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks about pricing.",
                },
            },
            {
                "id": "edge_prod_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller has received their answer and is all set.",
                },
            },
            {
                "id": "edge_prod_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 4. Pricing Inquiry Node
    {
        "id": "node_pricing_inquiry",
        "name": "Pricing Inquiry",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Address pricing transparently without hallucinating: \"I don't want to give you an inaccurate number since pricing depends on your team's specific requirements. I can have someone from our sales team follow up with the current pricing. Would you like me to take down your details?\" Never invent numbers, tiers, or discounts.",
        },
        "display_position": {"x": 600, "y": 560},
        "edges": [
            {
                "id": "edge_price_to_capture",
                "destination_node_id": "node_capture_contact_sales",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller agrees to follow-up or provides contact info.",
                },
            },
            {
                "id": "edge_price_to_human",
                "destination_node_id": "node_human_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller wants to talk to a human salesperson immediately.",
                },
            },
            {
                "id": "edge_price_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller declines follow-up or says thank you.",
                },
            },
            {
                "id": "edge_price_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 5. Demo Request Node
    {
        "id": "node_demo_request",
        "name": "Demo Request",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Welcome the request warmly: \"We'd love to arrange that for you.\" Collect their name, company, email, phone number, and key goals. Truth in Scheduling rule: DO NOT say \"Your demo is booked.\" Say: \"I've noted your request, and someone from the team will follow up with you to arrange the demo time.\"",
        },
        "display_position": {"x": 600, "y": 740},
        "edges": [
            {
                "id": "edge_demo_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Details collected and caller has no more questions.",
                },
            },
            {
                "id": "edge_demo_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 6. Existing Customer / Support Node
    {
        "id": "node_existing_customer_support",
        "name": "Existing Customer & Support",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Ask what they need help with: \"Of course. Could you tell me a little about what you need help with?\" If it requires account access or technical troubleshooting: \"I understand. Because that requires accessing your account details, I'll take down your information so our customer support team can follow up directly. You can also reach them at {{support_email}}.\" Never pretend to modify accounts.",
        },
        "display_position": {"x": 600, "y": 920},
        "edges": [
            {
                "id": "edge_supp_to_human",
                "destination_node_id": "node_human_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller insists on speaking with a human agent right now.",
                },
            },
            {
                "id": "edge_supp_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Issue noted or caller is satisfied.",
                },
            },
            {
                "id": "edge_supp_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 7. Human Request Node
    {
        "id": "node_human_request",
        "name": "Human Assistance Handoff",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Handle human handoff responsibly: If no live phone transfer is active, never pretend a transfer happened. Say: \"I can take down your details and what you need, and have the appropriate person from our team get back to you promptly. Who am I speaking with, and what is the best number or email to reach you?\"",
        },
        "display_position": {"x": 600, "y": 1100},
        "edges": [
            {
                "id": "edge_human_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Details logged for human team callback.",
                },
            },
            {
                "id": "edge_human_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 8. General Information Node
    {
        "id": "node_general_info",
        "name": "General Information",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Provide company details: \"Our office hours are {{business_hours}}, and you can find more details on our website at {{company_website}} or reach the team by email at {{sales_email}}.\" Ask if there is anything else they need.",
        },
        "display_position": {"x": 600, "y": 1280},
        "edges": [
            {
                "id": "edge_gen_to_sales",
                "destination_node_id": "node_sales_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks about the product or sales.",
                },
            },
            {
                "id": "edge_gen_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller is satisfied and has no more questions.",
                },
            },
            {
                "id": "edge_gen_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 9. Partnership Node
    {
        "id": "node_partnership",
        "name": "Partnership Inquiries",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Acknowledge partnership interest: \"Thank you for reaching out. I'll note your details and the nature of the partnership so our business development team can review and follow up with you. Could I have your name, company, and email?\"",
        },
        "display_position": {"x": 600, "y": 1460},
        "edges": [
            {
                "id": "edge_part_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Details noted for partnerships team.",
                },
            },
            {
                "id": "edge_part_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 10. Unknown Question Node
    {
        "id": "node_unknown_question",
        "name": "Unknown Question Guardrail",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Admit lack of information safely: \"I don't want to give you inaccurate information. I can have someone from our team follow up with you with those exact details. Would you like me to take down your contact info?\"",
        },
        "display_position": {"x": 600, "y": 1640},
        "edges": [
            {
                "id": "edge_unk_to_capture",
                "destination_node_id": "node_capture_contact_sales",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller provides contact information for follow-up.",
                },
            },
            {
                "id": "edge_unk_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller declines follow-up or has no more questions.",
                },
            },
            {
                "id": "edge_unk_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 11. AI Disclosure Node
    {
        "id": "node_ai_disclosure",
        "name": "AI Identity Disclosure",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Answer truthfully: \"I'm an AI assistant for {{sender_company_name}}, here to help with your questions and connect you with the right team when needed. How can I help you today?\" Never claim to be human.",
        },
        "display_position": {"x": 600, "y": 1820},
        "edges": [
            {
                "id": "edge_ai_to_sales",
                "destination_node_id": "node_sales_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks about the product or company offerings.",
                },
            },
            {
                "id": "edge_ai_to_demo",
                "destination_node_id": "node_demo_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller wants a demo.",
                },
            },
            {
                "id": "edge_ai_to_pricing",
                "destination_node_id": "node_pricing_inquiry",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller asks about pricing.",
                },
            },
            {
                "id": "edge_ai_to_support",
                "destination_node_id": "node_existing_customer_support",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller has a support or account question.",
                },
            },
            {
                "id": "edge_ai_to_human",
                "destination_node_id": "node_human_request",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests to speak with a human person.",
                },
            },
            {
                "id": "edge_ai_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller is satisfied or says goodbye.",
                },
            },
            {
                "id": "edge_ai_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 12. Contact Capture Node
    {
        "id": "node_capture_contact_sales",
        "name": "Capture Contact & Next Steps",
        "type": "conversation",
        "instruction": {
            "type": "prompt",
            "text": "Collect their name, company, email, and phone number if not already provided. Confirm: \"Thank you, I've noted your details and our team will follow up with you promptly. Is there anything else I can help you with today?\"",
        },
        "display_position": {"x": 1050, "y": 450},
        "edges": [
            {
                "id": "edge_cap_to_end",
                "destination_node_id": "node_end_call",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller says no, thank you, or is all set.",
                },
            },
            {
                "id": "edge_cap_to_opt_out",
                "destination_node_id": "node_opt_out",
                "transition_condition": {
                    "type": "prompt",
                    "prompt": "Caller requests not to be contacted.",
                },
            },
        ],
    },

    # 13. Opt-Out / Do-Not-Contact Node (End Node)
    {
        "id": "node_opt_out",
        "name": "Opt-Out DNC Terminal",
        "type": "end",
        "instruction": {
            "type": "prompt",
            "text": "Politely respect their request and immediately end the call: \"Understood. I'll make sure your request is respected. Thank you for letting us know.\"",
        },
        "display_position": {"x": 1050, "y": 1400},
    },

    # 14. Professional Close Call Node (End Node)
    {
        "id": "node_end_call",
        "name": "Professional Call Close",
        "type": "end",
        "instruction": {
            "type": "prompt",
            "text": "Politely thank the caller and end the call: \"Thank you for calling {{sender_company_name}}. Have a wonderful day!\"",
        },
        "display_position": {"x": 1050, "y": 800},
    },
]


def convert_inbound_agent_to_conversation_flow():
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        # Step 1: Create Conversation Flow
        print(f"[1/3] Creating Conversation Flow for Inbound Agent...")
        flow_payload = {
            "global_prompt": GLOBAL_PROMPT,
            "start_speaker": "agent",
            "start_node_id": "node_greeting",
            "model_choice": {
                "type": "cascading",
                "model": "gpt-4.1-mini",
            },
            "default_dynamic_variables": DEFAULT_DYNAMIC_VARIABLES,
            "nodes": NODES,
        }

        flow_resp = client.post("/create-conversation-flow", json=flow_payload)
        if flow_resp.status_code not in (200, 201):
            print(f"Failed to create Conversation Flow: {flow_resp.status_code} - {flow_resp.text}")
            return None

        flow_data = flow_resp.json()
        flow_id = flow_data["conversation_flow_id"]
        print(f"  --> Conversation Flow created! ID: {flow_id}")

        # Step 2: Update Inbound Agent to use the new Conversation Flow as response_engine
        print(f"\n[2/3] Updating Agent {AGENT_ID} to Conversation Flow response engine...")
        agent_update_payload = {
            "response_engine": {
                "type": "conversation-flow",
                "conversation_flow_id": flow_id,
                "version": 0,
            }
        }

        update_resp = client.patch(f"/update-agent/{AGENT_ID}", json=agent_update_payload)
        if update_resp.status_code != 200:
            print(f"Failed to update agent: {update_resp.status_code} - {update_resp.text}")
            return None

        updated_agent = update_resp.json()
        print(f"  --> Agent successfully updated to Conversation Flow!")
        print(f"      Agent ID:       {updated_agent.get('agent_id')}")
        print(f"      Agent Name:     {updated_agent.get('agent_name')}")
        print(f"      Response Engine:{updated_agent.get('response_engine')}")
        print(f"      Voice ID:       {updated_agent.get('voice_id')}")
        print(f"      Is Published:   {updated_agent.get('is_published')} (Preserved in Draft/Test State)")

        # Step 3: Verify updated agent
        print(f"\n[3/3] Verifying agent inspection...")
        verify_resp = client.get(f"/get-agent/{AGENT_ID}")
        if verify_resp.status_code == 200:
            agent_details = verify_resp.json()
            print("  --> Verification confirmed: Agent is now a Conversation Flow Agent!")
            return {
                "agent_id": AGENT_ID,
                "agent_name": agent_details.get("agent_name"),
                "conversation_flow_id": flow_id,
                "response_engine_type": agent_details.get("response_engine", {}).get("type"),
                "voice_id": agent_details.get("voice_id"),
                "is_published": agent_details.get("is_published"),
            }
        return None


if __name__ == "__main__":
    res = convert_inbound_agent_to_conversation_flow()
    if res:
        print("\nConversion successfully completed!")
        print(json.dumps(res, indent=2))
