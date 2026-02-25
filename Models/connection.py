import mysql.connector
import os
from dotenv import load_dotenv

# Load the passwords from the .env file (for your local laptop)
load_dotenv()

def get_connection():
    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 3306))
    )
    return conn

print("Successfully connected")