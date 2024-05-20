import os
import stripe
import mysql.connector
import datetime
from flask import Flask, request, jsonify, render_template, session, redirect
from mysql.connector import errorcode
import secrets
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generates and sets a random secret key

# Stripe API keys
stripe.api_key = 'sk_test_51NODfYJMPCTLT0UxdiGMK4PPOzA6pnVi1NejzSusKTIx3bJvvo7Pht4bGZjHMH5FUwMnbLH3024pXAaSsQrA9twi00qt305QGu'
endpoint_secret = 'we_1PIEPSJMPCTLT0Ux2cgjZvQ4'

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

            save_tokens_to_db(athlete_id, access_token, refresh_token, expires_at, athlete_id)
            return render_template('index.html', is_paid_user=is_paid_user(athlete_id), days_run=True, total_kms=True, avg_kms=True)
        else:
            return 'Failed to login. Error: ' + response.text
    else:
        return 'Authorization code not received.'

def is_paid_user(athlete_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT is_paid_user FROM strava_tokens WHERE athlete_id = %s", (athlete_id,))
        result = cursor.fetchone()
        cursor.close()
        return result and result[0]
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return False
    finally:
        if connection:
            connection.close()

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Strava Data App Premium Subscription',
                    },
                    'unit_amount': 500,
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url='https://yourdomain.com/success',
            cancel_url='https://yourdomain.com/cancel',
        )
        return redirect(session.url, code=303)
    except Exception as e:
        return str(e)

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_checkout_session(session)

    return '', 200

def handle_checkout_session(session):
    customer_email = session.get('customer_email')
    if customer_email:
        # Update your database to mark the user as a paid user
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("""
                UPDATE strava_tokens
                SET is_paid_user = TRUE
                WHERE athlete_id = (SELECT athlete_id FROM users WHERE email = %s)
            """, (customer_email,))
            connection.commit()
            cursor.close()
        except mysql.connector.Error as err:
            print(f"Error: {err.msg}")
        finally:
            if connection:
                connection.close()

@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return redirect('/')

    days_run = request.form.get('days_run') == 'on'
    total_kms = request.form.get('total_kms') == 'on'
    avg_kms = request.form.get('avg_kms') == 'on'
    total_elevation = request.form.get('total_elevation') == 'on'
    avg_elevation = request.form.get('avg_elevation') == 'on'
    avg_pace = request.form.get('avg_pace') == 'on'
    avg_pace_week = request.form.get('avg_pace_week') == 'on'
    beers_burnt = request.form.get('beers_burnt') == 'on'
    pizza_slices_burnt = request.form.get('pizza_slices_burnt') == 'on'
    remove_ad = request.form.get('remove_ad') == 'on'

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE strava_tokens
            SET days_run = %s, total_kms = %s, avg_kms = %s,
                total_elevation = %s, avg_elevation = %s,
                avg_pace = %s, avg_pace_week = %s,
                beers_burnt = %s, pizza_slices_burnt = %s,
                remove_ad = %s
            WHERE athlete_id = %s
        """, (days_run, total_kms, avg_kms,
              total_elevation, avg_elevation,
              avg_pace, avg_pace_week,
              beers_burnt, pizza_slices_burnt,
              remove_ad, athlete_id))
        connection.commit()
        cursor.close()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if connection:
            connection.close()

    return render_template('index.html', is_paid_user=is_paid_user(athlete_id), days_run=days_run, total_kms=total_kms, avg_kms=avg_kms)

def save_tokens_to_db(athlete_id, access_token, refresh_token, expires_at, owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO strava_tokens (athlete_id, access_token, refresh_token, expires_at, owner_id)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                access_token = VALUES(access_token),
                refresh_token = VALUES(refresh_token),
                expires_at = VALUES(expires_at),
                owner_id = VALUES(owner_id)
        """, (athlete_id, access_token, refresh_token, expires_at, owner_id))
        connection.commit()
        cursor.close()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if connection:
            connection.close()

def get_tokens_from_db(athlete_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT access_token, refresh_token, expires_at FROM strava_tokens WHERE athlete_id = %s", (athlete_id,))
        result = cursor.fetchone()
        cursor.close()
        return result
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return None
    finally:
        if connection:
            connection.close()

def calculate_days_run_this_year(activities):
    today = datetime.datetime.now(datetime.timezone.utc)
    start_of_year = datetime.datetime(today.year, 1, 1, tzinfo=datetime.timezone.utc)

    run_dates = set()

    for activity in activities:
        if activity['type'] == 'Run':
            run_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z').date()
            if run_date >= start_of_year.date():
                run_dates.add(run_date)

    days_run = len(run_dates)
    total_days = (today - start_of_year).days + 1

    return days_run, total_days

def calculate_kms_stats(activities):
    today = datetime.datetime.now(datetime.timezone.utc)
    start_of_year = datetime.datetime(today.year, 1, 1, tzinfo=datetime.timezone.utc)

    total_kms = 0
    kms_last_4_weeks = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            distance = activity.get('distance', 0) / 1000  # Convert meters to kilometers
            if activity_date >= start_of_year:
                total_kms += distance
            if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                kms_last_4_weeks += distance

    avg_kms_per_week = kms_last_4_weeks / 4
    return round(total_kms, 1), round(avg_kms_per_week, 1)

def calculate_elevation_stats(activities):
    today = datetime.datetime.now(datetime.timezone.utc)
    start_of_year = datetime.datetime(today.year, 1, 1, tzinfo=datetime.timezone.utc)

    total_elevation = 0
    elevation_last_4_weeks = 0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z')
            elevation = activity.get('total_elevation_gain', 0)
            if activity_date >= start_of_year:
                total_elevation += elevation
            if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                elevation_last_4_weeks += elevation

    avg_elevation_per_week = elevation_last_4_weeks / 4
    return round(total_elevation, 1), round(avg_elevation_per_week, 1)

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

    # Update the description
    new_description = f"Days run this year: {days_run}/{total_days}\nTotal kms run this year: {total_kms_run}\nAverage kms per week (last 4 weeks): {avg_kms_per_week}\nTotal elevation gain this year: {total_elevation}\nAverage elevation per week (last 4 weeks): {avg_elevation_per_week}"
    update_response = requests.put(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers,
        json={'description': new_description}  # Use JSON data
    )

    if update_response.status_code == 200:
        print(f"Activity {activity_id} updated successfully")
    else:
        print(f"Failed to update activity {activity_id}: {update_response.status_code} {update_response.text}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
