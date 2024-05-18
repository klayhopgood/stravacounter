from flask import Flask, request, jsonify
import requests
import datetime

app = Flask(__name__)

VERIFY_TOKEN = 'STRAVA'
ACCESS_TOKEN = 'd0501c0ca101046b32d3839d7f409339ba8c3d01'  # Use your actual access token

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if verify_token == VERIFY_TOKEN:
            return jsonify({'hub.challenge': challenge})
        return 'Invalid verification token', 403
    elif request.method == 'POST':
        event = request.json
        print(f"Received event: {event}")
        if event['object_type'] == 'activity' and event['aspect_type'] == 'create':
            handle_activity_create(event['object_id'])
        return 'Event received', 200

def handle_activity_create(activity_id):
    print(f"Processing activity creation for activity ID: {activity_id}")
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    response = requests.get(f'https://www.strava.com/api/v3/athlete/activities', headers=headers)
    print(f"Response Status Code: {response.status_code}")
    if response.status_code == 200:
        activities = response.json()
        print(f"Fetched {len(activities)} activities")
        days_run, total_days = calculate_days_run_this_year(activities)
        description = f"{days_run}/{total_days} days of running this year!"
        update_activity_description(activity_id, description)
    else:
        print(f"Failed to fetch activities: {response.text}")

def calculate_days_run_this_year(activities):
    now = datetime.datetime.now()
    start_of_year = datetime.datetime(now.year, 1, 1)
    days_run = set()
    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%SZ')
            if activity_date >= start_of_year:
                days_run.add(activity_date.date())
    total_days = (now - start_of_year).days + 1
    return len(days_run), total_days

def update_activity_description(activity_id, description):
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    data = {
        'description': description
    }
    response = requests.put(f'https://www.strava.com/api/v3/activities/{activity_id}', headers=headers, json=data)
    if response.status_code == 200:
        print(f"Activity {activity_id} updated successfully")
    else:
        print(f"Failed to update activity {activity_id}: {response.status_code} {response.text}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
