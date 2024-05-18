import mysql.connector
from mysql.connector import errorcode

db_config = {
    'user': 'doadmin',
    'password': 'AVNS_i5v39MnnGnz0wUvbNOS',  # Replace with your actual password
    'host': 'dbaas-db-10916787-do-user-16691845-0.c.db.ondigitalocean.com',
    'port': '25060',
    'database': 'defaultdb',
    'ssl_ca': '/Users/klayhopgood/Downloads/ca-certificate.crt',  # Adjust path if needed
    'ssl_disabled': False
}

create_table_query = """
CREATE TABLE strava_tokens (
    id INT AUTO_INCREMENT PRIMARY KEY,
    athlete_id VARCHAR(255) NOT NULL,
    access_token VARCHAR(255) NOT NULL,
    refresh_token VARCHAR(255) NOT NULL,
    expires_at BIGINT NOT NULL
);
"""

try:
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute(create_table_query)
    connection.commit()
    print("Table `strava_tokens` created successfully.")
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
        print("Table already exists.")
    else:
        print(err.msg)
finally:
    cursor.close()
    connection.close()
