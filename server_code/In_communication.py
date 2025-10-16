import anvil.server, anvil.secrets, requests, json, time

# ======================================================
# ---- Load credentials & settings ----
# ======================================================
ODOO_URL = anvil.secrets.get_secret("ODOO_URL").rstrip(
  "/"
)  # e.g. https://patiofactory.odoo.com/odoo
ODOO_DB = anvil.secrets.get_secret("ODOO_DB")
ODOO_KEY = anvil.secrets.get_secret("ODOO_API_KEY").strip()
CAMPAIGN_NAMES = [
  n.strip() for n in anvil.secrets.get_secret("ODOO_CAMPAIGNS").split(",")
]

HEADERS = {
  "Authorization": f"bearer {ODOO_KEY}",
  "Content-Type": "application/json; charset=utf-8",
  "X-Odoo-Database": ODOO_DB,
}

_campaign_cache = {}


# ======================================================
# ---- Generic JSON-2 call ----
# ======================================================
def _json2(model: str, method: str, body: dict):
  """Call Odoo JSON-2 endpoint with full logging and robust result parsing."""
  url = f"{ODOO_URL}/json/2/{model}/{method}"
  try:
    r = requests.post(url, json=body, headers=HEADERS, timeout=20)
    if r.status_code != 200:
      print(f"❌ {r.status_code} {r.reason} → {url}")
      print("Request body:", json.dumps(body))
      print("Response:", r.text)
      r.raise_for_status()

    data = r.json()

    # --- Normalize different Odoo JSON-2 return formats ---
    if isinstance(data, bool):
      # e.g. result of write(), unlink() → True
      return data
    elif isinstance(data, list):
      # e.g. search_read results
      return data
    elif isinstance(data, dict):
      # sometimes contains "result", sometimes direct structure
      return data.get("result", data)
    else:
      print(f"⚠️ Unexpected response type: {type(data)}")
      return None

  except Exception as e:
    print(f"🔥 Exception calling {model}.{method}: {e}")
    return None


# ======================================================
# ---- Helper: Get campaign ID (cached) ----
# ======================================================
def _get_campaign_id(name: str):
  """Return campaign ID by name using cache for performance."""
  if name in _campaign_cache:
    return _campaign_cache[name]

  body = {
    "ids": [],  # Required due to Odoo bug in controller
    "domain": [["name", "=", name]],
    "fields": ["id", "name"],
    "context": {},
  }
  res = _json2("marketing.campaign", "search_read", body)

  if res and isinstance(res, list) and len(res) > 0 and "id" in res[0]:
    cid = res[0]["id"]
    _campaign_cache[name] = cid
    return cid

  print(f"⚠️ No campaign record found for '{name}'. Raw response: {res}")
  return None


# ======================================================
# ---- Main webhook endpoint ----
# ======================================================
@anvil.server.http_endpoint(
  "/lead_in_comm/afbf9e4a-95b9-4d8a-9ef9-8a86dfa65966", methods=["POST"]
)
def lead_in_comm(**kwargs):
  """Triggered by Odoo webhook when lead enters 'In Communication' stage."""
  data = anvil.server.request.body_json or kwargs
  lead_id = data.get("id") or data.get("_id")
  if not lead_id:
    return {"error": "Missing lead ID"}

  print(f"\n=== Processing Lead ID {lead_id} ===")

  for name in CAMPAIGN_NAMES:
    campaign_id = _get_campaign_id(name)
    if not campaign_id:
      print(f"⚠️ Campaign '{name}' not found or inaccessible.")
      continue

    print(f"→ Campaign '{name}' (ID {campaign_id})")

    # --- find participants ---
    part_body = {
      "ids": [],
      "domain": [
        ["campaign_id", "=", campaign_id],
        ["res_id", "=", lead_id],
        ["model_id.model", "=", "crm.lead"],
      ],
      "fields": ["id"],
      "context": {},
    }
    participants = _json2("marketing.participant", "search_read", part_body)

    if participants:
      ids = [p["id"] for p in participants if "id" in p]
      if ids:
        del_body = {"ids": ids, "context": {}}
        res = _json2("marketing.participant", "unlink", del_body)
        print(f"✅ Deleted participants {ids} → {res}")
      else:
        print(f"ℹ️ Participants found but missing IDs: {participants}")
    else:
      print(f"ℹ️ No participants found for '{name}'")

    # --- reset boolean field ---
  print("→ Resetting x_studio_in_communication flag...")
  off_result = on_result = None

  off_body = {
    "ids": [lead_id],
    "vals": {"x_studio_in_communication": False},
    "context": {},
  }
  on_body = {
    "ids": [lead_id],
    "vals": {"x_studio_in_communication": True},
    "context": {},
  }

  off_result = _json2("crm.lead", "write", off_body)
  time.sleep(1)
  on_result = _json2("crm.lead", "write", on_body)

  print(f"✅ Flag reset for Lead {lead_id} (off→on) → {on_result}")
  return {"ok": True, "lead_id": lead_id, "result": on_result}
