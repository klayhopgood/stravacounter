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


def calculate_days_run_this_year():
    headers = {
        'Authorization': f'Bearer {STRAVA_ACCESS_TOKEN}'
    }

    # Get the current date and the start of the year
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    activities = []
    page = 1
    per_page = 200
    fetched_all = False

    while not fetched_all:
        response = requests.get(
            f'https://www.strava.com/api/v3/athlete/activities',
            headers=headers,
            params={'page': page, 'per_page': per_page}
        )

        if response.status_code != 200:
            print(f"Failed to fetch activities: {response.text}")
            return 0, 0

        data = response.json()
        activities.extend(data)

        # Check if we've fetched all activities
        if len(data) < per_page:
            fetched_all = True
        else:
            page += 1

        # Filter out activities older than the start of the year
        activities = [activity for activity in activities if
                      datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%SZ') >= start_of_year]

    run_dates = set()

    for activity in activities:
        if activity['type'] == 'Run':
            run_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%SZ').date()
            run_dates.add(run_date)
            print(f"Counted Run Date: {run_date}")

    days_run = len(run_dates)
    total_days = (today - start_of_year).days + 1

    return days_run, total_days

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
