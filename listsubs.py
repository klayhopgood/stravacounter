import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

response = requests.get(
    'https://www.strava.com/api/v3/push_subscriptions',
    params={
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET
    }
)

# Print response status code and raw text for debugging
print(f"Status Code: {response.status_code}")
print(f"Response Text: {response.text}")


