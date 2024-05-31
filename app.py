from flask import Flask, request, redirect, jsonify, render_template, session, url_for
import requests
import mysql.connector
import datetime
from mysql.connector import errorcode
import secrets
from dateutil import parser
from flask_session import Session

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generates and sets a random secret key
app.config['SESSION_TYPE'] = 'filesystem'  # Store sessions in the file system (or choose another type)
Session(app)

# Strava credentials
CLIENT_ID = '99652'  # Replace with your Strava client ID
CLIENT_SECRET = '2dc10e8d62b4925837aac970b6258fc3eae96c63'  # Replace with your Strava client secret
VERIFY_TOKEN = 'STRAVA'

# Database configuration
db_config = {
    'user': 'doadmin',
    'password': 'AVNS_i5v39MnnGnz0wUvbNOS',  # Replace with your actual password
    'host': 'dbaas-db-10916787-do-user-16691845-0.c.db.ondigitalocean.com',
    'port': '25060',
    'database': 'defaultdb',
    'ssl_ca': '/Users/klayhopgood/Downloads/ca-certificate.crt',  # Adjust path if needed
    'ssl_disabled': False
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/')
def home():
    return render_template('signup.html')

@app.route('/login')
def login():
    redirect_uri = url_for('login_callback', _external=True)
    authorize_url = f'https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&scope=activity:write,activity:read_all'
    return redirect(authorize_url)

@app.route('/login/callback')
def login_callback():
    code = request.args.get('code')
    if code:
        token_url = 'https://www.strava.com/oauth/token'
        payload = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
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

            # Debugging print statements
            print(f"Access Token: {access_token}")
            print(f"Refresh Token: {refresh_token}")
            print(f"Expires At: {expires_at}")
            print(f"Athlete ID: {athlete_id}")

            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            session['expires_at'] = expires_at
            session['athlete_id'] = athlete_id
            print(f"Set session athlete_id: {session.get('athlete_id')}")
            print(f"Session data after login: {dict(session)}")  # Log entire session data

            save_tokens_to_db(athlete_id, access_token, refresh_token, expires_at)

            preferences = get_user_preferences(athlete_id)
            return render_template('index.html', preferences=preferences)
        else:
            return 'Failed to login. Error: ' + response.text
    else:
        return 'Authorization code not received.'

@app.route('/deauthorize')
def deauthorize():
    access_token = session.get('access_token')
    if access_token:
        deauthorize_url = 'https://www.strava.com/oauth/deauthorize'
        response = requests.post(deauthorize_url, data={'access_token': access_token})
        if response.status_code == 200:
            session.pop('access_token', None)
            session.pop('refresh_token', None)
            session.pop('expires_at', None)
            session.pop('athlete_id', None)
            return redirect('/')
        else:
            return 'Failed to deauthorize. Error: ' + response.text
    else:
        return redirect('/')

def save_tokens_to_db(athlete_id, access_token, refresh_token, expires_at):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO strava_tokens (athlete_id, owner_id, access_token, refresh_token, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                access_token = VALUES(access_token),
                refresh_token = VALUES(refresh_token),
                expires_at = VALUES(expires_at),
                owner_id = VALUES(owner_id)
        """, (athlete_id, athlete_id, access_token, refresh_token, expires_at))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_tokens_from_db(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT access_token, refresh_token, expires_at FROM strava_tokens WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
        cursor.close()
        return result
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return None
    finally:
        if connection:
            connection.close()

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
            handle_activity_create(event['object_id'], event['owner_id'])
        return 'Event received', 200

def handle_activity_create(activity_id, owner_id):
    if not owner_id:
        print("No owner_id in the request")
        return

    tokens = get_tokens_from_db(owner_id)
    if not tokens:
        print(f"No tokens found for owner_id {owner_id}")
        return

    access_token = tokens['access_token']
    headers = {
        'Authorization': f'Bearer {access_token}'
    }

    response = requests.get(
        'https://www.strava.com/api/v3/athlete/activities',
        headers=headers,
        params={'per_page': 200}
    )

    if response.status_code != 200:
        print(f"Failed to fetch activities: {response.text}")
        return

    activities = response.json()
    days_run, total_days = calculate_days_run_this_year(activities)
    total_kms_run, avg_kms_per_week = calculate_kms_stats(activities)
    total_elevation, avg_elevation_per_week = calculate_elevation_stats(activities)

    # Get the activity to update
    activity_response = requests.get(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers
    )

    if activity_response.status_code != 200:
        print(f"Failed to fetch activity {activity_id}: {activity_response.text}")
        return

    activity = activity_response.json()

    # Fetch user preferences
    preferences = get_user_preferences(owner_id)

    # Calculate calories burnt for this activity
    total_calories_burnt = activity.get('calories', 0)
    beers_burnt = total_calories_burnt / 140
    pizza_slices_burnt = total_calories_burnt / 285

    # Build the new description based on preferences
    new_description = ""
    if preferences.get('days_run', True):
        new_description += f"🌍 Days run this year: {days_run}/{total_days}\n"
    if preferences.get('total_kms', True):
        new_description += f"🏃 Total kms run this year: {total_kms_run:.1f} km\n"
    if preferences.get('avg_kms', True):
        new_description += f"🏃 Average kms per week (last 4 weeks): {avg_kms_per_week:.1f} km\n"
    if preferences.get('total_elevation', False):
        new_description += f"⛰️ Total elevation gain this year: {total_elevation:.1f} m\n"
    if preferences.get('avg_elevation', False):
        new_description += f"⛰️ Average elevation per week (last 4 weeks): {avg_elevation_per_week:.1f} m\n"
    if preferences.get('beers_burnt', False):
        new_description += f"🍺 Beers burnt: {beers_burnt:.1f}\n"
    if preferences.get('pizza_slices_burnt', False):
        new_description += f"🍕 Pizza slices burnt: {pizza_slices_burnt:.1f}\n"
    if not preferences.get('remove_promo', False):
        new_description += "Try for free at www.blah.com"

    update_response = requests.put(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers,
        json={'description': new_description}  # Use JSON data
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
            run_date = parser.parse(activity['start_date_local']).date()
            if run_date >= start_of_year.date():
                run_dates.add(run_date)

    days_run = len(run_dates)
    total_days = (today - start_of_year).days + 1

    return days_run, total_days

def calculate_kms_stats(activities):
    today = datetime.datetime.today()
    start_of_4_weeks_ago = today - datetime.timedelta(weeks=4)

    total_kms_run = 0.0
    kms_last_4_weeks = 0.0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = parser.parse(activity['start_date_local']).date()
            if activity_date >= start_of_4_weeks_ago.date():
                kms_last_4_weeks += activity['distance'] / 1000
            if activity_date >= datetime.datetime(today.year, 1, 1).date():
                total_kms_run += activity['distance'] / 1000

    avg_kms_per_week = kms_last_4_weeks / 4

    return round(total_kms_run, 1), round(avg_kms_per_week, 1)

def calculate_elevation_stats(activities):
    today = datetime.datetime.today()
    start_of_4_weeks_ago = today - datetime.timedelta(weeks=4)

    total_elevation = 0.0
    elevation_last_4_weeks = 0.0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = parser.parse(activity['start_date_local']).date()
            if activity_date >= start_of_4_weeks_ago.date():
                elevation_last_4_weeks += activity['total_elevation_gain']
            if activity_date >= datetime.datetime(today.year, 1, 1).date():
                total_elevation += activity['total_elevation_gain']

    avg_elevation_per_week = elevation_last_4_weeks / 4

    return round(total_elevation, 1), round(avg_elevation_per_week, 1)

def get_user_preferences(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM user_preferences WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
        cursor.close()
        if result:
            return {
                'days_run': result.get('days_run', True),
                'total_kms': result.get('total_kms', True),
                'avg_kms': result.get('avg_kms', True),
                'total_elevation': result.get('total_elevation', False),
                'avg_elevation': result.get('avg_elevation', False),
                'avg_pace': result.get('avg_pace', False),
                'avg_pace_per_week': result.get('avg_pace_per_week', False),
                'beers_burnt': result.get('beers_burnt', False),
                'pizza_slices_burnt': result.get('pizza_slices_burnt', False),
                'remove_promo': result.get('remove_promo', False)
            }
        else:
            return {
                'days_run': True,
                'total_kms': True,
                'avg_kms': True,
                'total_elevation': False,
                'avg_elevation': False,
                'avg_pace': False,
                'avg_pace_per_week': False,
                'beers_burnt': False,
                'pizza_slices_burnt': False,
                'remove_promo': False
            }
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return {
            'days_run': True,
            'total_kms': True,
            'avg_kms': True,
            'total_elevation': False,
            'avg_elevation': False,
            'avg_pace': False,
            'avg_pace_per_week': False,
            'beers_burnt': False,
            'pizza_slices_burnt': False,
            'remove_promo': False
        }
    finally:
        if connection:
            connection.close()


@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    print(f"Session data before updating preferences: {dict(session)}")  # Log session data
    owner_id = session.get('athlete_id')
    if not owner_id:
        access_token = session.get('access_token')
        if not access_token:
            return 'User not authenticated', 403

        tokens = get_tokens_from_db_by_access_token(access_token)
        if tokens:
            owner_id = tokens['athlete_id']
        else:
            return 'User not authenticated', 403

    preferences = {
        'days_run': 1 if 'days_run' in request.form else 0,
        'total_kms': 1 if 'total_kms' in request.form else 0,
        'avg_kms': 1 if 'avg_kms' in request.form else 0,
        'total_elevation': 1 if 'total_elevation' in request.form else 0,
        'avg_elevation': 1 if 'avg_elevation' in request.form else 0,
        'avg_pace': 1 if 'avg_pace' in request.form else 0,
        'avg_pace_per_week': 1 if 'avg_pace_per_week' in request.form else 0,
        'beers_burnt': 1 if 'beers_burnt' in request.form else 0,
        'pizza_slices_burnt': 1 if 'pizza_slices_burnt' in request.form else 0,
        'remove_promo': 1 if 'remove_promo' in request.form else 0
    }

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO user_preferences (owner_id, days_run, total_kms, avg_kms, total_elevation, avg_elevation, avg_pace, avg_pace_per_week, beers_burnt, pizza_slices_burnt, remove_promo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                days_run = VALUES(days_run),
                total_kms = VALUES(total_kms),
                avg_kms = VALUES(avg_kms),
                total_elevation = VALUES(total_elevation),
                avg_elevation = VALUES(avg_elevation),
                avg_pace = VALUES(avg_pace),
                avg_pace_per_week = VALUES(avg_pace_per_week),
                beers_burnt = VALUES(beers_burnt),
                pizza_slices_burnt = VALUES(pizza_slices_burnt),
                remove_promo = VALUES(remove_promo)
        """, (owner_id, preferences['days_run'], preferences['total_kms'], preferences['avg_kms'], preferences['total_elevation'], preferences['avg_elevation'], preferences['avg_pace'], preferences['avg_pace_per_week'], preferences['beers_burnt'], preferences['pizza_slices_burnt'], preferences['remove_promo']))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template('index.html', preferences=preferences, updated=True)

@app.route('/session_debug')
def session_debug():
    return jsonify(dict(session))

def get_tokens_from_db_by_access_token(access_token):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT athlete_id, access_token, refresh_token, expires_at FROM strava_tokens WHERE access_token = %s", (access_token,))
        result = cursor.fetchone()
        cursor.close()
        return result
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return None
    finally:
        if connection:
            connection.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
