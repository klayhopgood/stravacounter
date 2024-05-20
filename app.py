from flask import Flask, request, redirect, jsonify, render_template, session
import requests
import mysql.connector
import datetime
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
endpoint_secret = 'we_1PIEPSJMPCTLT0Ux2cgjZvQ4'

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
            return redirect('/index')
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
                owner_id = VALUES(owner_id),
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

def get_tokens_from_db(athlete_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT access_token, refresh_token, expires_at, days_run, total_kms, avg_kms, is_paid_user FROM strava_tokens WHERE athlete_id = %s", (athlete_id,))
        result = cursor.fetchone()
        cursor.close()
        return result
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return None
    finally:
        if connection:
            connection.close()

@app.route('/index', methods=['GET', 'POST'])
def index():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return redirect('/login')

    if request.method == 'POST':
        days_run = 'days_run' in request.form
        total_kms = 'total_kms' in request.form
        avg_kms = 'avg_kms' in request.form
        update_user_preferences(athlete_id, days_run, total_kms, avg_kms)

    user_data = get_tokens_from_db(athlete_id)
    return render_template('index.html', user_data=user_data)

def update_user_preferences(athlete_id, days_run, total_kms, avg_kms):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE strava_tokens
            SET days_run = %s, total_kms = %s, avg_kms = %s
            WHERE athlete_id = %s
        """, (days_run, total_kms, avg_kms, athlete_id))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return jsonify({'error': str(e)}), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return jsonify({'error': str(e)}), 400

    # Handle the event
    if event['type'] == 'invoice.payment_succeeded':
        handle_payment_succeeded(event['data']['object'])
    elif event['type'] == 'invoice.payment_failed':
        handle_payment_failed(event['data']['object'])
    elif event['type'] == 'customer.subscription.created':
        handle_subscription_created(event['data']['object'])
    elif event['type'] == 'customer.subscription.updated':
        handle_subscription_updated(event['data']['object'])
    elif event['type'] == 'customer.subscription.deleted':
        handle_subscription_deleted(event['data']['object'])

    return jsonify({'status': 'success'}), 200

def handle_payment_succeeded(invoice):
    # Handle successful payment logic here
    pass

def handle_payment_failed(invoice):
    # Handle failed payment logic here
    pass

def handle_subscription_created(subscription):
    athlete_id = get_athlete_id_from_subscription(subscription)
    update_paid_status(athlete_id, True)

def handle_subscription_updated(subscription):
    athlete_id = get_athlete_id_from_subscription(subscription)
    update_paid_status(athlete_id, subscription['status'] == 'active')

def handle_subscription_deleted(subscription):
    athlete_id = get_athlete_id_from_subscription(subscription)
    update_paid_status(athlete_id, False)

def get_athlete_id_from_subscription(subscription):
    # Implement logic to retrieve athlete_id from subscription metadata or other means
    return subscription['metadata']['athlete_id']

def update_paid_status(athlete_id, is_paid):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            UPDATE strava_tokens
            SET is_paid_user = %s
            WHERE athlete_id = %s
        """, (is_paid, athlete_id))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

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
    today = datetime.datetime.now(datetime.timezone.utc)
    start_of_year = datetime.datetime(today.year, 1, 1, tzinfo=datetime.timezone.utc)
    start_of_4_weeks_ago = today - datetime.timedelta(weeks=4)

    total_kms_run = 0.0
    kms_last_4_weeks = 0.0

    for activity in activities:
        if activity['type'] == 'Run':
            activity_date = datetime.datetime.strptime(activity['start_date'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
            distance_km = activity['distance'] / 1000.0  # Convert meters to kilometers

            if activity_date >= start_of_year:
                total_kms_run += distance_km
            if start_of_4_weeks_ago <= activity_date <= today:
                kms_last_4_weeks += distance_km

    avg_kms_per_week = kms_last_4_weeks / 4.0

    return round(total_kms_run, 1), round(avg_kms_per_week, 1)

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

    # Get the activity to update
    activity_response = requests.get(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers
    )

    if activity_response.status_code != 200:
        print(f"Failed to fetch activity {activity_id}: {activity_response.text}")
        return

    activity = activity_response.json()

    # Construct new description
    new_description = activity.get('description', '')
    if tokens['days_run']:
        new_description += f"\nDays run this year: {days_run}/{total_days}"
    if tokens['total_kms']:
        new_description += f"\nTotal kilometers run this year: {total_kms_run}"
    if tokens['avg_kms']:
        new_description += f"\nAverage kilometers per week (last 4 weeks): {avg_kms_per_week}"

    # Update the description
    update_response = requests.put(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers,
        json={'description': new_description.strip()}  # Use JSON data
    )

    if update_response.status_code == 200:
        print(f"Activity {activity_id} updated successfully")
    else:
        print(f"Failed to update activity {activity_id}: {update_response.status_code} {update_response.text}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
