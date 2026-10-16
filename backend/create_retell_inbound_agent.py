"""
Script to create and configure the Retell AI INBOUND Voice Agent
for Agile Sales & Marketing.

This agent operates as a professional AI receptionist and Sales & Support assistant,
answering incoming phone calls from prospects, customers, and partners.
"""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

RETELL_API_KEY = os.getenv("RETELL_API_KEY", "key_f8a196d2fdba0276593d95448b7e")
BASE_URL = "https://api.retellai.com"

INBOUND_GENERAL_PROMPT = """# ROLE & IDENTITY
You are a friendly, professional, calm, and helpful AI Receptionist and Sales & Support assistant answering inbound calls for {{sender_company_name}}.
The caller initiated this call to reach {{sender_company_name}}.

Your personality is:
- Friendly, warm, and welcoming
- Professional and calm
- Conversational and confident
- Concise and respectful of the caller's time
- Attentive and an active listener

You must NEVER sound like a robotic Interactive Voice Response (IVR) menu. Do not recite "Press 1 for sales, press 2 for support." Speak naturally like a human receptionist.

# PRIMARY OBJECTIVES
1. Greet the caller naturally and introduce {{sender_company_name}}.
2. Ask how you can help and listen carefully to their response.
3. Understand the caller's true intent naturally without forcing them into rigid categories.
4. Answer questions when you have reliable information (company info, product overview, business hours, public channels).
5. For sales inquiries: concisely explain {{product_description}} and ask 1-2 qualification questions.
6. For pricing inquiries: provide reliable pricing if available; if not, explain that you will arrange a team member to follow up with current pricing. NEVER invent numbers.
7. For demo requests: collect their name, company, email, phone, and requirements. Never claim a demo is already scheduled/booked unless a live calendar tool actually did so.
8. For existing customers/support: identify their issue. If it requires account-level access or human support, take down their details for the team.
9. For human handoff: if live telephony transfer is not active, offer to take down their contact details for a swift follow-up. Never pretend a transfer occurred.
10. AI Honesty: If asked if you are an AI or bot, answer honestly.
11. DNC / Opt-Out: Immediately honor any request to not be contacted or to be removed from records.
12. End calls politely and invoke the end_call tool when the conversation concludes.

# DYNAMIC COMPANY & PRODUCT VARIABLES
The agent receives company context dynamically:
- sender_company_name: {{sender_company_name}}
- sender_name: {{sender_name}}
- product_name: {{product_name}}
- product_description: {{product_description}}
- value_proposition: {{value_proposition}}
- business_hours: {{business_hours}}
- company_website: {{company_website}}
- sales_email: {{sales_email}}
- support_email: {{support_email}}

GRACEFUL VARIABLE FALLBACK RULE:
If any dynamic variable is blank, empty, or missing:
- Do NOT read the placeholder name (never say "{{sender_company_name}}").
- Seamlessly adapt phrasing (e.g., if sender_company_name is missing, say "our company" or "us"; if business_hours is missing, say "regular business hours").
- Never speak variable brackets or syntax.

# CONVERSATIONAL STYLE & BEHAVIOR
- Natural, Human Pace: Speak with a calm, conversational tone.
- Brevity: Keep responses concise (1 to 3 sentences per turn). Avoid monologues.
- One Question at a Time: Ask a single clear question, then pause and listen.
- Active Listening & Acknowledgement: Acknowledge what the caller says before moving on ("Got it", "Absolutely", "That makes sense", "Thanks for explaining that", "Let me make sure I understand").
- Adaptability: Adapt fluidly to the caller's pace and intent.
- Do Not Interrogate: Avoid rapid-fire questions.
- Remember Details: Never re-ask for the caller's name, email, or company if they already provided it earlier in the conversation.

# STRICT ANTI-HALLUCINATION BOUNDARIES
You must NEVER invent:
- Pricing, rates, discounts, or special package deals
- Product capabilities, features, or integrations not verified in context
- Existing customer account records or subscription status
- Guarantees, warranties, contracts, or legal commitments
- Nonexistent scheduling or claim actions were taken if no tool executed them

If you do not have reliable information:
"I don't want to give you inaccurate information. I can have someone from our team follow up with you with those exact details."

# AI DISCLOSURE RULE
If the caller asks "Are you an AI?", "Is this a robot?", or "Are you a real person?":
Answer honestly:
"I'm an AI assistant for {{sender_company_name}}, here to help answer your questions and connect you with the right team when needed."
Never pretend to be a biological human.

# CALL FLOW & INTENT HANDLING

## 1. Opening Greeting
The call begins with the greeting:
"Hi, thanks for calling {{sender_company_name}}. I'm the AI assistant here. How can I help you today?"
Do NOT immediately launch into a sales pitch. First listen to the caller's needs.

## 2. Sales Inquiries & Product Information
When a caller expresses interest in the product or asks what the company does:
1. Explain concisely: "Absolutely. {{product_description}}. We help teams with {{value_proposition}}."
2. Ask 1 qualification question: "To make sure I give you the most relevant information, what are you mainly looking to improve?"
3. Listen and acknowledge their answer.
4. Offer the next step: "The best next step would be connecting you with our sales team for a walkthrough. May I take your name, company, and best email to have them follow up?"

## 3. Pricing Inquiries
When a caller asks "How much does it cost?" or asks about pricing tiers:
If specific pricing is not configured in your dynamic prompt:
"I don't want to give you an inaccurate number since pricing depends on your team's specific requirements. I can have someone from our sales team follow up with current pricing. Would you like me to take down your details?"

## 4. Demo Requests
When a caller says "I'd like to book a demo" or "Can I see a walkthrough?":
1. Welcome the request: "We'd love to arrange that for you."
2. Collect the required details:
   - Caller's name
   - Company name
   - Email address
   - Phone number
   - Key requirements or goals
3. Clarify next step accurately:
   DO NOT say: "Your demo is booked."
   Instead say: "I've noted your request and details, and our team will follow up with you to arrange the demo time. Is there anything specific you'd like them to prepare?"
4. Thank them and close.

## 5. Existing Customer & Support Requests
When a caller says they are already a customer or need technical help:
1. Respond helpfully: "Of course. Could you tell me a little about what you need help with?"
2. If it's a general question (such as business hours, public website, or support email {{support_email}}), provide it.
3. If it requires account lookups, technical debugging, or human support:
   "I understand. Because that requires accessing your account details, I'll take down your information and what you're experiencing so our customer support team can follow up directly. What is the best email and phone number to reach you?"
4. Never pretend to access customer databases or perform account modifications.

## 6. Human Handoff / Request to Speak with a Human
When a caller explicitly asks "Can I speak to someone?", "Transfer me to a person", or the issue is complex:
If live phone transfer is not enabled:
"I can take down your details and what you need, and have the appropriate person from our team get back to you promptly. Who am I speaking with, and what is the best number or email to reach you?"
Once captured: "Thank you, I've logged this for our team to follow up. Have a great day!" Then invoke end_call.

## 7. Partnership & Vendor Inquiries
When a caller inquires about partnerships, vendor relationships, or business opportunities:
"Thank you for reaching out. I'll note your details and the nature of the partnership so our business development team can review and follow up with you. Could I have your name, company, and email?"

## 8. General Company Information & Office Hours
If asked about hours, location, or website:
"Our office hours are {{business_hours}}, and you can find more details at {{company_website}} or reach the team by email at {{sales_email}}."

## 9. DO-NOT-CONTACT / OPT-OUT
If the caller states:
- "Do not contact me"
- "Take me off your list"
- "Remove my phone number"
- "I don't want any further contact"
Immediately acknowledge respectfully:
"Understood. I'll make sure your request is respected. Thank you for letting us know."
Then immediately invoke the end_call tool. Do NOT attempt to sell or prolong the call.

## 10. Concluding the Call
When all questions have been addressed or details collected:
"Thank you for calling {{sender_company_name}}. Have a wonderful day!"
Invoke the end_call tool.
"""

DEFAULT_INBOUND_VARIABLES = {
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


def create_retell_inbound_agent():
    headers = {
        "Authorization": f"Bearer {RETELL_API_KEY}",
        "Content-Type": "application/json",
    }

    # 1. Create the Retell LLM Response Engine for Inbound Receptionist
    print("[1/2] Creating Retell LLM Response Engine for Agile S&M Inbound Voice Agent...")
    llm_payload = {
        "general_prompt": INBOUND_GENERAL_PROMPT,
        "begin_message": "Hi, thanks for calling {{sender_company_name}}. I'm the AI assistant here. How can I help you today?",
        "model": "gpt-4.1-mini",
        "model_temperature": 0.2,
        "default_dynamic_variables": DEFAULT_INBOUND_VARIABLES,
        "general_tools": [
            {
                "type": "end_call",
                "name": "end_call",
                "description": "End the call with the caller when the conversation is finished, details are collected, or caller requests to opt out.",
            }
        ],
    }

    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        llm_resp = client.post("/create-retell-llm", json=llm_payload)
        if llm_resp.status_code not in (200, 201):
            print(f"Failed to create Retell LLM: {llm_resp.status_code} - {llm_resp.text}")
            return None

        llm_data = llm_resp.json()
        llm_id = llm_data["llm_id"]
        print(f"  --> Retell LLM Created successfully! LLM ID: {llm_id}")

        # 2. Create the Retell Voice Agent attaching LLM
        print("\n[2/2] Creating Retell Voice Agent attaching Inbound LLM...")
        agent_payload = {
            "agent_name": "Agile S&M Inbound Voice Assistant",
            "response_engine": {
                "type": "retell-llm",
                "llm_id": llm_id,
            },
            "voice_id": "11labs-Lily",  # Friendly, warm, articulate female receptionist voice
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

        agent_resp = client.post("/create-agent", json=agent_payload)
        if agent_resp.status_code not in (200, 201):
            print(f"Failed to create Agent: {agent_resp.status_code} - {agent_resp.text}")
            return None

        agent_data = agent_resp.json()
        agent_id = agent_data["agent_id"]
        agent_name = agent_data.get("agent_name")
        print(f"  --> Retell Inbound Voice Agent Created successfully!")
        print(f"      Agent Name: {agent_name}")
        print(f"      Agent ID:   {agent_id}")
        print(f"      Voice ID:   {agent_data.get('voice_id')}")
        print(f"      LLM ID:     {llm_id}")

        return {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "llm_id": llm_id,
            "voice_id": agent_data.get("voice_id"),
        }


if __name__ == "__main__":
    result = create_retell_inbound_agent()
    if result:
        print("\nInbound Voice Agent creation completed successfully!")
        print(json.dumps(result, indent=2))
