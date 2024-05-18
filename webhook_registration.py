import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

CALLBACK_URL = 'https://2744-109-25-96-79.ngrok-free.app/webhook'  # Replace with your actual ngrok URL

create_url = 'https://www.strava.com/api/v3/push_subscriptions'
response = requests.post(
    create_url,
    data={
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'callback_url': CALLBACK_URL,
        'verify_token': 'STRAVA'
    }
)

print(f"Create Status Code: {response.status_code}")
print(response.json())
