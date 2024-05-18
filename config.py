import os
SQLALCHEMY_TRACK_MODIFICATIONS = False
STRAVA_CLIENT_ID = os.getenv('99652')
STRAVA_CLIENT_SECRET = os.getenv('2dc10e8d62b4925837aac970b6258fc3eae96c63')
STRAVA_REDIRECT_URI = 'https://plankton-app-fdt3l.ondigitalocean.app/authorize'
