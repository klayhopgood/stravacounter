from flask import Flask, request, jsonify
import requests
import datetime

app = Flask(__name__)

VERIFY_TOKEN = 'STRAVA'
ACCESS_TOKEN = 'd0501c0ca101046b32d3839d7f409339ba8c3d01'  # Use your actual access token

processed_activities = set()  # Set to keep track of processed activities

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode and token:
            if mode == 'subscribe' and token == VERIFY_TOKEN:
                return jsonify({'hub.challenge': challenge}), 200
            else:
                return 'Verification failed', 403

    if request.method == 'POST':
        event = request.get_json()
        print(f"Received event: {event}")  # Log the event for debugging purposes

        # Handle activity creation event
        if event['object_type'] == 'activity':
            if event['aspect_type'] == 'create':
                handle_activity_create(event['object_id'])
            elif event['aspect_type'] == 'delete':
                handle_activity_delete(event['object_id'])

        return '', 200

def handle_activity_create(activity_id):
    if activity_id in processed_activities:
        print(f"Activity ID {activity_id} already processed.")
        return

    print(f"Processing activity creation for activity ID: {activity_id}")  # Log activity processing
    # Calculate days run this year
    days_run, total_days = calculate_days_run_this_year()
    description = f"{days_run}/{total_days} days run this year"

    # Update activity description
    update_activity_description(activity_id, description)

    processed_activities.add(activity_id)  # Mark activity as processed

def handle_activity_delete(activity_id):
    print(f"Processing activity deletion for activity ID: {activity_id}")  # Log activity deletion
    if activity_id in processed_activities:
        processed_activities.remove(activity_id)  # Remove from processed activities if it was previously processed

def calculate_days_run_this_year():
    # Get the current year and the date 13 months ago
    current_year = datetime.datetime.now().year
    thirteen_months_ago = datetime.datetime.now() - datetime.timedelta(days=13*30)

    # Fetch activities for the past 13 months, handling pagination
    url = 'https://www.strava.com/api/v3/athlete/activities'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
    params = {'per_page': 200, 'page': 1}

    run_days = set()
    while True:
        response = requests.get(url, headers=headers, params=params)
        print(f"Response Status Code: {response.status_code}")  # Debug: Print response status code
        if response.status_code == 401:
            print("Authorization error. Please check your access token.")
            break
        if response.status_code != 200:
            print(f"Failed to fetch activities: {response.text}")
            break

        activities = response.json()
        print(f"Fetched {len(activities)} activities")  # Debug: Print number of activities fetched
        if not activities:
            break

        for activity in activities:
            if activity.get('type') == 'Run':
                run_date_local = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%SZ')
                # Only consider runs from the current year
                if run_date_local.year == current_year:
                    print(f"Counted Run Date: {run_date_local.date()}")  # Debug: Print each counted run date
                    run_days.add(run_date_local.date())
                # Stop if the activity is older than 13 months
                if run_date_local < thirteen_months_ago:
                    return len(run_days), (datetime.date.today() - datetime.date(current_year, 1, 1)).days + 1

        params['page'] += 1

    # Calculate the total days into the year
    total_days = (datetime.date.today() - datetime.date(current_year, 1, 1)).days + 1

    return len(run_days), total_days

def update_activity_description(activity_id, description):
    url = f'https://www.strava.com/api/v3/activities/{activity_id}'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
    data = {'description': description}

    response = requests.put(url, headers=headers, data=data)
    if response.status_code == 401:
        print("Authorization error. Please check your access token.")
        return
    if response.status_code == 200:
        print(f'Activity {activity_id} updated successfully')
    else:
        print(f'Failed to update activity {activity_id}: {response.status_code} {response.text}')

if __name__ == '__main__':
    app.run(debug=True, port=8000)  # Ensure this matches the Gunicorn port
