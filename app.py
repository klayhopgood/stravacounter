from flask import Flask, redirect, url_for, session, request, jsonify, render_template
import requests
import mysql.connector
from mysql.connector import errorcode
import os
import datetime  # Importing datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

client_id = os.getenv('STRAVA_CLIENT_ID')
client_secret = os.getenv('STRAVA_CLIENT_SECRET')
redirect_uri = os.getenv('STRAVA_REDIRECT_URI')

db_config = {
    'user': 'doadmin',
    'password': 'AVNS_i5v39MnnGnz0wUvbNOS',
    'host': 'dbaas-db-10916787-do-user-16691845-0.c.db.ondigitalocean.com',
    'port': '25060',
    'database': 'defaultdb',
    'ssl_ca': '/Users/klayhopgood/Downloads/ca-certificate.crt',
    'ssl_disabled': False
}

def save_tokens_to_db(access_token, refresh_token, athlete_id, expires_at):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO strava_tokens (athlete_id, access_token, refresh_token, expires_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE access_token=VALUES(access_token), refresh_token=VALUES(refresh_token), expires_at=VALUES(expires_at)
        """, (athlete_id, access_token, refresh_token, expires_at))
        connection.commit()
    except mysql.connector.Error as err:
        print(err)
    finally:
        cursor.close()
        connection.close()

def get_access_token(athlete_id):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute("""
            SELECT access_token FROM strava_tokens WHERE athlete_id = %s
        """, (athlete_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except mysql.connector.Error as err:
        print(err)
    finally:
        cursor.close()
        connection.close()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    authorize_url = f"https://www.strava.com/oauth/authorize?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}&approval_prompt=force&scope=read,activity:write,activity:read_all"
    return redirect(authorize_url)

@app.route('/authorize')
def login_callback():
    code = request.args.get('code')
    if code:
        token_url = 'https://www.strava.com/oauth/token'
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
        }
        response = requests.post(token_url, data=payload)
        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token')
            expires_at = tokens.get('expires_at')
            athlete_id = str(tokens.get('athlete').get('id'))
            save_tokens_to_db(access_token, refresh_token, athlete_id, expires_at)
            session['athlete_id'] = athlete_id
            session['access_token'] = access_token
            return redirect(url_for('index'))
        else:
            return 'Failed to login. Error: ' + response.text
    else:
        return 'Authorization code not received.'

@app.route('/index')
def index():
    if 'athlete_id' in session:
        return render_template('index.html')
    else:
        return redirect(url_for('home'))

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        verify_token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        if verify_token == os.getenv('STRAVA_VERIFY_TOKEN'):
            return jsonify({'hub.challenge': challenge})
        return 'Invalid verification token', 403
    elif request.method == 'POST':
        event = request.json
        print(f"Received event: {event}")
        if event['object_type'] == 'activity' and event['aspect_type'] == 'create':
            handle_activity_create(event['object_id'], event['owner_id'])
        return 'Event received', 200

def handle_activity_create(activity_id, athlete_id):
    access_token = get_access_token(athlete_id)
    if not access_token:
        print("No access_token found for athlete_id: ", athlete_id)
        return

    headers = {
        'Authorization': f'Bearer {access_token}'
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

    activity_response = requests.get(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers
    )

    if activity_response.status_code != 200:
        print(f"Failed to fetch activity {activity_id}: {activity_response.text}")
        return

    activity = activity_response.json()

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
