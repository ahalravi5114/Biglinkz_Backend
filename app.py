from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from db_utils import get_user_id_by_email, create_campaign_in_db, get_db_connection
import os
from datetime import datetime

app = Flask(__name__)

# Enable CORS for all origins and methods
CORS(app)

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT user_id, email, password, type, time FROM user_data WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            # Update last login time
            update_query = "UPDATE user_data SET time = %s WHERE email = %s"
            current_time = datetime.now(pytz.utc)
            cursor.execute(update_query, (current_time, email))
            conn.commit()

            cursor.close()
            conn.close()

            return jsonify({
                "message": "Login successful",
                "user": {
                    "user_id": user['user_id'],
                    "email": user['email'],
                    "type": user['type'],
                    "last_login": user['time']
                }
            }), 200
        else:
            cursor.close()
            conn.close()
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirmPassword')
        accounttype = data.get('type')

        if not email or not password or not confirm_password or not accounttype:
            return jsonify({"error": "All fields are required"}), 400

        if password != confirm_password:
            return jsonify({"error": "Password and confirm password do not match"}), 400

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        current_time = datetime.now(pytz.utc)
        query = "INSERT INTO user_data (email, password, type, time) VALUES (%s, %s, %s, %s) RETURNING user_id, email, type, time"
        cursor.execute(query, (email, hashed_password, accounttype, current_time))
        user = cursor.fetchone()

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "Signup successful", "user": user}), 201

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/create-campaign', methods=['POST'])
def create_campaign():
    try:
        data = request.get_json()

        required_fields = [
            'brand_name', 'brand_instagram_id', 'product', 'website', 'email', 
            'caption', 'hashtag', 'tags', 'content_type', 'deadline', 'target_followers',
            'influencer_gender', 'influencer_location', 'campaign_title', 'target_reach',
            'budget', 'goal', 'manager_name', 'contact_number', 'rewards'
        ]

        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"{field} is required"}), 400

        user_id = get_user_id_by_email(data['email'])
        if not user_id:
            return jsonify({"error": "User with the provided email does not exist"}), 404

        data['user_id'] = user_id

        campaign = create_campaign_in_db(data)

        return jsonify({"message": "Campaign created successfully", "campaign": campaign}), 201

    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True)