import json
import os
import stripe
import secrets
import requests
import datetime
import mysql.connector
from flask import Flask, request, redirect, jsonify, render_template, session, url_for
from dateutil import parser
from flask_session import Session

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Stripe configuration
stripe.api_key = 'sk_test_51PJDimAlw5arL9EanWVm9Jg9yF5ZiFgnLx3tzh5Snx2fbW2TduAATIB1Lzmf4gQiYscwGRKZxavu89UVqubbjbqh00dRAB8Kme'
stripe_endpoint_secret = 'whsec_SpYHjmZTR6G7iowQFSHSkXngW4ewqRLr'

# Database configuration
db_config = {
    'user': 'doadmin',
    'password': 'AVNS_i5v39MnnGnz0wUvbNOS',
    'host': 'dbaas-db-10916787-do-user-16691845-0.c.db.ondigitalocean.com',
    'port': '25060',
    'database': 'defaultdb',
    'ssl_ca': '/Users/klayhopgood/Downloads/ca-certificate.crt',
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
    authorize_url = f'https://www.strava.com/oauth/authorize?client_id=99652&redirect_uri={redirect_uri}&response_type=code&scope=activity:write,activity:read_all'
    return redirect(authorize_url)

@app.route('/login/callback')
def login_callback():
    code = request.args.get('code')
    if code:
        token_url = 'https://www.strava.com/oauth/token'
        payload = {
            'client_id': '99652',
            'client_secret': '2dc10e8d62b4925837aac970b6258fc3eae96c63',
            'code': code,
            'grant_type': 'authorization_code',
        }
        response = requests.post(token_url, data=payload)
        if response.status_code == 200:
            tokens = response.json()
            session['access_token'] = tokens.get('access_token')
            session['refresh_token'] = tokens.get('refresh_token')
            session['expires_at'] = tokens.get('expires_at')
            session['athlete_id'] = str(tokens.get('athlete').get('id'))
            save_tokens_to_db(session['athlete_id'], session['access_token'], session['refresh_token'], session['expires_at'])
            preferences = get_user_preferences(session['athlete_id'])
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

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, stripe_endpoint_secret
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Error while verifying webhook signature: {e}")
        return 'Invalid signature', 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        client_reference_id = session.get('client_reference_id')
        if client_reference_id:
            update_paid_status(client_reference_id, True)

    return 'Success', 200

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

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return 'User not authenticated', 403

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{
                'price': 'price_1PJEMaAlw5arL9Eaq14rYBu1',
                'quantity': 1,
            }],
            success_url=url_for('subscription_success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('subscription_cancel', _external=True),
            client_reference_id=athlete_id
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        print(f"Error creating Stripe Checkout session: {e}")
        return str(e), 500

@app.route('/subscription-success')
def subscription_success():
    return "Subscription successful! You are now a paid user."

@app.route('/subscription-cancel')
def subscription_cancel():
    return "Subscription cancelled."

@app.route('/unsubscribe', methods=['POST'])
def unsubscribe():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return 'User not authenticated', 403

    try:
        tokens = get_tokens_from_db(athlete_id)
        if tokens and tokens.get('stripe_customer_id'):
            subscriptions = stripe.Subscription.list(customer=tokens['stripe_customer_id'])
            for sub in subscriptions:
                stripe.Subscription.delete(sub.id)
            update_paid_status(athlete_id, False)
            return redirect('/')
        else:
            return 'No active subscription found.', 400
    except Exception as e:
        print(f"Error during unsubscription: {e}")
        return str(e), 500

@app.route('/update_preferences', methods=['POST'])
def update_preferences():
    athlete_id = session.get('athlete_id')
    if not athlete_id:
        return 'User not authenticated', 403

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
        """, (athlete_id, preferences['days_run'], preferences['total_kms'], preferences['avg_kms'], preferences['total_elevation'], preferences['avg_elevation'], preferences['avg_pace'], preferences['avg_pace_per_week'], preferences['beers_burnt'], preferences['pizza_slices_burnt'], preferences['remove_promo']))
        connection.commit()
        return render_template('index.html', preferences=preferences, updated=True)
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return 'Database error', 500
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
                'remove_promo': result.get('remove_promo', False),
                'is_paid_user': check_if_paid_user(owner_id)
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
                'remove_promo': False,
                'is_paid_user': check_if_paid_user(owner_id)
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
            'remove_promo': False,
            'is_paid_user': False
        }
    finally:
        if connection:
            connection.close()

def check_if_paid_user(owner_id):
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT is_paid_user FROM strava_tokens WHERE owner_id = %s", (owner_id,))
        result = cursor.fetchone()
        cursor.close()
        return result['is_paid_user'] == 1 if result else False
    except mysql.connector.Error as err:
        print(f"Error: {err.msg}")
        return False
    finally:
        if connection:
            connection.close()

@app.route('/subscription-success')
def subscription_success():
    return "Subscription successful! You are now a paid user."

@app.route('/subscription-cancel')
def subscription_cancel():
    return "Subscription cancelled."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
