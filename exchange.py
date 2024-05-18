import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI

authorization_code = '2fc1bc1f157916be023476bc080640560c58fe21'  # Replace with the code obtained from the redirect URL

response = requests.post(
    'https://www.strava.com/api/v3/oauth/token',
    data={
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'code': authorization_code,
        'grant_type': 'authorization_code'
    }
)

tokens = response.json()
print(tokens)

# Update config.py with new tokens
new_access_token = tokens.get('access_token')
new_refresh_token = tokens.get('refresh_token')

if new_access_token and new_refresh_token:
    with open('config.py', 'r') as file:
        config = file.readlines()

    for i, line in enumerate(config):
        if line.startswith('STRAVA_ACCESS_TOKEN'):
            config[i] = f'STRAVA_ACCESS_TOKEN = \'{new_access_token}\'\n'
        if line.startswith('STRAVA_REFRESH_TOKEN'):
            config[i] = f'STRAVA_REFRESH_TOKEN = \'{new_refresh_token}\'\n'

    with open('config.py', 'w') as file:
        file.writelines(config)
else:
    print("Failed to obtain new tokens. Please check your credentials.")
