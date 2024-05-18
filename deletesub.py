import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET

# Replace with the actual subscription ID you want to delete
subscription_id = '258814'

response = requests.delete(
    f'https://www.strava.com/api/v3/push_subscriptions/{subscription_id}',
    params={
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET
    }
)

print(f"Status Code: {response.status_code}")
print(f"Response Text: {response.text}")
