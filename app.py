import datetime
import requests
import mysql.connector
from flask import Flask, request, redirect, session, render_template
import stripe

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Configure your database
db_config = {
    'user': 'doadmin',
    'password': 'AVNS_i5v39MnnGnz0wUvbNOS',  # Replace with your actual password
    'host': 'dbaas-db-10916787-do-user-16691845-0.c.db.ondigitalocean.com',
    'port': '25060',
    'database': 'defaultdb',
    'ssl_ca': '/Users/klayhopgood/Downloads/ca-certificate.crt',  # Adjust path if needed
    'ssl_disabled': False
}

# Stripe configuration
stripe.api_key = 'sk_test_51NODfYJMPCTLT0UxdiGMK4PPOzA6pnVi1NejzSusKTIx3bJvvo7Pht4bGZjHMH5FUwMnbLH3024pXAaSsQrA9twi00qt305QGu'
STRIPE_WEBHOOK_SECRET = 'we_1PIEPSJMPCTLT0Ux2cgjZvQ4'

# Client ID
CLIENT_ID = 'your_client_id'

def get_db_connection():
    return mysql.connector.connect(**db_config)

def is_paid_user(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT is_paid_user FROM strava_tokens WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return False
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
    redirect_uri = 'https://plankton-app-fdt3l.ondigitalocean.app/login/callback'
    authorize_url = f'https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&scope=activity:write,activity:read_all'
    return redirect(authorize_url)

@app.route('/login/callback')
def login_callback():
    code = request.args.get('code')
    token_response = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': CLIENT_ID,
            'client_secret': 'your_client_secret',
            'code': code,
            'grant_type': 'authorization_code'
        }
    ).json()

    access_token = token_response['access_token']
    refresh_token = token_response['refresh_token']
    expires_at = token_response['expires_at']
    athlete = token_response['athlete']
    athlete_id = athlete['id']

    save_tokens_to_db(athlete_id, athlete_id, access_token, refresh_token, expires_at)

    session['athlete_id'] = athlete_id

    return render_template('index.html', is_paid_user=is_paid_user(athlete_id), days_run=True, total_kms=True, avg_kms=True)

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

@app.route('/webhook', methods=['POST'])
def webhook():
    event = request.get_json()
    if event['object_type'] == 'activity' and event['aspect_type'] == 'create':
        handle_activity_create(event['object_id'], event['owner_id'])
    return '', 200

def handle_activity_create(activity_id, owner_id):
    tokens = get_tokens(owner_id)
    if not tokens:
        print(f"No tokens found for owner_id {owner_id}")
        return

    access_token = tokens['access_token']

    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(f'https://www.strava.com/api/v3/activities/{activity_id}', headers=headers)
    activity = response.json()

    activities = get_all_activities(access_token)
    if not activities:
        print(f"No activities found for owner_id {owner_id}")
        return

    preferences = get_user_preferences(owner_id)

    days_run, total_days = calculate_days_run_this_year(activities)
    total_kms_run, avg_kms_per_week = calculate_kms_stats(activities)
    total_elevation, avg_elevation_per_week = calculate_elevation_stats(activities)
    avg_pace, avg_pace_per_week = calculate_pace_stats(activities)
    total_calories = calculate_calories(activities)

    new_description = activity.get('description', '')

    if preferences['days_run']:
        new_description += f"Days run this year: {days_run}/{total_days}\n"
    if preferences['total_kms']:
        new_description += f"Total kms run this year: {total_kms_run:.1f} km\n"
    if preferences['avg_kms']:
        new_description += f"Average kms per week (last 4 weeks): {avg_kms_per_week:.1f} km\n"
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
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z').astimezone().replace(tzinfo=None)
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
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z').astimezone().replace(tzinfo=None)
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
            activity_date = datetime.datetime.strptime(activity['start_date_local'], '%Y-%m-%dT%H:%M:%S%z').astimezone().replace(tzinfo=None)
            if activity_date >= start_of_year:
                total_time += activity['moving_time']
                total_distance += activity['distance']
                if today - datetime.timedelta(weeks=4) <= activity_date <= today:
                    weeks_data_time += activity['moving_time']
                    weeks_data_distance += activity['distance']

    avg_pace = (total_time / 60) / (total_distance / 1000) if total_distance > 0 else 0  # Pace in min/km
    avg_pace_per_week = (weeks_data_time / 60) / (weeks_data_distance / 1000) if weeks_data_distance > 0 else 0  # Pace in min/km

    return round(avg_pace, 1), round(avg_pace_per_week, 1)

def calculate_calories(activities):
    total_calories = 0

    for activity in activities:
        if activity['type'] == 'Run':
            total_calories += activity['calories']

    return total_calories

def get_tokens(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT access_token, refresh_token, expires_at FROM strava_tokens WHERE owner_id = %s", (owner_id,))
        return cursor.fetchone()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_all_activities(access_token):
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get('https://www.strava.com/api/v3/athlete/activities', headers=headers)
    if response.status_code == 200:
        return response.json()
    return []

def get_user_preferences(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM user_preferences WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
        if result:
            return result
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
    if not owner_id:
        return redirect('/')

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
        """, (
            owner_id, preferences['days_run'], preferences['total_kms'], preferences['avg_kms'],
            preferences['total_elevation'], preferences['avg_elevation'], preferences['avg_pace'],
            preferences['avg_pace_per_week'], preferences['beers_burnt'], preferences['pizza_slices_burnt'],
            preferences['remove_promo']
        ))
        connection.commit()
        updated = True
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        updated = False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return render_template('index.html', is_paid_user=is_paid_user(owner_id), **preferences, updated=updated)

@app.route('/create_checkout_session', methods=['POST'])
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Premium Membership',
                    },
                    'unit_amount': 500,
                    'recurring': {
                        'interval': 'month',
                    },
                },
                'quantity': 1,
            }],
            mode='subscription',
            success_url='https://plankton-app-fdt3l.ondigitalocean.app/success',
            cancel_url='https://plankton-app-fdt3l.ondigitalocean.app/cancel',
        )
        return redirect(checkout_session.url)
    except Exception as e:
        return str(e)

@app.route('/success')
def success():
    return 'Subscription successful. You are now a premium user.'

@app.route('/cancel')
def cancel():
    return 'Subscription canceled. You are not a premium user.'

@app.route('/stripe_webhook', methods=['POST'])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return '', 400
    except stripe.error.SignatureVerificationError as e:
        return '', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_id = session['customer']
        # Update the database to mark the user as a paid user
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            cursor.execute("UPDATE strava_tokens SET is_paid_user = TRUE WHERE owner_id = %s", (customer_id,))
            connection.commit()
        except mysql.connector.Error as err:
            print(f"Error: {err.msg}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    return '', 200

@app.route('/cancel_subscription', methods=['POST'])
def cancel_subscription():
    owner_id = session.get('athlete_id')
    if not owner_id:
        return redirect('/')

    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("UPDATE strava_tokens SET is_paid_user = FALSE WHERE owner_id = %s", (owner_id,))
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

    return redirect('/')

@app.route('/contact')
def contact():
    return 'For all inquiries, contact us at klay at simplifiedanalytics dot com dot au'

if __name__ == '__main__':
    app.run(debug=True)
