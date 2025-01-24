import mysql.connector
from mysql.connector import Error

def create_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="devops123",
            database="chat1"
        )
        if conn.is_connected():
            print("Connected to MySQL")
        return conn
    except Error as e:
        print(f"Error: {e}")
        return None
