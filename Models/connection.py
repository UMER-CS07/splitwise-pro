import mysql.connector
import os

def get_connection():
    # We use ssl_disabled=False to tell Aiven we want a secure line.
    # Note: For the Free Tier, you often don't need the .pem file 
    # IF you set ssl_disabled=False and use the correct port.
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        port=int(os.environ.get("DB_PORT", 10936)),
        ssl_disabled=False,
        connection_timeout=10,
        autocommit=True  # This ensures your 'INSERT' actually saves!
    )