import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

def make_the_call(target_phone_number):
    auth_id = os.getenv("VOBIZ_AUTH_ID")
    auth_token = os.getenv("VOBIZ_AUTH_TOKEN")
    
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
    
    headers = {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": os.getenv("VOBIZ_DID"),
        "to": target_phone_number,
        "answer_url": f"{os.getenv('PUBLIC_URL')}/answer",
        "answer_method": "POST"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code in [200, 201]:
        data = response.json()
        # Fix: Get the ID using 'call_uuid' as per the Vobiz response format
        call_id = data.get("call_uuid") 
        print(f"Success! Call fired. SID: {call_id}")
    else:
        print(f"Failed: {response.text}") # THIS WILL TELL US WHY IT FAILED

if __name__ == "__main__":
    # Ensure your number is in +91... format
    make_the_call("+918921898022")