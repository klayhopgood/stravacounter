from flask import Flask, redirect, url_for, session, request, jsonify, render_template
import requests
import datetime
import os
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = os.urandom(24)

VERIFY_TOKEN = 'STRAVA'

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login')
def login():
    strava_authorize_url = (
        f"https://www.strava.com/oauth/authorize?client_id={os.getenv('STRAVA_CLIENT_ID')}&response_type=code"
        f"&redirect_uri={quote(os.getenv('REDIRECT_URI'), safe='')}&approval_prompt=force&scope=read,activity:write,activity:read_all"
    )
    return redirect(strava_authorize_url)

@app.route('/authorize')
def authorize():
    code = request.args.get('code')
    token_response = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': os.getenv('STRAVA_CLIENT_ID'),
            'client_secret': os.getenv('STRAVA_CLIENT_SECRET'),
            'code': code,
            'grant_type': 'authorization_code'
        }
    )
    token_json = token_response.json()
    session['strava_token'] = token_json
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'strava_token' not in session:
        return redirect(url_for('login'))
    token = session['strava_token']['access_token']
    return f"Welcome to Strava Counter<br>Your access token: {token}<br><a href='/logout'>Logout</a>"

@app.route('/logout')
def logout():
    session.pop('strava_token', None)
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
        'Authorization': f'Bearer {os.getenv('STRAVA_ACCESS_TOKEN')}'
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
