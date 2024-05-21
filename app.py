import os
import datetime
import requests
from flask import Flask, request, redirect, session, url_for, render_template
import mysql.connector
import stripe

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Load configuration from environment variables or directly set them
CLIENT_ID = '99652'
CLIENT_SECRET = '2dc10e8d62b4925837aac970b6258fc3eae96c63'
STRIPE_SECRET_KEY = 'sk_test_51NODfYJMPCTLT0UxdiGMK4PPOzA6pnVi1NejzSusKTIx3bJvvo7Pht4bGZjHMH5FUwMnbLH3024pXAaSsQrA9twi00qt305QGu'
STRIPE_WEBHOOK_SECRET = 'we_1PIEPSJMPCTLT0Ux2cgjZvQ4'
REDIRECT_URI = 'https://plankton-app-fdt3l.ondigitalocean.app/login/callback'

stripe.api_key = STRIPE_SECRET_KEY

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

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login')
def login():
    redirect_uri = url_for('login_callback', _external=True)
    authorize_url = f'https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&scope=activity:write,activity:read_all'
    return redirect(authorize_url)

@app.route('/login/callback')
def login_callback():
    code = request.args.get('code')
    token_response = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code'
        }
    ).json()
    access_token = token_response['access_token']
    refresh_token = token_response['refresh_token']
    expires_at = token_response['expires_at']
    athlete_id = token_response['athlete']['id']
    owner_id = athlete_id

    save_tokens_to_db(athlete_id, owner_id, access_token, refresh_token, expires_at)

    session['athlete_id'] = athlete_id
    preferences = get_user_preferences(athlete_id)
    return render_template('index.html', is_paid_user=is_paid_user(athlete_id), **preferences)

def is_paid_user(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT is_paid_user FROM strava_tokens WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
        return result and result[0]
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def calculate_kms_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_kms = 0
    weeks_data = []

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'].replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
            if activity_date >= start_of_year:
                total_kms += activity['distance'] / 1000
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
            activity_date = datetime.datetime.strptime(activity['start_date_local'].replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
            if activity_date >= start_of_year:
                total_elevation += activity['total_elevation_gain']
                if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                    weeks_data.append(activity['total_elevation_gain'])

    avg_elevation_per_week = sum(weeks_data) / 4 if weeks_data else 0

    return round(total_elevation, 1), round(avg_elevation_per_week, 1)

def calculate_pace_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_time = 0
    total_distance = 0
    weeks_data_time = 0
    weeks_data_distance = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'].replace('Z', ''), '%Y-%m-%dT%H:%M:%S')
            if activity_date >= start_of_year:
                total_time += activity['moving_time']
                total_distance += activity['distance']
                if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                    weeks_data_time += activity['moving_time']
                    weeks_data_distance += activity['distance']

    avg_pace = (total_time / 60) / (total_distance / 1000) if total_distance > 0 else 0  # Pace in min/km
    avg_pace_per_week = (weeks_data_time / 60) / (weeks_data_distance / 1000) if weeks_data_distance > 0 else 0

    return round(avg_pace, 2), round(avg_pace_per_week, 2)

def calculate_calories(activities):
    total_calories = 0
    for activity in activities:
        if activity['type'] == 'Run':
            total_calories += activity.get('calories', 0)
    return total_calories

def get_tokens(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM strava_tokens WHERE owner_id = %s", (owner_id,))
        return cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_user_preferences(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM user_preferences WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
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
        return {}
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    owner_id = session.get('athlete_id')
    preferences = {
        'days_run': 'days_run' in request.form,
        'total_kms': 'total_kms' in request.form,
        'avg_kms': 'avg_kms' in request.form,
        'total_elevation': 'total_elevation' in request.form,
        'avg_elevation': 'avg_elevation' in request.form,
        'avg_pace': 'avg_pace' in request.form,
        'avg_pace_per_week': 'avg_pace_per_week' in request.form,
        'beers_burnt': 'beers_burnt' in request.form,
        'pizza_slices_burnt': 'pizza_slices_burnt' in request.form,
        'remove_promo': 'remove_promo' in request.form
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
        """, (owner_id, preferences['days_run'], preferences['total_kms'], preferences['avg_kms'], preferences['total_elevation'],
              preferences['avg_elevation'], preferences['avg_pace'], preferences['avg_pace_per_week'], preferences['beers_burnt'],
              preferences['pizza_slices_burnt'], preferences['remove_promo']))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template('index.html', is_paid_user=is_paid_user(owner_id), **preferences, updated=True)

@app.route('/webhook', methods=['POST'])
def webhook():
    event = request.json
    if event and event['object_type'] == 'activity' and event['aspect_type'] == 'create':
        owner_id = event['owner_id']
        activity_id = event['object_id']

        tokens = get_tokens(owner_id)
        if not tokens:
            print(f"No tokens found for owner_id {owner_id}")
            return '', 200

        activities = get_all_activities(tokens['access_token'])
        if not activities:
            return '', 200

        total_kms_run, avg_kms_per_week = calculate_kms_stats(activities)
        total_elevation, avg_elevation_per_week = calculate_elevation_stats(activities)
        avg_pace, avg_pace_per_week = calculate_pace_stats(activities)
        total_calories = calculate_calories(activities)
        beers_burnt = round(total_calories / 43, 1)
        pizza_slices_burnt = round(total_calories / 285, 1)

        preferences = get_user_preferences(owner_id)

        description = ""

        if preferences.get('days_run', True):
            days_run = len({activity['start_date_local'][:10] for activity in activities if activity['type'] == 'Run'})
            description += f"Days run this year: {days_run}\n"
        if preferences.get('total_kms', True):
            description += f"Total kms run this year: {total_kms_run}\n"
        if preferences.get('avg_kms', True):
            description += f"Average kms per week (last 4 weeks): {avg_kms_per_week}\n"
        if preferences.get('total_elevation', False):
            description += f"Total elevation gain this year: {total_elevation}\n"
        if preferences.get('avg_elevation', False):
            description += f"Average elevation gain per week (last 4 weeks): {avg_elevation_per_week}\n"
        if preferences.get('avg_pace', False):
            description += f"Average pace this year: {avg_pace}\n"
        if preferences.get('avg_pace_per_week', False):
            description += f"Average pace per week (last 4 weeks): {avg_pace_per_week}\n"
        if preferences.get('beers_burnt', False):
            description += f"Number of beers burnt: {beers_burnt}\n"
        if preferences.get('pizza_slices_burnt', False):
            description += f"Number of pizza slices burnt: {pizza_slices_burnt}\n"
        if not preferences.get('remove_promo', False):
            description += "Try for free at www.example.com"

        # Update the activity with the description
        update_response = requests.put(
            f'https://www.strava.com/api/v3/activities/{activity_id}',
            headers={'Authorization': f'Bearer {tokens["access_token"]}'},
            data={'description': description}
        )

        print(f"Response Status Code: {update_response.status_code}")

    return '', 200

@app.route('/create_checkout_session', methods=['POST'])
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': 'YOUR_PRICE_ID',
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('payment_success', _external=True),
            cancel_url=url_for('home', _external=True),
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return str(e), 400

@app.route('/payment_success')
def payment_success():
    owner_id = session.get('athlete_id')
    if owner_id:
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE strava_tokens SET is_paid_user = TRUE WHERE owner_id = %s
            """, (owner_id,))
            connection.commit()
        except mysql.connector.Error as err:
            print(f"Error: {err.msg}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    return render_template('index.html', is_paid_user=True, **get_user_preferences(owner_id), updated=True)

@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        print(f"Error while parsing Stripe event: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Error while verifying Stripe signature: {e}")
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get('customer_email')
        # Handle successful payment here

    return '', 200

def get_all_activities(access_token):
    activities = []
    page = 1
    while True:
        response = requests.get(
            f'https://www.strava.com/api/v3/athlete/activities',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'per_page': 200, 'page': page}
        )
        if response.status_code != 200:
            break
        page_activities = response.json()
        if not page_activities:
            break
        activities.extend(page_activities)
        page += 1
    return activities

if __name__ == '__main__':
    app.run()
