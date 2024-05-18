from flask import Flask, redirect, url_for, session, request, jsonify, render_template
import requests
import os
import mysql.connector
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')

client_id = os.getenv('STRAVA_CLIENT_ID')
client_secret = os.getenv('STRAVA_CLIENT_SECRET')
redirect_uri = os.getenv('STRAVA_REDIRECT_URI')

db_config = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'database': os.getenv('DB_NAME'),
    'ssl_ca': os.getenv('DB_SSL_CA')
}

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/login')
def login():
    authorize_url = f'https://www.strava.com/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=activity:write,activity:read_all'
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
            athlete_id = str(tokens.get('athlete').get('id'))
            session['access_token'] = access_token
            session['refresh_token'] = refresh_token
            session['athlete_id'] = athlete_id
            save_tokens_to_db(access_token, refresh_token, athlete_id)
            return render_template('index.html')
        else:
            return 'Failed to login. Error: ' + response.text
    else:
        return 'Authorization code not received.'

def save_tokens_to_db(access_token, refresh_token, athlete_id):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO strava_tokens (athlete_id, access_token, refresh_token, expires_at) VALUES (%s, %s, %s, %s)",
            (athlete_id, access_token, refresh_token, tokens['expires_at'])
        )
        connection.commit()
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

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
            handle_activity_create(event['object_id'])
        return 'Event received', 200

def handle_activity_create(activity_id):
    access_token = session.get('access_token')
    if not access_token:
        print("No access_token in session.")
        return

    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(
        f'https://www.strava.com/api/v3/activities/{activity_id}',
        headers=headers
    )

    if response.status_code != 200:
        print(f"Failed to fetch activity {activity_id}: {response.text}")
        return

    activity = response.json()
    # Assuming calculate_days_run_this_year and update_activity_description are defined
    days_run, total_days = calculate_days_run_this_year(activity)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
