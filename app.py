from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from db_utils import get_user_id_by_email, create_campaign_in_db, get_db_connection, update_campaign_status, schedule_campaign_status_update
import os
from datetime import datetime, timedelta
import pytz
import logging
from psycopg2.extras import DictCursor
from instagrapi import Client  
import smtplib 
from flask_mail import Mail
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)  
CORS(app)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  
app.config['MAIL_PASSWORD'] = 'your-email-password'  

mail = Mail(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


UPLOAD_FOLDER = './uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
    """Endpoint for creating a new campaign with file uploads."""
    try:
        # Use form data for both text and file fields
        data = request.form.to_dict()
        files = request.files

        # Validate required fields, including files
        required_fields = [
            'brand_name', 'brand_instagram_id', 'product', 'website', 'email',
            'caption', 'hashtag', 'tags', 'content_type', 'target_followers',
            'influencer_gender', 'influencer_location', 'campaign_title', 'target_reach',
            'budget', 'goal', 'manager_name', 'contact_number', 'rewards',
            'start_date', 'end_date', 'brand_logo', 'campaign_assets','description'
        ]

        for field in required_fields:
            if field not in data or not data[field]:
                if field in ['brand_logo', 'campaign_assets']:  # Check files for these fields
                    if field == 'brand_logo' and 'brand_logo' not in files:
                        return jsonify({"error": f"Missing or empty required field: {field}"}), 400
                    if field == 'campaign_assets' and len(files.getlist('campaign_assets')) == 0:
                        return jsonify({"error": f"Missing or empty required field: {field}"}), 400
                else:
                    return jsonify({"error": f"Missing or empty required field: {field}"}), 400

        # Validate email
        email = data['email']
        user_id = get_user_id_by_email(email)
        if not user_id:
            return jsonify({"error": "User with the provided email does not exist"}), 404

        # Add user_id to campaign data
        data['user_id'] = user_id

        # Handle brand logo upload
        brand_logo = files.get('brand_logo')
        logo_filename = secure_filename(brand_logo.filename)
        logo_path = os.path.join(app.config['UPLOAD_FOLDER'], logo_filename)
        brand_logo.save(logo_path)
        data['brand_logo'] = logo_path  # Store the file path in the campaign data

        start_date_str = data['start_date']
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            deadline = start_date - timedelta(days=20)
            data['deadline'] = deadline.strftime('%Y-%m-%d')
        except ValueError as ve:
            return jsonify({"error": "Invalid date format for start_date. Expected format: YYYY-MM-DD"}), 400

        # Handle campaign assets upload (multiple files)
        asset_files = files.getlist('campaign_assets')  # Allow multiple files for assets
        asset_paths = []
        for asset in asset_files:
            asset_filename = secure_filename(asset.filename)
            asset_path = os.path.join(app.config['UPLOAD_FOLDER'], asset_filename)
            asset.save(asset_path)
            asset_paths.append(asset_path)
        data['campaign_assets'] = ','.join(asset_paths)  # Store asset paths as a comma-separated string

        # Insert campaign into the database
        create_campaign_in_db(data)

        return jsonify({"message": "Campaign created successfully"}), 201

    except Exception as e:
        logging.error(f"Error creating campaign: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/get-campaigns', methods=['GET'])
def get_campaigns():
    """Endpoint for fetching campaigns created by a user, including brand logo and campaign assets."""
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

                campaign_list = []
                for campaign in campaigns:
                    # Extract paths to brand logo and assets
                    brand_logo_path = campaign.get("brand_logo", "")
                    campaign_assets = campaign.get("campaign_assets", "").split(',') if campaign.get("campaign_assets") else []

                    campaign_list.append({
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
                        "end_date": campaign["end_date"],
                        "brand_logo": brand_logo_path,  # Add brand logo path
                        "campaign_assets": campaign_assets,
                        "description": campaign["description"],# Add campaign assets paths
                        "deadline": campaign["deadline"]
                    })

                return jsonify({"campaigns": campaign_list}), 200

    except Exception as e:
        logging.error(f"Error fetching campaigns: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/getprofile', methods=['POST'])
def profile():
    """
    Endpoint to add or update influencer profile details.
    Expects profile details in JSON payload along with user_id.
    """
    try:
        data = request.get_json()

        required_fields = [
            "user_id", "first_name", "last_name", "insta_id", "email", "phone_number",
            "followers", "country", "state", "city", "category"
        ]

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                insert_query = """
                    INSERT INTO influencer_profile (
                        user_id, first_name, last_name, insta_id, email, phone_number, followers,
                        country, state, city, category
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (insta_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        email = EXCLUDED.email,
                        phone_number = EXCLUDED.phone_number,
                        followers = EXCLUDED.followers,
                        country = EXCLUDED.country,
                        state = EXCLUDED.state,
                        city = EXCLUDED.city,
                        category = EXCLUDED.category
                """
                cursor.execute(insert_query, (
                    data["user_id"], data["first_name"], data["last_name"], data["insta_id"],
                    data["email"], data["phone_number"], data["followers"],
                    data["country"], data["state"], data["city"],
                    data["category"]
                ))
                conn.commit()

        return jsonify({"message": "Profile added/updated successfully"}), 200
    except Exception as e:
        logging.error(f"Error handling profile: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/profile/<user_id>', methods=['GET'])
def get_profile(user_id):
    """
    Endpoint to get influencer profile details based on user_id.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Query to fetch the profile details for the given user_id
                select_query = """
                    SELECT first_name, last_name, insta_id, email, phone_number, followers,
                           country, state, city, category
                    FROM influencer_profile
                    WHERE user_id = %s
                """
                cursor.execute(select_query, (user_id,))
                profile = cursor.fetchone()

                if profile:
                    # Prepare response with the profile data
                    profile_data = {
                        "first_name": profile[0],
                        "last_name": profile[1],
                        "insta_id": profile[2],
                        "email": profile[3],
                        "phone_number": profile[4],
                        "followers": profile[5],
                        "country": profile[6],
                        "state": profile[7],
                        "city": profile[8],
                        "category": profile[9],
                    }
                    return jsonify(profile_data), 200
                else:
                    return jsonify({"error": "Profile not found"}), 404

    except Exception as e:
        logging.error(f"Error fetching profile for user_id {user_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

from psycopg2.extras import DictCursor

@app.route('/eligible-campaigns', methods=['GET'])
def get_eligible_campaigns():
    """
    Endpoint for influencers to see campaigns they are eligible for.
    Compares influencer's followers count with target_followers of campaigns.
    Fetches influencer data using user_id.
    """
    try:
        # Get the user_id from the query parameters
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        # Fetch influencer's insta_id and followers count from the database based on user_id
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:  # Use DictCursor here
                influencer_query = """
                    SELECT insta_id, followers
                    FROM influencer_profile
                    WHERE user_id = %s
                """
                cursor.execute(influencer_query, (user_id,))
                influencer = cursor.fetchone()

                if not influencer:
                    return jsonify({"error": "Influencer profile not found"}), 404

                insta_id = influencer["insta_id"]  # Access as a dictionary
                influencer_followers = influencer["followers"]

                # Fetch campaigns where the influencer meets the target followers criteria
                campaign_query = """
                    SELECT *
                    FROM campaigns
                    WHERE target_followers <= %s
                """
                cursor.execute(campaign_query, (influencer_followers,))
                campaigns = cursor.fetchall()

                # Return the eligible campaigns
                if not campaigns:
                    return jsonify({"message": "No eligible campaigns found"}), 200

                eligible_campaigns = [
                    {
                        "campaign_id": campaign["id"],  # Access as a dictionary
                        "brand_name": campaign["brand_name"],
                        "brand_instagram_id": campaign["brand_instagram_id"],
                        "product": campaign["product"],
                        "website": campaign["website"],
                        "email": campaign["email"],
                        "caption": campaign["caption"],
                        "hashtag": campaign["hashtag"],
                        "tags": campaign["tags"],
                        "content_type": campaign["content_type"],
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
                        "end_date": campaign["end_date"],
                        "description": campaign["description"],
                        "deadline": campaign["deadline"]
                    }
                    for campaign in campaigns
                ]

                return jsonify({"eligible_campaigns": eligible_campaigns}), 200

    except Exception as e:
        logging.error(f"Error fetching eligible campaigns: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/campaign/respond', methods=['POST'])
def respond_to_campaign():
    """Endpoint for influencers to accept/reject a campaign or submit the submission URL."""
    try:
        data = request.get_json()  # Get JSON data from the request
        
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Case 1: Accept/Reject Campaign
        if "influencer_status" in data:
            influencer_id = str(data.get('influencer_id'))  # Ensure it's a string if it's VARCHAR in DB
            campaign_id = str(data.get('campaign_id'))  # Ensure it's a string if it's VARCHAR in DB
            influencer_status = data.get('influencer_status')
            deadline = data.get('deadline')

            # Validate required fields for accept/reject
            if not influencer_id or not campaign_id or not influencer_status or not deadline:
                return jsonify({"error": "All fields (influencer_id, campaign_id, influencer_status, deadline) are required"}), 400

            if influencer_status not in ["accepted", "rejected"]:
                return jsonify({"error": "Invalid status value. Use 'accepted' or 'rejected'"}), 400

            # Fetch campaign title and user_id from campaigns table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query_campaign = "SELECT campaign_title, user_id FROM campaigns WHERE id = %s"
                    cursor.execute(query_campaign, (campaign_id,))
                    campaign = cursor.fetchone()

                    if not campaign:
                        return jsonify({"error": "Campaign not found"}), 404

                    campaign_title, user_id = campaign

            # Fetch influencer's name from influencer_profile table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query_influencer = "SELECT first_name, last_name FROM influencer_profile WHERE user_id = %s"
                    cursor.execute(query_influencer, (influencer_id,))
                    influencer = cursor.fetchone()

                    if not influencer:
                        return jsonify({"error": "Influencer not found"}), 404

                    influencer_name = f"{influencer[0]} {influencer[1]}"

            # Construct content based on the influencer's action
            content = f"{campaign_title} has been {influencer_status} by {influencer_name}"

            # Insert or update the influencer campaign record
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query = """
                    INSERT INTO influencer_campaign (influencer_id, campaign_id, influencer_status, deadline, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (influencer_id, campaign_id) DO UPDATE 
                    SET influencer_status = EXCLUDED.influencer_status,
                        deadline = EXCLUDED.deadline,
                        updated_at = EXCLUDED.updated_at
                    """
                    updated_at = datetime.utcnow()  # UTC timestamp
                    cursor.execute(query, (influencer_id, campaign_id, influencer_status, deadline, updated_at))
                    conn.commit()

            # Insert notification record in the notifications table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query_notification = """
                    INSERT INTO notifications (user_id, campaign_id, content, created_at)
                    VALUES (%s, %s, %s, %s)
                    """
                    created_at = datetime.utcnow()  # Current timestamp for notification
                    cursor.execute(query_notification, (user_id, campaign_id, content, created_at))
                    conn.commit()

            return jsonify({
                "message": "Campaign response recorded successfully",
                "details": {
                    "influencer_id": influencer_id,
                    "campaign_id": campaign_id,
                    "influencer_status": influencer_status,
                    "content": content,
                    "updated_at": updated_at
                }
            }), 201

        # Case 2: Update Submission URL
        elif "submission_url" in data:
            influencer_id = str(data.get('influencer_id'))  # Ensure it's a string if it's VARCHAR in DB
            campaign_id = str(data.get('campaign_id'))  # Ensure it's a string if it's VARCHAR in DB
            submission_url = data.get('submission_url')

            # Validate required fields for submission URL update
            if not influencer_id or not campaign_id or not submission_url:
                return jsonify({"error": "Fields (influencer_id, campaign_id, submission_url) are required for URL update"}), 400

            # Fetch campaign title and user_id from campaigns table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query_campaign = "SELECT campaign_title, user_id FROM campaigns WHERE id = %s"
                    cursor.execute(query_campaign, (campaign_id,))
                    campaign = cursor.fetchone()

                    if not campaign:
                        return jsonify({"error": "Campaign not found"}), 404

                    campaign_title, user_id = campaign

            # Fetch influencer's name from influencer_profile table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query_influencer = "SELECT first_name, last_name FROM influencer_profile WHERE user_id = %s"
                    cursor.execute(query_influencer, (influencer_id,))
                    influencer = cursor.fetchone()

                    if not influencer:
                        return jsonify({"error": "Influencer not found"}), 404

                    influencer_name = f"{influencer[0]} {influencer[1]}"

            # Construct content based on submission URL
            content = f"{influencer_name} has submitted the URL for {campaign_title}"

            # Update the submission URL in the influencer_campaign table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query = """
                    UPDATE influencer_campaign
                    SET submission_url = %s, updated_at = %s
                    WHERE influencer_id = %s AND campaign_id = %s
                    """
                    updated_at = datetime.utcnow()  # UTC timestamp
                    cursor.execute(query, (submission_url, updated_at, influencer_id, campaign_id))
                    conn.commit()

            # Insert notification record in the notifications table
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    query_notification = """
                    INSERT INTO notifications (user_id, campaign_id, content, created_at)
                    VALUES (%s, %s, %s, %s)
                    """
                    created_at = datetime.utcnow()  # Current timestamp for notification
                    cursor.execute(query_notification, (user_id, campaign_id, content, created_at))
                    conn.commit()

            return jsonify({
                "message": "Submission URL updated successfully",
                "details": {
                    "influencer_id": influencer_id,
                    "campaign_id": campaign_id,
                    "submission_url": submission_url,
                    "content": content,
                    "updated_at": updated_at
                }
            }), 200

        else:
            return jsonify({"error": "Invalid request. Provide either influencer_status or submission_url"}), 400

    except Exception as e:
        logging.error(f"Error processing campaign response: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/active-campaigns', methods=['GET']) 
def active_campaigns():
    """Endpoint for fetching active campaigns for an influencer based on influencer_status = 'accepted'."""
    try:
        influencer_id = request.args.get('user_id')
        if not influencer_id:
            return jsonify({"error": "User ID is required"}), 400

        # Log the user_id being passed
        logging.debug(f"Fetching active campaigns for influencer user_id: {influencer_id}")

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                # Step 1: Fetch all influencer campaign details where influencer_status is 'accepted'
                query_influencer_campaigns = """
                    SELECT influencer_id, campaign_id, influencer_status, campaign_status, submission_url
                    FROM influencer_campaign 
                    WHERE influencer_id = %s AND influencer_status = 'accepted'
                """
                
                # Log the query for influencer campaigns
                logging.debug(f"Executing query: {query_influencer_campaigns} with user_id: {influencer_id}")
                cursor.execute(query_influencer_campaigns, (influencer_id,))
                influencer_campaigns = cursor.fetchall()

                # If no campaigns are found for the influencer, return an empty list
                if not influencer_campaigns:
                    return jsonify({"influencer_campaigns": []}), 200

                # Step 2: Fetch campaign details for the campaign_ids obtained from the influencer_campaign table
                campaign_ids = [campaign["campaign_id"] for campaign in influencer_campaigns]
                
                query_campaign_details = """
                    SELECT * 
                    FROM campaigns 
                    WHERE id IN %s
                """
                
                # Log the query for campaign details
                logging.debug(f"Executing query: {query_campaign_details} with campaign_ids: {campaign_ids}")
                cursor.execute(query_campaign_details, (tuple(campaign_ids),))
                campaigns = cursor.fetchall()

                # Log the campaigns fetched from the campaigns table
                logging.debug(f"Campaign details fetched: {campaigns}")

                if not campaigns:
                    return jsonify({"campaigns": []}), 200  # Return empty list if no matching campaigns

                # Return both influencer_campaigns and campaigns as separate objects
                return jsonify({
                    "influencer_campaigns": [dict(record) for record in influencer_campaigns],  # Convert list of tuples to list of dicts
                    "campaigns": [dict(record) for record in campaigns]  # Convert list of tuples to list of dicts
                }), 200

    except Exception as e:
        logging.error(f"Error fetching active campaigns: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/notifications/display', methods=['GET'])
def display_notifications():
    """Endpoint to display notifications for a user."""
    try:
        # Use query parameters for GET requests
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({"error": "user_id is required"}), 400

        # Fetch notifications for the user
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                query = """
                SELECT content, created_at 
                FROM notifications 
                WHERE user_id = %s 
                ORDER BY created_at DESC
                """
                cursor.execute(query, (user_id,))
                notifications = cursor.fetchall()

                if not notifications:
                    return jsonify({"message": "No notifications found for the user"}), 200

        # Prepare the response
        notification_list = [
            {"content": notification[0], "created_at": notification[1].isoformat() if notification[1] else None}
            for notification in notifications
        ]

        return jsonify({
            "message": "Notifications retrieved successfully",
            "notifications": notification_list
        }), 200

    except Exception as e:
        logging.error(f"Error retrieving notifications: {str(e)}")
        return jsonify({"error": "An error occurred while retrieving notifications"}), 500

def start_scheduler():
    schedule_campaign_status_update()

if __name__ == '__main__':
    start_scheduler()
    app.run(debug=True)
