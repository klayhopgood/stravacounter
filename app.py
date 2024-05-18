import os
import json
import datetime
from flask import Flask, redirect, url_for, session, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
import requests

app = Flask(__name__)
app.secret_key = 'random_secret_key'  # Replace with your actual secret key
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://klayhopgood:SuperSecretPassword123!@localhost/strava_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class StravaToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.BigInteger, nullable=False)
    access_token = db.Column(db.String(255), nullable=False)
    refresh_token = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

# Configure OAuth
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
        return jsonify({'access_token': session['strava_token']})
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
    user_id = token['athlete']['id']

    # Save token to database
    strava_token = StravaToken(
        user_id=user_id,
        access_token=token['access_token'],
        refresh_token=token['refresh_token'],
        expires_at=token['expires_at']
    )
    db.session.add(strava_token)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if verify_token == 'STRAVA':
            return jsonify({'hub.challenge': challenge})
        return 'Invalid verification token', 403
    elif request.method == 'POST':
        event = request.json
        print(f"Received event: {event}")
        if event['object_type'] == 'activity' and event['aspect_type'] == 'create':
            handle_activity_create(event['object_id'], event['owner_id'])
        return 'Event received', 200

def handle_activity_create(activity_id, user_id):
    # Get the token for the user from the database
    strava_token = StravaToken.query.filter_by(user_id=user_id).order_by(StravaToken.created_at.desc()).first()

    if not strava_token:
        print("No strava_token found for user.")
        return

    headers = {
        'Authorization': f'Bearer {strava_token.access_token}'
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
    db.create_all()
    app.run(host='0.0.0.0', port=8080, debug=True)
