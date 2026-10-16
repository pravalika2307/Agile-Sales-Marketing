import asyncio
import time
from app.services.integrations.hubspot.client import HubSpotClient
from app.core.config import settings

async def main():
    client = HubSpotClient()
    print("Is configured:", client.is_configured)
    if not client.is_configured:
        print("HubSpot is not configured.")
        return

    # Probe 1: Account info
    t0 = time.time()
    try:
        resp = await client.get("/account-info/v3/details", check_status=False)
        dt = time.time() - t0
        print(f"Account info: status={resp.status_code}, time={dt:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print("Portal ID:", data.get("portalId"), "Account Type:", data.get("accountType"))
    except Exception as e:
        print("Account info error:", e)

    # Probe 2: Contacts
    t0 = time.time()
    try:
        resp = await client.get("/crm/v3/objects/contacts", params={"limit": 5}, check_status=False)
        dt = time.time() - t0
        print(f"Contacts: status={resp.status_code}, time={dt:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print("Contacts sample count:", len(data.get("results", [])), "paging:", data.get("paging"))
    except Exception as e:
        print("Contacts error:", e)

    # Probe 3: Companies
    t0 = time.time()
    try:
        resp = await client.get("/crm/v3/objects/companies", params={"limit": 5}, check_status=False)
        dt = time.time() - t0
        print(f"Companies: status={resp.status_code}, time={dt:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print("Companies sample count:", len(data.get("results", [])), "paging:", data.get("paging"))
        else:
            print("Companies error text:", resp.text[:300])
    except Exception as e:
        print("Companies error:", e)

    # Probe 4: Deals
    t0 = time.time()
    try:
        resp = await client.get("/crm/v3/objects/deals", params={"limit": 5}, check_status=False)
        dt = time.time() - t0
        print(f"Deals: status={resp.status_code}, time={dt:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print("Deals sample count:", len(data.get("results", [])), "paging:", data.get("paging"))
        else:
            print("Deals error text:", resp.text[:300])
    except Exception as e:
        print("Deals error:", e)

    # Probe 5: Token info (oauth / access-tokens)
    t0 = time.time()
    try:
        resp = await client.get(f"/oauth/v1/access-tokens/{client._access_token}", check_status=False)
        dt = time.time() - t0
        print(f"Token info endpoint: status={resp.status_code}, time={dt:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print("Token scopes:", data.get("scopes"))
            print("Hub ID:", data.get("hub_id"))
            print("App ID:", data.get("app_id"))
            print("User:", data.get("user"))
        else:
            print("Token info response:", resp.text[:300])
    except Exception as e:
        print("Token info error:", e)

if __name__ == "__main__":
    asyncio.run(main())
