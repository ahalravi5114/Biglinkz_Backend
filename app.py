from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from db_utils import get_user_id_by_email, create_campaign_in_db, get_db_connection
import os
from datetime import datetime
import pytz
import logging
from psycopg2.extras import DictCursor
from instagrapi import Client  # For fetching Instagram data
import smtplib 

app = Flask(__name__)  # Initialize Flask app

# Enable CORS for all origins and methods
CORS(app)

# Setup logging
logging.basicConfig(level=logging.DEBUG)

@app.route('/login', methods=['POST'])
def login():
    """Endpoint for user login."""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                query = "SELECT user_id, email, password, type, time FROM user_data WHERE email = %s"
                cursor.execute(query, (email,))
                user = cursor.fetchone()

                if user and check_password_hash(user[2], password):
                    # Update last login time
                    update_query = "UPDATE user_data SET time = %s WHERE email = %s"
                    current_time = datetime.now(pytz.utc)
                    cursor.execute(update_query, (current_time, email))
                    conn.commit()

                    return jsonify({
                        "message": "Login successful",
                        "user": {
                            "user_id": user[0],
                            "email": user[1],
                            "type": user[3],
                            "last_login": user[4]
                        }
                    }), 200
                else:
                    return jsonify({"error": "Invalid email or password"}), 401
    except Exception as e:
        logging.error(f"Login error: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/signup', methods=['POST'])
def signup():
    """Endpoint for user signup."""
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

        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters long"}), 400

        hashed_password = generate_password_hash(password)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                current_time = datetime.now(pytz.utc)
                query = """
                    INSERT INTO user_data (email, password, type, time)
                    VALUES (%s, %s, %s, %s)
                    RETURNING user_id, email, type, time
                """
                cursor.execute(query, (email, hashed_password, accounttype, current_time))
                user = cursor.fetchone()
                conn.commit()

                return jsonify({
                    "message": "Signup successful",
                    "user": {
                        "user_id": user[0],
                        "email": user[1],
                        "type": user[2],
                        "last_login": user[3]
                    }
                }), 201
    except Exception as e:
        logging.error(f"Signup error: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@app.route('/create-campaign', methods=['POST'])
def create_campaign():
    """Endpoint for creating a new campaign."""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = [
            'brand_name', 'brand_instagram_id', 'product', 'website', 'email',
            'caption', 'hashtag', 'tags', 'content_type', 'deadline', 'target_followers',
            'influencer_gender', 'influencer_location', 'campaign_title', 'target_reach',
            'budget', 'goal', 'manager_name', 'contact_number', 'rewards',
            'start_date', 'end_date'
        ]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Missing or empty required field: {field}"}), 400

        # Log and validate email
        email = data['email']
        logging.debug(f"Received email: {email}")
        if not email:
            return jsonify({"error": "Email is required"}), 400

        # Fetch user ID from email
        user_id = get_user_id_by_email(email)
        if not user_id:
            return jsonify({"error": "User with the provided email does not exist"}), 404

        # Add user_id to campaign data
        data['user_id'] = user_id
        logging.debug(f"Final data passed to DB: {data}")
        # Create campaign in the database
        create_campaign_in_db(data)

        return jsonify({"message": "Campaign created successfully"}), 201

    except Exception as e:
        logging.error(f"Error creating campaign: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/get-campaigns', methods=['GET'])
def get_campaigns():
    """Endpoint for fetching campaigns created by a user."""
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        # Log the user_id being passed
        logging.debug(f"Fetching campaigns for user_id: {user_id}")

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                query = "SELECT * FROM campaigns WHERE user_id = %s"
                # Log the query and the parameters
                logging.debug(f"Executing query: {query} with user_id: {user_id}")
                cursor.execute(query, (user_id,))
                campaigns = cursor.fetchall()

                # Log the campaigns fetched from the database
                logging.debug(f"Campaigns found: {campaigns}")

                if not campaigns:
                    return jsonify({"campaigns": []}), 200  # Return empty list with 200 OK

                campaign_list = [{
                    "campaign_id": campaign["id"],
                    "brand_name": campaign["brand_name"],
                    "brand_instagram_id": campaign["brand_instagram_id"],
                    "product": campaign["product"],
                    "website": campaign["website"],
                    "email": campaign["email"],
                    "caption": campaign["caption"],
                    "hashtag": campaign["hashtag"],
                    "tags": campaign["tags"],
                    "content_type": campaign["content_type"],
                    "deadline": campaign["deadline"],
                    "target_followers": campaign["target_followers"],
                    "influencer_gender": campaign["influencer_gender"],
                    "influencer_location": campaign["influencer_location"],
                    "campaign_title": campaign["campaign_title"],
                    "target_reach": campaign["target_reach"],
                    "budget": campaign["budget"],
                    "goal": campaign["goal"],
                    "manager_name": campaign["manager_name"],
                    "contact_number": campaign["contact_number"],
                    "rewards": campaign["rewards"],
                    "status": campaign["status"],
                    "start_date": campaign["start_date"],
                    "end_date": campaign["end_date"]
                } for campaign in campaigns]

                return jsonify({"campaigns": campaign_list}), 200

    except Exception as e:
        logging.error(f"Error fetching campaigns: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/profile', methods=['GET', 'POST', 'PUT'])
def profile():
    """Endpoint for managing influencer profile."""
    try:
        if request.method == 'GET':
            # Fetch influencer data by Instagram ID
            insta_id = request.args.get('insta_id')

            if not insta_id:
                return jsonify({"error": "Instagram ID is required"}), 400

            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=DictCursor) as cursor:
                    query = """
                        SELECT email, phone_number, followers FROM influencer_profile WHERE insta_id = %s
                    """
                    cursor.execute(query, (insta_id,))
                    influencer = cursor.fetchone()

                    if not influencer:
                        return jsonify({"error": "Influencer not found"}), 404

                    return jsonify({
                        "email": influencer["email"],
                        "phone_number": influencer["phone_number"],
                        "followers": influencer["followers"]
                    }), 200

        elif request.method == 'POST':
            # Fetch Instagram data and send OTP
            data = request.get_json()
            insta_id = data.get('insta_id')

            if not insta_id:
                return jsonify({"error": "Instagram ID is required"}), 400

            # Fetch Instagram data
            cl = Client()
            try:
                insta_user = cl.user_info_by_username(insta_id)
                email = insta_user.email
                phone_number = insta_user.phone_number
                followers = insta_user.follower_count
            except Exception as e:
                return jsonify({"error": f"Failed to fetch Instagram data: {str(e)}"}), 500

            # Store fetched data in DB
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    insert_query = """
                        INSERT INTO influencer_profile (insta_id, email, phone_number, followers)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (insta_id) DO UPDATE
                        SET email = EXCLUDED.email, phone_number = EXCLUDED.phone_number, followers = EXCLUDED.followers
                    """
                    cursor.execute(insert_query, (insta_id, email, phone_number, followers))
                    conn.commit()


        elif request.method == 'PUT':
            # Verify OTP and update profile
            data = request.get_json()
            email = data.get('email')
            first_name = data.get('first_name')
            last_name = data.get('last_name')
            country = data.get('country')
            state = data.get('state')
            city = data.get('city')
            category = data.get('category')

            # Update profile in DB
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    update_query = """
                        UPDATE influencer_profile
                        SET First_name = %s, Last_name = %s, country = %s, state = %s, city = %s, category = %s
                        WHERE email = %s
                    """
                    cursor.execute(update_query, (first_name, last_name, country, state, city, category, email))
                    conn.commit()

            return jsonify({"message": "Profile updated successfully"}), 200

    except Exception as e:
        logging.error(f"Error handling profile: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
