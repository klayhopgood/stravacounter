from flask import Flask, request, redirect, jsonify, render_template, session
import requests
import mysql.connector
import datetime
from mysql.connector import errorcode
import secrets
import stripe

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generates and sets a random secret key

# Strava credentials
CLIENT_ID = '99652'  # Replace with your Strava client ID
CLIENT_SECRET = '2dc10e8d62b4925837aac970b6258fc3eae96c63'  # Replace with your Strava client secret
VERIFY_TOKEN = 'STRAVA'

# Stripe credentials
stripe.api_key = 'sk_test_51NODfYJMPCTLT0UxdiGMK4PPOzA6pnVi1NejzSusKTIx3bJvvo7Pht4bGZjHMH5FUwMnbLH3024pXAaSsQrA9twi00qt305QGu'
STRIPE_WEBHOOK_SECRET = 'we_1PIEPSJMPCTLT0Ux2cgjZvQ4'

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
    return render_template('login.html')

@app.route('/login')
def login():
    redirect_uri = request.base_url + '/callback'
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
            owner_id = athlete_id

            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            session['expires_at'] = expires_at
            session['athlete_id'] = athlete_id

            save_tokens_to_db(athlete_id, owner_id, access_token, refresh_token, expires_at)
            return render_template('index.html', is_paid_user=is_paid_user(athlete_id), days_run=True, total_kms=True, avg_kms=True)
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

def save_tokens_to_db(athlete_id, owner_id, access_token, refresh_token, expires_at):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO strava_tokens (athlete_id, owner_id, access_token, refresh_token, expires_at, is_paid_user)
            VALUES (%s, %s, %s, %s, %s, FALSE)
            ON DUPLICATE KEY UPDATE
                access_token = VALUES(access_token),
                refresh_token = VALUES(refresh_token),
                expires_at = VALUES(expires_at)
        """, (athlete_id, owner_id, access_token, refresh_token, expires_at))
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

def is_paid_user(athlete_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT is_paid_user FROM strava_tokens WHERE athlete_id = %s", (athlete_id,))
        result = cursor.fetchone()
        cursor.close()
        return result['is_paid_user'] if result else False
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return False
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

    print(f"Response Status Code: {response.status_code}")

    if response.status_code != 200:
        print(f"Failed to fetch activities: {response.text}")
        return

    activities = response.json()
    days_run, total_days = calculate_days_run_this_year(activities)

    total_kms_run, avg_kms_per_week = calculate_kms_stats(activities)
    total_elevation, avg_elevation_per_week = calculate_elevation_stats(activities)
    avg_pace, avg_pace_per_week = calculate_pace_stats(activities)
    total_calories = calculate_calories(activities)

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

    # Update the description
    new_description = activity.get('description', '')
    if preferences['days_run']:
        new_description += f"Days run this year: {days_run}/{total_days}\n"
    if preferences['total_kms']:
        new_description += f"Total kilometers run this year: {total_kms_run:.1f} km\n"
    if preferences['avg_kms']:
        new_description += f"Average kilometers per week (last 4 weeks): {avg_kms_per_week:.1f} km\n"
    if preferences['total_elevation']:
        new_description += f"Total elevation gain this year: {total_elevation:.1f} m\n"
    if preferences['avg_elevation']:
        new_description += f"Average elevation gain per week (last 4 weeks): {avg_elevation_per_week:.1f} m\n"
    if preferences['avg_pace']:
        new_description += f"Average pace this year: {avg_pace:.1f} min/km\n"
    if preferences['avg_pace_per_week']:
        new_description += f"Average pace per week (last 4 weeks): {avg_pace_per_week:.1f} min/km\n"
    if preferences['beers_burnt']:
        new_description += f"Number of beers burnt: {total_calories / 43:.1f}\n"
    if preferences['pizza_slices_burnt']:
        new_description += f"Number of pizza slices burnt: {total_calories / 285:.1f}\n"
    if not is_paid_user(owner_id):
        new_description += "Try for free at www.example.com\n"

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
            run_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z').date()
            if run_date >= start_of_year.date():
                run_dates.add(run_date)
                print(f"Counted Run Date: {run_date}")

    days_run = len(run_dates)
    total_days = (today - start_of_year).days + 1

    return days_run, total_days

def calculate_kms_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_kms = 0
    weeks_data = []

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            if activity_date >= start_of_year:
                total_kms += activity['distance'] / 1000  # Convert meters to kilometers
                if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                    weeks_data.append(activity['distance'] / 1000)

    avg_kms_per_week = sum(weeks_data) / 4 if weeks_data else 0

    return round(total_kms, 1), round(avg_kms_per_week, 1)

def calculate_elevation_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_elevation = 0
    weeks_data = []

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            if activity_date >= start_of_year:
                total_elevation += activity['total_elevation_gain']  # Assume this is in meters
                if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                    weeks_data.append(activity['total_elevation_gain'])

    avg_elevation_per_week = sum(weeks_data) / 4 if weeks_data else 0

    return round(total_elevation, 1), round(avg_elevation_per_week, 1)

def calculate_pace_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_pace = 0
    weeks_data = []
    run_count = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            if activity_date >= start_of_year:
                total_pace += activity['moving_time'] / (activity['distance'] / 1000)  # min/km
                run_count += 1
                if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                    weeks_data.append(activity['moving_time'] / (activity['distance'] / 1000))

    avg_pace = total_pace / run_count if run_count else 0
    avg_pace_per_week = sum(weeks_data) / len(weeks_data) if weeks_data else 0

    return round(avg_pace, 1), round(avg_pace_per_week, 1)

def calculate_calories(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_calories = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            if activity_date >= start_of_year:
                total_calories += activity['calories']

    return total_calories

def get_user_preferences(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT days_run, total_kms, avg_kms, total_elevation, avg_elevation, avg_pace, avg_pace_per_week, beers_burnt, pizza_slices_burnt
            FROM strava_tokens WHERE owner_id = %s
        """, (owner_id,))
        result = cursor.fetchone()
        cursor.close()
        return result if result else {
            'days_run': True,
            'total_kms': True,
            'avg_kms': True,
            'total_elevation': False,
            'avg_elevation': False,
            'avg_pace': False,
            'avg_pace_per_week': False,
            'beers_burnt': False,
            'pizza_slices_burnt': False
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
            'pizza_slices_burnt': False
        }
    finally:
        if connection:
            connection.close()

@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return redirect('/')

    preferences = request.form
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE strava_tokens SET
                days_run = %s,
                total_kms = %s,
                avg_kms = %s,
                total_elevation = %s,
                avg_elevation = %s,
                avg_pace = %s,
                avg_pace_per_week = %s,
                beers_burnt = %s,
                pizza_slices_burnt = %s
            WHERE athlete_id = %s
        """, (
            preferences.get('days_run') == 'on',
            preferences.get('total_kms') == 'on',
            preferences.get('avg_kms') == 'on',
            preferences.get('total_elevation') == 'on',
            preferences.get('avg_elevation') == 'on',
            preferences.get('avg_pace') == 'on',
            preferences.get('avg_pace_per_week') == 'on',
            preferences.get('beers_burnt') == 'on',
            preferences.get('pizza_slices_burnt') == 'on',
            athlete_id
        ))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template('index.html', is_paid_user=is_paid_user(athlete_id), **preferences, updated=True)

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        print(f"Webhook error: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Webhook signature error: {e}")
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session(session)

    return '', 200

def handle_checkout_session(session):
    customer_id = session.get('client_reference_id')
    if customer_id:
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE strava_tokens SET is_paid_user = TRUE WHERE athlete_id = %s
            """, (customer_id,))
            connection.commit()
        except mysql.connector.Error as err:
            print(f"Error: {err.msg}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

if __name__ == '__main__':
    app.run(debug=True)
