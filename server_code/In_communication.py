import anvil.server, anvil.secrets, requests

# ---- Load credentials & settings ----
ODOO_URL = anvil.secrets.get_secret("ODOO_URL").rstrip("/")
ODOO_DB = anvil.secrets.get_secret("ODOO_DB")
ODOO_KEY = anvil.secrets.get_secret("ODOO_API_KEY").strip()
CAMPAIGN_NAMES = [
  name.strip() for name in anvil.secrets.get_secret("ODOO_CAMPAIGNS").split(",")
]

HEADERS = {
  "Authorization": f"bearer {ODOO_KEY}",
  "Content-Type": "application/json; charset=utf-8",
  "X-Odoo-Database": ODOO_DB,
}


def _json2(model: str, method: str, body: dict):
  """Minimal JSON-2 client for Odoo Online."""
  url = f"{ODOO_URL}/json_2"
  payload = {"model": model, "method": method, **body}
  r = requests.post(url, json=payload, headers=HEADERS, timeout=20)
  r.raise_for_status()
  return r.json().get("result")


# ---- Main endpoint triggered by Odoo webhook ----
@anvil.server.http_endpoint(
  "/lead_in_comm/afbf9e4a-95b9-4d8a-9ef9-8a86dfa65966", methods=["POST"]
)
def lead_in_comm(**kwargs):
  data = anvil.server.request.body_json or kwargs
  lead_id = data.get("id") or data.get("_id")

  if not lead_id:
    return {"error": "Missing lead ID"}

  print(f"Processing Lead ID {lead_id}")

  # For each campaign name → find campaign → find participant → delete
  for name in CAMPAIGN_NAMES:
    campaigns = _json2(
      "marketing.campaign",
      "search_read",
      {"domain": [["name", "=", name]], "fields": ["id", "name"]},
    )

    if not campaigns:
      print(f"⚠️ Campaign '{name}' not found.")
      continue

    campaign_id = campaigns[0]["id"]
    print(f"→ Campaign {name} (ID {campaign_id})")

    # Find participant(s)
    participants = _json2(
      "marketing.participant",
      "search_read",
      {
        "domain": [
          ["campaign_id", "=", campaign_id],
          ["res_id", "=", lead_id],
          ["model_id.model", "=", "crm.lead"],
        ],
        "fields": ["id"],
      },
    )

    if participants:
      ids = [p["id"] for p in participants]
      _json2("marketing.participant", "unlink", {"args": [ids]})
      print(f"✅ Deleted participants {ids} from {name}")
    else:
      print(f"ℹ️ No participants found for {name}")

    # Reset the boolean flag
  _json2("crm.lead", "write", {"args": [[lead_id], {"x_studio_in_communication": False}]})
  _json2("crm.lead", "write", {"args": [[lead_id], {"x_studio_in_communication": True}]})
  print(f"✅ Reset x_in_comm_email_sent for Lead {lead_id}")

  return {"ok": True, "lead_id": lead_id}
