from flask import Flask, request, jsonify, redirect, url_for, session, render_template
from authlib.integrations.flask_client import OAuth
import requests
import datetime
import os

app = Flask(__name__)
app.secret_key = 'random_secret_key'
oauth = OAuth(app)

strava = oauth.register(
    name='strava',
    client_id=os.getenv('STRAVA_CLIENT_ID'),
    client_secret=os.getenv('STRAVA_CLIENT_SECRET'),
    authorize_url='https://www.strava.com/oauth/authorize',
    authorize_params=None,
    access_token_url='https://www.strava.com/oauth/token',
    access_token_params=None,
    client_kwargs={'scope': 'read,activity:write,activity:read_all'}
)

@app.route('/')
def index():
    if 'strava_token' in session:
        return render_template('index.html', token=session['strava_token'])
    return render_template('login.html')

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return strava.authorize_redirect(redirect_uri)

@app.route('/logout')
def logout():
    session.pop('strava_token', None)
    return redirect(url_for('index'))

@app.route('/authorize')
def authorize():
    token = strava.authorize_access_token()
    session['strava_token'] = token
    return redirect(url_for('index'))

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
    headers = {
        'Authorization': f'Bearer {session["strava_token"]["access_token"]}'
    }

    response = requests.get(
        'https://www.strava.com/api/v3/athlete/activities',
        headers=headers,
        params={'per_page': 200}
    )

    print(f"Response Status Code: {response.status_code}")

    if response.status_code != 200:
        print(f"Failed to fetch activities: {response.text}")
        return

    activities = response.json()
    days_run, total_days = calculate_days_run_this_year(activities)

    # Get the activity to update
    activity_response = requests.get(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers
    )

    if activity_response.status_code != 200:
        print(f"Failed to fetch activity {activity_id}: {activity_response.text}")
        return

    activity = activity_response.json()

    # Update the description
    new_description = f"{activity.get('description', '')}\nDays run this year: {days_run}/{total_days}"
    update_response = requests.put(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers,
        data={'description': new_description}
    )

    if update_response.status_code == 200:
        print(f"Activity {activity_id} updated successfully")
    else:
        print(f"Failed to update activity {activity_id}: {update_response.status_code} {update_response.text}")

def calculate_days_run_this_year(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    run_dates = set()

    for activity in activities:
        if activity['type'] == 'Run':
            run_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z').date()
            if run_date >= start_of_year.date():
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
