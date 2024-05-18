from flask import Flask, redirect, url_for, session, request, render_template
from stravalib import Client
import mysql.connector
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

app.config['STRAVA_CLIENT_ID'] = os.getenv('STRAVA_CLIENT_ID')
app.config['STRAVA_CLIENT_SECRET'] = os.getenv('STRAVA_CLIENT_SECRET')
app.config['STRAVA_REDIRECT_URI'] = os.getenv('STRAVA_REDIRECT_URI')

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

@app.route('/')
def home():
    c = Client()
    url = c.authorization_url(
        client_id=app.config["STRAVA_CLIENT_ID"],
        redirect_uri=url_for("logged_in", _external=True),
        approval_prompt="auto",
    )
    return render_template("login.html", authorize_url=url)

@app.route('/strava-oauth')
def logged_in():
    error = request.args.get("error")
    if error:
        return render_template("login_error.html", error=error)
    else:
        code = request.args.get("code")
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=app.config["STRAVA_CLIENT_ID"],
            client_secret=app.config["STRAVA_CLIENT_SECRET"],
            code=code,
        )
        access_token = token_response['access_token']
        refresh_token = token_response['refresh_token']
        expires_at = token_response['expires_at']
        strava_athlete = client.get_athlete()

        athlete_id = str(strava_athlete.id)
        save_tokens_to_db(access_token, refresh_token, athlete_id, expires_at)
        session['athlete_id'] = athlete_id
        session['access_token'] = access_token

        return render_template("index.html", athlete=strava_athlete)

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

def get_access_token(athlete_id):
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute("SELECT access_token FROM strava_tokens WHERE athlete_id = %s", (athlete_id,))
        result = cursor.fetchone()
        cursor.close()
        return result[0] if result else None
    except mysql.connector.Error as err:
        print(err)
    finally:
        connection.close()

def handle_activity_create(activity_id, athlete_id):
    access_token = get_access_token(athlete_id)
    if not access_token:
        print(f"No access_token found for athlete_id: {athlete_id}")
        return

    client = Client(access_token=access_token)
    activities = client.get_activities(limit=200)

    days_run, total_days = calculate_days_run_this_year(activities)

    activity = client.get_activity(activity_id)
    new_description = f"{activity.description}\nDays run this year: {days_run}/{total_days}"
    client.update_activity(activity_id, description=new_description)

def calculate_days_run_this_year(activities):
    today = datetime.datetime.today()
    start_of_year = datetime.datetime(today.year, 1, 1)

    run_dates = set()

    for activity in activities:
        if activity.type == 'Run':
            run_date = activity.start_date_local.date()
            if run_date >= start_of_year.date():
                run_dates.add(run_date)

    days_run = len(run_dates)
    total_days = (today - start_of_year).days + 1

    return days_run, total_days

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
