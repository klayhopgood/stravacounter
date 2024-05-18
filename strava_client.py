import requests
from config import STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REDIRECT_URI, STRAVA_ACCESS_TOKEN

class StravaClient:
    def __init__(self):
        self.access_token = STRAVA_ACCESS_TOKEN
        self.base_url = 'https://www.strava.com/api/v3'

    def get_authorization_url(self):
        return (
            f"https://www.strava.com/oauth/authorize?client_id={STRAVA_CLIENT_ID}"
            f"&response_type=code&redirect_uri={STRAVA_REDIRECT_URI}"
            f"&scope=activity:read_all,activity:write"
        )

    def exchange_code_for_token(self, code):
        url = 'https://www.strava.com/oauth/token'
        payload = {
            'client_id': STRAVA_CLIENT_ID,
            'client_secret': STRAVA_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code'
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        self.access_token = response.json()['access_token']
        return response.json()

    def get_activities(self):
        url = f'{self.base_url}/athlete/activities'
        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_days_run_in_year(self):
        activities = self.get_activities()
        current_year = datetime.now().year
        days_run = set()

        for activity in activities:
            if activity['type'] == 'Run':
                activity_date = datetime.strptime(activity['start_date'], '%Y-%m-%dT%H:%M:%SZ')
                if activity_date.year == current_year:
                    days_run.add(activity_date.date())

        return len(days_run)

    def get_days_in_current_year(self):
        now = datetime.now()
        start_of_year = datetime(now.year, 1, 1)
        return (now - start_of_year).days + 1

    def update_activity(self, activity_id, description):
        url = f'{self.base_url}/activities/{activity_id}'
        headers = {'Authorization': f'Bearer {self.access_token}'}
        response = requests.put(url, headers=headers, data={'description': description})
        response.raise_for_status()
        return response.json()

    def update_latest_activity(self, description):
        activities = self.get_activities()
        latest_activity_id = activities[0]['id']
        self.update_activity(latest_activity_id, description)
