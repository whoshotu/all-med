from dotenv import load_dotenv
import os, requests, time

load_dotenv()
api_key = os.environ.get("CALLE_API_KEY")
url = "https://api.heycall-e.com/v1/calls"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

# 1. Create call
print("Creating call...")
resp = requests.post(
    url, 
    headers=headers, 
    json={"task": "Hello, this is a test call.", "recipients": [{"phones": ["+16615315664"], "region": "US"}]},
    timeout=60
)
print("Create response HTTP:", resp.status_code)
data = resp.json()
print("Create response JSON:", data)

if "id" in data:
    call_id = data["id"]
    print("\nPolling call:", call_id)
    # 2. Poll
    for i in range(5):
        time.sleep(3)
        poll_resp = requests.get(f"{url}/{call_id}", headers=headers)
        print("Poll response HTTP:", poll_resp.status_code)
        print("Poll response JSON:", poll_resp.json())
