"""Run end-to-end outreach flow for pravalikapalle@agilereceivables.com"""
import asyncio
import json
from httpx import ASGITransport, AsyncClient
from app.main import app

TARGET_EMAIL = "pravalikapalle@agilereceivables.com"

async def main():
    print(f"=== Starting Email Outreach Run for {TARGET_EMAIL} ===")
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Step 1: Register/Authenticate Tenant
        print("\n[Step 1] Authenticating / Registering Tenant...")
        reg_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "admin@agilereceivables.com",
                "password": "Password123!",
                "full_name": "Agile Admin",
                "organization_name": "Agile Receivables Org",
            },
        )
        if reg_resp.status_code == 201:
            token = reg_resp.json()["tokens"]["access_token"]
            print("  Registered new admin tenant successfully.")
        else:
            # Try login if already registered
            login_resp = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": "admin@agilereceivables.com",
                    "password": "Password123!",
                },
            )
            assert login_resp.status_code == 200, f"Auth failed: {login_resp.text}"
            token = login_resp.json()["tokens"]["access_token"]
            print("  Logged in existing admin tenant successfully.")

        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Create Campaign
        print("\n[Step 2] Creating Campaign...")
        camp_resp = await client.post(
            "/api/v1/campaigns",
            json={
                "name": "Live Outreach Verification",
                "type": "sales_outbound",
                "description": "Integration verification campaign for SES v2 outreach pipeline",
            },
            headers=headers,
        )
        assert camp_resp.status_code == 201, f"Campaign creation failed: {camp_resp.text}"
        campaign = camp_resp.json()
        campaign_id = campaign["id"]
        print(f"  Campaign created: ID={campaign_id}, Name='{campaign['name']}'")

        # Step 3: Create Contact
        print(f"\n[Step 3] Creating Contact for {TARGET_EMAIL}...")
        cont_resp = await client.post(
            "/api/v1/contacts",
            json={
                "email": TARGET_EMAIL,
                "first_name": "Pravalika",
                "last_name": "Palle",
                "job_title": "Lead",
            },
            headers=headers,
        )
        assert cont_resp.status_code == 201, f"Contact creation failed: {cont_resp.text}"
        contact = cont_resp.json()
        contact_id = contact["id"]
        print(f"  Contact created: ID={contact_id}, Email={contact['email']}")

        # Step 4: Enroll Contact into Campaign
        print("\n[Step 4] Enrolling Contact into Campaign...")
        enr_resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/contacts/{contact_id}",
            json={"enrollment_status": "queued"},
            headers=headers,
        )
        assert enr_resp.status_code == 201, f"Enrollment failed: {enr_resp.text}"
        enrollment = enr_resp.json()
        campaign_contact_id = enrollment["id"]
        print(f"  Enrollment created: ID={campaign_contact_id}, Status={enrollment['enrollment_status']}")

        # Step 5: Create Draft Outreach
        print("\n[Step 5] Creating Draft Outreach Item...")
        outreach_payload = {
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "campaign_contact_id": campaign_contact_id,
            "channel": "email",
            "subject": "Agile Sales & Marketing Integration Test",
            "body": "Hi Pravalika,\n\nThis is a live verification email confirming that the Agile Sales & Marketing outreach system has been successfully integrated with AWS SES v2.\n\nBest regards,\nAgile Sales & Marketing Team",
        }
        out_resp = await client.post(
            "/api/v1/outreach",
            json=outreach_payload,
            headers=headers,
        )
        assert out_resp.status_code == 201, f"Draft outreach creation failed: {out_resp.text}"
        draft_outreach = out_resp.json()
        outreach_id = draft_outreach["id"]
        print(f"  Draft Outreach created: ID={outreach_id}, Status={draft_outreach['status']}")

        # Step 6: Dispatch / Send Outreach
        print(f"\n[Step 6] Dispatching Outreach Email to {TARGET_EMAIL} via configured provider...")
        send_resp = await client.post(
            f"/api/v1/outreach/{outreach_id}/send",
            headers=headers,
        )
        print(f"  HTTP Status Code: {send_resp.status_code}")
        send_data = send_resp.json()
        print("  Send Response:")
        print(json.dumps(send_data, indent=2))
        assert send_resp.status_code == 200, f"Send failed: {send_resp.text}"
        
        provider_msg_id = send_data.get("provider_message_id")
        print(f"\n  >>> RESULT: Email Sent Successfully! Provider={send_data.get('provider')}, MessageId={provider_msg_id} <<<")

        # Step 7: Check Audit Events
        print("\n[Step 7] Checking Outreach Audit Trail...")
        events_resp = await client.get(
            f"/api/v1/outreach/{outreach_id}/events",
            headers=headers,
        )
        events = events_resp.json()
        print(f"  Found {len(events)} lifecycle events:")
        for ev in events:
            print(f"    - Event: {ev['event_type']} at {ev['created_at']}")

        # Step 8: Test Webhook Tracking (Simulating SES Delivery Receipt)
        if provider_msg_id:
            print("\n[Step 8] Ingesting SES Delivery Webhook Notification...")
            webhook_payload = {
                "eventType": "Delivery",
                "mail": {
                    "messageId": provider_msg_id,
                    "destination": [TARGET_EMAIL],
                },
                "delivery": {
                    "timestamp": "2026-10-07T17:25:00.000Z",
                    "processingTimeMillis": 1200,
                    "recipients": [TARGET_EMAIL],
                    "smtpResponse": "250 2.0.0 OK",
                },
            }
            webhook_resp = await client.post(
                "/api/v1/outreach/tracking/ses-webhook",
                json=webhook_payload,
            )
            print(f"  Webhook Response ({webhook_resp.status_code}): {webhook_resp.json()}")

            # Step 9: Re-fetch Outreach to verify first_delivered_at
            print("\n[Step 9] Re-fetching Outreach Item to Verify Updated Delivery State...")
            final_resp = await client.get(
                f"/api/v1/outreach/{outreach_id}",
                headers=headers,
            )
            final_data = final_resp.json()
            print(f"  Current Status: {final_data['status']}")
            print(f"  First Delivered At: {final_data.get('first_delivered_at')}")

if __name__ == "__main__":
    asyncio.run(main())
