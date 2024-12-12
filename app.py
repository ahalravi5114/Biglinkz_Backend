from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from models import create_campaign_in_db, get_user_id_by_email

app = Flask(__name__)

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

        # Query to get the stored hashed password and other user details
        query = "SELECT user_id, email, password, type FROM user_data WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            # If the password matches
            return jsonify({
                "message": "Login successful",
                "user": {
                    "user_id": user['user_id'],
                    "email": user['email'],
                    "type": user['type']
                }
            }), 200
        else:
            # If the email or password is incorrect
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirmPassword')  # Accept confirmPassword from the frontend
        accounttype = data.get('type')

        if not email or not password or not confirm_password or not accounttype:
            return jsonify({"error": "Email, password, confirm password, and account type are required"}), 400

        if password != confirm_password:
            return jsonify({"error": "Password and confirm password do not match"}), 400

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = "INSERT INTO user_data (email, password, type) VALUES (%s, %s, %s) RETURNING user_id, email, type"
        cursor.execute(query, (email, hashed_password, accounttype))
        user = cursor.fetchone()

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Signup successful", "user": user}), 201

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/create-campaign', methods=['POST'])
def create_campaign():
    """Endpoint to create a new campaign."""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = [
            'brand_name', 'brand_instagram_id', 'product', 'website', 'email', 
            'caption', 'hashtag', 'tags', 'content_type', 'deadline', 'target_followers',
            'influencer_gender', 'influencer_location', 'campaign_title', 'target_reach',
            'budget', 'goal', 'manager_name', 'contact_number', 'rewards'
        ]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"{field} is required"}), 400

        # Retrieve user ID by email
        user_id = get_user_id_by_email(data['email'])
        if not user_id:
            return jsonify({"error": "User with the provided email does not exist"}), 404

        # Add user ID to campaign details
        data['user_id'] = user_id

        # Insert campaign into the database
        campaign = create_campaign_in_db(data)

        return jsonify({"message": "Campaign created successfully", "campaign": campaign}), 201

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)