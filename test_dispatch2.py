from dotenv import load_dotenv
import os, requests

load_dotenv()
api_key = os.environ.get("CALLE_API_KEY")
url = "https://api.heycall-e.com/v1/calls"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

# Test standard recipient payload
payload = {
    "task": "Test call",
    "recipients": [
        {
            "phones": ["+16615315664"],
            "region": "US",
            "from": "+16615315664" # Just testing if "from" is the right key
        }
    ]
}
print("Testing 'from' key in recipient:")
resp = requests.post(url, headers=headers, json=payload, timeout=10)
print(resp.status_code)
print(resp.json())

# Test standard from_phone field
payload2 = {
    "task": "Test call",
    "from_phone": "+16615315664",
    "recipients": [
        {
            "phones": ["+16615315664"],
            "region": "US"
        }
    ]
}
print("\nTesting 'from_phone' key at root:")
resp2 = requests.post(url, headers=headers, json=payload2, timeout=10)
print(resp2.status_code)
print(resp2.json())
