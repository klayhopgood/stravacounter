import requests
from config import STRAVA_ACCESS_TOKEN

print(f"Using access token: {STRAVA_ACCESS_TOKEN}")

url = 'https://www.strava.com/api/v3/push_subscriptions'
headers = {
    'Authorization': f'Bearer {STRAVA_ACCESS_TOKEN}'
}
response = requests.get(url, headers=headers)
print(response.json())
