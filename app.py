from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(_name_)

# Enable CORS for all origins and methods
CORS(app)

# Get the database URL from environment variables
DB_URL = os.getenv('DATABASE_URL')

# Establishing a connection to Neon DB
def get_db_connection():
    return psycopg2.connect(DB_URL)

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = "SELECT * FROM user_data WHERE email = %s AND password = %s"
        cursor.execute(query, (email, password))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            return jsonify({"message": "Login successful", "user": user}), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

if _name_ == '_main_':
    app.run(debug=True)