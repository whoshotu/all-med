from dotenv import load_dotenv
import os, requests

load_dotenv()
api_key = os.environ.get("CALLE_API_KEY")
url = "https://api.heycall-e.com/v1/calls"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

keys_to_test = ["caller_id", "from_number", "phone_number"]

for key in keys_to_test:
    payload = {
        "task": "Test call",
        key: "+16615315664",
        "recipients": [{"phones": ["+16615315664"], "region": "US"}]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    print(f"Testing root '{key}': {resp.status_code}")
    if resp.status_code != 422:
        print(resp.json())

for key in keys_to_test:
    payload = {
        "task": "Test call",
        "recipients": [{"phones": ["+16615315664"], "region": "US", key: "+16615315664"}]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    print(f"Testing recipient '{key}': {resp.status_code}")
    if resp.status_code != 422:
        print(resp.json())

