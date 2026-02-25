import mysql.connector
import os
from dotenv import load_dotenv

# Load the passwords from the .env file (for your local laptop)
load_dotenv()

def get_connection():
    # Use the absolute path to the certificate on Render
    # On Render, your files live in /opt/render/project/src/
    cert_path = os.path.join(os.getcwd(), 'ca.pem')
    
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 10936)),
        # Add the SSL configuration here
        ssl_ca=cert_path,
        ssl_verify_cert=True
    )
    return conn

print("Successfully connected")