import requests

client_id = '99652'
client_secret = '2dc10e8d62b4925837aac970b6258fc3eae96c63'
code = '4c9b054b3a28fe591670ffd6fb2f6c912c68f5ee'  # Replace with the actual authorization code

response = requests.post(
    'https://www.strava.com/oauth/token',
    data={
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code'
    }
)

print(response.json())
