import anvil.server


@anvil.server.http_endpoint("/lead_in_comm/afbf9e4a-95b9-4d8a-9ef9-8a86dfa65966", methods=["POST"])
def lead_in_communication(**kwargs):
  print("Webhook received:", kwargs)
  # You can later verify HMAC, write to Data Table, send SMS, etc.
  return {"status": "ok"}
