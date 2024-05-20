from flask import Flask, request, redirect, jsonify, render_template, session, url_for
import requests
import mysql.connector
import datetime
from mysql.connector import errorcode
import secrets
import stripe

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generates and sets a random secret key

# Stripe configuration
stripe.api_key = 'sk_test_51NODfYJMPCTLT0UxdiGMK4PPOzA6pnVi1NejzSusKTIx3bJvvo7Pht4bGZjHMH5FUwMnbLH3024pXAaSsQrA9twi00qt305QGu'
STRIPE_PUBLISHABLE_KEY = 'pk_test_51NODfYJMPCTLT0UxGAfs7ubBPVTJ4QRHzqhC44GeS5c7HtBlbsHYxMd26PVGWWSZyJ2TQSJ6PgIFigop2iRMpHF700mKAYDJDL'
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

            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            session['expires_at'] = expires_at
            session['athlete_id'] = athlete_id

            save_tokens_to_db(athlete_id, access_token, refresh_token, expires_at)
            return redirect(url_for('dashboard'))
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
                expires_at = VALUES(expires_at)
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
        cursor.execute("SELECT access_token, refresh_token, expires_at, is_paid_user, days_run, total_kms, avg_kms, total_elevation, avg_elevation, avg_pace_year, avg_pace_4weeks, beers_burnt, pizza_burnt, remove_try_free FROM strava_tokens WHERE owner_id = %s", (owner_id,))
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
    tokens = get_tokens_from_db(owner_id)
    if not tokens:
        print(f"No tokens found for owner_id {owner_id}")
        return

    access_token = tokens['access_token']
    is_paid_user = tokens['is_paid_user']
    days_run = tokens['days_run']
    total_kms = tokens['total_kms']
    avg_kms = tokens['avg_kms']
    total_elevation = tokens.get('total_elevation', False)
    avg_elevation = tokens.get('avg_elevation', False)
    avg_pace_year = tokens.get('avg_pace_year', False)
    avg_pace_4weeks = tokens.get('avg_pace_4weeks', False)
    beers_burnt = tokens.get('beers_burnt', False)
    pizza_burnt = tokens.get('pizza_burnt', False)
    remove_try_free = tokens.get('remove_try_free', False)

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
    days_run_count, total_days = calculate_days_run_this_year(activities)
    total_kms_run, avg_kms_per_week = calculate_kms_stats(activities)
    total_elevation_gain, avg_elevation_per_week = calculate_elevation_stats(activities)
    avg_pace_year_value, avg_pace_4weeks_value = calculate_pace_stats(activities)
    total_calories_burnt, beers_burnt_count, pizza_burnt_count = calculate_calories_burnt(activities)

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
    new_description = activity.get('description', '')

    if days_run:
        new_description += f"\nDays run this year: {days_run_count}/{total_days}"
    if total_kms:
        new_description += f"\nTotal kms run this year: {total_kms_run:.1f} km"
    if avg_kms:
        new_description += f"\nAverage kms per week (last 4 weeks): {avg_kms_per_week:.1f} km"
    if is_paid_user:
        if total_elevation:
            new_description += f"\nTotal elevation gain this year: {total_elevation_gain:.1f} m"
        if avg_elevation:
            new_description += f"\nAverage elevation gain per week (last 4 weeks): {avg_elevation_per_week:.1f} m"
        if avg_pace_year:
            new_description += f"\nAverage pace per km this year: {avg_pace_year_value:.1f} min/km"
        if avg_pace_4weeks:
            new_description += f"\nAverage pace per km per week (last 4 weeks): {avg_pace_4weeks_value:.1f} min/km"
        if beers_burnt:
            new_description += f"\nNumber of beers burnt: {beers_burnt_count}"
        if pizza_burnt:
            new_description += f"\nNumber of pizza slices burnt: {pizza_burnt_count}"
        if remove_try_free and not remove_try_free:
            new_description += "\nTry for free at www.blah.com"

    update_response = requests.put(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers,
        json={'description': new_description.strip()}  # Use JSON data and remove leading/trailing spaces
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

    total_kms_run = 0
    kms_last_4weeks = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            distance_km = activity['distance'] / 1000  # Convert from meters to kilometers
            total_kms_run += distance_km

            if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                kms_last_4weeks += distance_km

    avg_kms_per_week = kms_last_4weeks / 4

    return total_kms_run, avg_kms_per_week

def calculate_elevation_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_elevation_gain = 0
    elevation_last_4weeks = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            elevation_gain = activity['total_elevation_gain']
            total_elevation_gain += elevation_gain

            if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                elevation_last_4weeks += elevation_gain

    avg_elevation_per_week = elevation_last_4weeks / 4

    return total_elevation_gain, avg_elevation_per_week

def calculate_pace_stats(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    total_time_year = 0
    total_distance_year = 0
    total_time_4weeks = 0
    total_distance_4weeks = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            time_seconds = activity['moving_time']
            distance_km = activity['distance'] / 1000  # Convert from meters to kilometers

            if activity_date >= start_of_year:
                total_time_year += time_seconds
                total_distance_year += distance_km

            if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                total_time_4weeks += time_seconds
                total_distance_4weeks += distance_km

    avg_pace_year = (total_time_year / total_distance_year) / 60  # Convert to minutes per km
    avg_pace_4weeks = (total_time_4weeks / total_distance_4weeks) / 60  # Convert to minutes per km

    return avg_pace_year, avg_pace_4weeks

def calculate_calories_burnt(activities):
    total_calories = 0

    for activity in activities:
        if activity['type'] == 'Run':
            calories = activity.get('calories', 0)
            total_calories += calories

    beers_burnt = total_calories // 43
    pizza_slices_burnt = total_calories // 285

    return total_calories, beers_burnt, pizza_slices_burnt

@app.route('/dashboard')
def dashboard():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return redirect(url_for('login'))

    tokens = get_tokens_from_db(athlete_id)
    if not tokens:
        return redirect(url_for('login'))

    return render_template('index.html',
                           is_paid_user=tokens['is_paid_user'],
                           days_run=tokens['days_run'],
                           total_kms=tokens['total_kms'],
                           avg_kms=tokens['avg_kms'],
                           total_elevation=tokens['total_elevation'],
                           avg_elevation=tokens['avg_elevation'],
                           avg_pace_year=tokens['avg_pace_year'],
                           avg_pace_4weeks=tokens['avg_pace_4weeks'],
                           beers_burnt=tokens['beers_burnt'],
                           pizza_burnt=tokens['pizza_burnt'],
                           remove_try_free=tokens['remove_try_free'])

@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return redirect(url_for('login'))

    days_run = 'days_run' in request.form
    total_kms = 'total_kms' in request.form
    avg_kms = 'avg_kms' in request.form
    total_elevation = 'total_elevation' in request.form
    avg_elevation = 'avg_elevation' in request.form
    avg_pace_year = 'avg_pace_year' in request.form
    avg_pace_4weeks = 'avg_pace_4weeks' in request.form
    beers_burnt = 'beers_burnt' in request.form
    pizza_burnt = 'pizza_burnt' in request.form
    remove_try_free = 'remove_try_free' in request.form

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE strava_tokens
            SET days_run = %s, total_kms = %s, avg_kms = %s, total_elevation = %s, avg_elevation = %s, avg_pace_year = %s, avg_pace_4weeks = %s, beers_burnt = %s, pizza_burnt = %s, remove_try_free = %s
            WHERE athlete_id = %s
        """, (days_run, total_kms, avg_kms, total_elevation, avg_elevation, avg_pace_year, avg_pace_4weeks, beers_burnt, pizza_burnt, remove_try_free, athlete_id))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return redirect(url_for('dashboard'))

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': 'YOUR_PRICE_ID',
                'quantity': 1,
            }],
            mode='subscription',
            success_url=url_for('dashboard', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('dashboard', _external=True),
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return str(e)

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return 'Invalid signature', 400

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session(session)

    return '', 200

def handle_checkout_session(session):
    customer_id = session.get('client_reference_id')
    # Update the user to mark as paid
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE strava_tokens
            SET is_paid_user = TRUE
            WHERE athlete_id = %s
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
    app.run(host='0.0.0.0', port=5000, debug=True)
