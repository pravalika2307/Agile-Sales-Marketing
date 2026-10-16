from app.core.database import SessionLocal
from app.models.lead import Lead
from app.models.crm import Company, Contact, Deal
from app.models.outreach import Outreach
from app.models.campaign import Campaign
from app.models.call_record import CallRecord
from app.models.hubspot_sync import HubSpotSyncRun

db = SessionLocal()

print("--- OUTREACH RECORDS WITH DETAILS ---")
outreaches = db.query(Outreach).all()
for o in outreaches:
    print(f"  ID={o.id}\n    org={o.organization_id}\n    recipient={o.recipient}\n    status={o.status}\n    channel={o.channel}\n    provider={o.provider}\n    provider_msg_id={o.provider_message_id}\n    campaign_id={o.campaign_id}\n    contact_id={o.contact_id}\n    call_record_id={o.call_record_id}\n    subject={o.subject}\n    created_at={o.created_at}\n    sent_at={o.sent_at}")

print("\n--- HUBSPOT CONTACTS VS COMPANIES IN DB ---")
contacts_with_company = db.query(Contact).filter(Contact.company_id.isnot(None)).count()
contacts_without_company = db.query(Contact).filter(Contact.company_id.is_(None)).count()
print(f"Contacts with company_id: {contacts_with_company}, without company_id: {contacts_without_company}")

leads_with_company = db.query(Lead).filter(Lead.company_id.isnot(None)).count()
leads_without_company = db.query(Lead).filter(Lead.company_id.is_(None)).count()
print(f"Leads with company_id: {leads_with_company}, without company_id: {leads_without_company}")

db.close()
