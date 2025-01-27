from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from db_utils import get_user_id_by_email, create_campaign_in_db, get_db_connection, update_campaign_status
import os
from datetime import datetime, timedelta
import pytz
import logging
from psycopg2.extras import DictCursor
from instagrapi import Client  
import smtplib 
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
import cloudinary
import cloudinary.uploader
import cloudinary.api
from threading import Thread

app = Flask(__name__)  
CORS(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

cloudinary.config(
    cloud_name="dfjafdlaa", 
    api_key="633636381374495", 
    api_secret="yawcgmBjl2wypJ4BHHXyR-LJY2s"
)

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
    """Endpoint for creating a new campaign with file uploads to Cloudinary."""
    try:
        # Parse form data and files
        data = request.form.to_dict()
        files = request.files

        # Validate required fields
        required_fields = [
            'brand_name', 'brand_instagram_id', 'product', 'website', 'email',
            'caption', 'hashtag', 'tags', 'content_type', 'target_followers',
            'influencer_gender', 'influencer_location', 'campaign_title', 'target_reach',
            'budget', 'goal', 'manager_name', 'contact_number', 'rewards',
            'start_date', 'end_date', 'brand_logo', 'campaign_assets', 'description'
        ]

        for field in required_fields:
            if field not in data or not data[field]:
                if field in ['brand_logo', 'campaign_assets']:
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

        data['user_id'] = user_id

        # Upload brand logo to Cloudinary
        brand_logo = files.get('brand_logo')
        if brand_logo:
            upload_response = cloudinary.uploader.upload(
                brand_logo,
                folder="brand_logos",
                use_filename=True,
                unique_filename=True,
                invalidate=True
            )
            if not upload_response or 'secure_url' not in upload_response:
                return jsonify({"error": "Failed to upload brand logo"}), 500
            data['brand_logo'] = upload_response['secure_url']

        # Parse and validate start_date
        start_date_str = data['start_date']
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            deadline = start_date - timedelta(days=20)
            data['deadline'] = deadline.strftime('%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format for start_date. Expected format: YYYY-MM-DD"}), 400

        # Upload campaign assets to Cloudinary
        asset_files = files.getlist('campaign_assets')
        asset_urls = []
        for asset in asset_files:
            upload_response = cloudinary.uploader.upload(
                asset,
                folder="campaign_assets",
                use_filename=True,
                unique_filename=True,
                invalidate=True
            )
            if not upload_response or 'secure_url' not in upload_response:
                return jsonify({"error": "Failed to upload campaign asset"}), 500
            asset_urls.append(upload_response['secure_url'])
        data['campaign_assets'] = ','.join(asset_urls)

        # Insert into database
        create_campaign_in_db(data)  # Ensure this function accepts dictionaries

        return jsonify({"message": "Campaign created successfully"}), 201

    except Exception as e:
        logging.error(f"Error creating campaign: {str(e)}", exc_info=True)
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
                    campaign_assets = (
                        campaign["campaign_assets"].split(",") 
                        if campaign["campaign_assets"] else []
                    )
                    campaign_assets = [url.strip() for url in campaign_assets]

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
                        "brand_logo": campaign["brand_logo"],
                        "campaign_assets": campaign_assets,                       
                        "description": campaign["description"],
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
                # Check if the user_id exists in the table
                check_query = """
                    SELECT 1 FROM influencer_profile WHERE user_id = %s
                """
                cursor.execute(check_query, (data["user_id"],))
                existing_user = cursor.fetchone()

                if existing_user:
                    # If user_id exists, update the record
                    update_query = """
                        UPDATE influencer_profile
                        SET first_name = %s, last_name = %s, insta_id = %s, email = %s, 
                            phone_number = %s, followers = %s, country = %s, state = %s, 
                            city = %s, category = %s
                        WHERE user_id = %s
                    """
                    cursor.execute(update_query, (
                        data["first_name"], data["last_name"], data["insta_id"],
                        data["email"], data["phone_number"], data["followers"],
                        data["country"], data["state"], data["city"], data["category"],
                        data["user_id"]
                    ))
                else:
                    # If user_id does not exist, insert a new record
                    insert_query = """
                        INSERT INTO influencer_profile (
                            user_id, first_name, last_name, insta_id, email, phone_number, followers,
                            country, state, city, category
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        data["user_id"], data["first_name"], data["last_name"], data["insta_id"],
                        data["email"], data["phone_number"], data["followers"],
                        data["country"], data["state"], data["city"], data["category"]
                    ))

                conn.commit()

        return jsonify({"message": "Profile added/updated successfully"}), 200
    except Exception as e:
        logging.error(f"Error handling profile: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

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

@app.route('/eligible-campaigns', methods=['GET'])
def get_eligible_campaigns():
    """
    Endpoint for influencers to see campaigns they are eligible for.
    Compares influencer's followers count with target_followers of campaigns.
    Excludes campaigns already present in the influencer_campaign table.
    """
    try:
        # Get the user_id from the query parameters
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        # Fetch influencer's insta_id and followers count from the database based on user_id
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                influencer_query = """
                    SELECT id AS influencer_id, insta_id, followers
                    FROM influencer_profile
                    WHERE user_id = %s
                """
                cursor.execute(influencer_query, (user_id,))
                influencer = cursor.fetchone()

                if not influencer:
                    return jsonify({"error": "Influencer profile not found"}), 404

                influencer_id = influencer["influencer_id"]
                influencer_followers = influencer["followers"]

                campaign_query = """
                    SELECT *
                    FROM campaigns
                    WHERE CAST(target_followers AS INTEGER) <= %s
                """
                cursor.execute(campaign_query, (influencer_followers,))

                campaigns = cursor.fetchall()
                if not campaigns:
                    return jsonify({"message": "No eligible campaigns found"}), 200

                campaign_list = []
                for campaign in campaigns:
                    campaign_assets = (
                        campaign["campaign_assets"].split(",") 
                        if campaign["campaign_assets"] else []
                    )
                    campaign_assets = [url.strip() for url in campaign_assets]

                eligible_campaigns = [
                    {
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
                        "brand_logo": campaign["brand_logo"],
                        "campaign_assets": campaign_assets,
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
                    WHERE influencer_id = %s AND influencer_status = 'accepted' AND campaign_status!='past'
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

                processed_campaigns = []
                for campaign in campaigns:
                    campaign_dict = dict(campaign)  # Convert to dict
                    if "campaign_assets" in campaign_dict and campaign_dict["campaign_assets"]:
                        # Split campaign_assets by comma into a list
                        campaign_dict["campaign_assets"] = campaign_dict["campaign_assets"].split(",")
                    processed_campaigns.append(campaign_dict)

                # Return both influencer_campaigns and processed campaigns as separate objects
                return jsonify({
                    "influencer_campaigns": [dict(record) for record in influencer_campaigns],  # Convert list of tuples to list of dicts
                    "campaigns": processed_campaigns  # Return campaigns with campaign_assets as an array
                }), 200

    except Exception as e:
        logging.error(f"Error fetching active campaigns: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/past-campaigns', methods=['GET'])
def past_campaigns():
    """Endpoint for fetching past campaigns for an influencer based on submitted URLs."""
    try:
        influencer_id = request.args.get('user_id')
        if not influencer_id:
            return jsonify({"error": "User ID is required"}), 400

        # Log the user_id being passed
        logging.debug(f"Fetching past campaigns for influencer user_id: {influencer_id}")

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                # Step 1: Fetch all influencer campaign details where campaign_status is 'past' and a submission_url exists
                query_influencer_campaigns = """
                    SELECT influencer_id, campaign_id, influencer_status, campaign_status, submission_url
                    FROM influencer_campaign 
                    WHERE influencer_id = %s 
                    AND campaign_status = 'past'
                    AND submission_url IS NOT NULL
                """
                
                # Log the query for influencer campaigns
                logging.debug(f"Executing query: {query_influencer_campaigns} with user_id: {influencer_id}")
                cursor.execute(query_influencer_campaigns, (influencer_id,))
                influencer_campaigns = cursor.fetchall()

                # If no campaigns are found for the influencer, return an empty list
                if not influencer_campaigns:
                    return jsonify({"influencer_campaigns": [], "campaigns": []}), 200

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

                # Return both influencer_campaigns and campaigns as separate objects
                processed_campaigns = []
                for campaign in campaigns:
                    campaign_dict = dict(campaign)  # Convert to dict
                    if "campaign_assets" in campaign_dict and campaign_dict["campaign_assets"]:
                        # Split campaign_assets by comma into a list
                        campaign_dict["campaign_assets"] = campaign_dict["campaign_assets"].split(",")
                    processed_campaigns.append(campaign_dict)

                # Return both influencer_campaigns and processed campaigns as separate objects
                return jsonify({
                    "influencer_campaigns": [dict(record) for record in influencer_campaigns],  # Convert list of tuples to list of dicts
                    "campaigns": processed_campaigns  # Return campaigns with campaign_assets as an array
                }), 200

    except Exception as e:
        logging.error(f"Error fetching past campaigns: {str(e)}")
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
                SELECT id, content, campaign_id, created_at , status
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
            {"id": notification[0], "content": notification[1],"campaign_id": notification[2], "created_at": notification[3].isoformat() if notification[3] else None., "status": notification[4]}
            for notification in notifications
        ]

        return jsonify({
            "message": "Notifications retrieved successfully",
            "notifications": notification_list
        }), 200

    except Exception as e:
        logging.error(f"Error retrieving notifications: {str(e)}")
        return jsonify({"error": "An error occurred while retrieving notifications"}), 500

@app.route('/update-notification', methods=['POST'])
def update_notification_status():
    """
    Endpoint to update the status of a notification to 'viewed'.
    Expects notification_id in the JSON payload.
    """
    try:
        data = request.get_json()

        # Check for required field
        if "notification_id" not in data:
            return jsonify({"error": "Missing field: notification_id"}), 400

        notification_id = data["notification_id"]

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if the notification exists
                select_query = """
                    SELECT id, status FROM notifications
                    WHERE id = %s
                """
                cursor.execute(select_query, (notification_id,))
                notification = cursor.fetchone()

                if not notification:
                    return jsonify({"error": "Notification not found"}), 404

                # Update status if not already 'viewed'
                if notification[1] == 'viewed':
                    return jsonify({"message": "Notification is already marked as viewed"}), 200

                update_query = """
                    UPDATE notifications
                    SET status = 'viewed'
                    WHERE id = %s
                """
                cursor.execute(update_query, (notification_id,))
                conn.commit()

        return jsonify({"message": "Notification status updated to 'viewed'"}), 200
    except Exception as e:
        logging.error(f"Error updating notification status: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    
@app.route('/update-status', methods=['GET'])
def update_status():
    try:
        update_campaign_status()
        return jsonify({"message": "Campaign statuses updated successfully"}), 200
    except Exception as e:
        logging.error(f"Error updating campaign statuses: {e}")
        return jsonify({"error": "Failed to update campaign statuses"}), 500

@app.route('/get-campaign-influencers', methods=['GET'])
def get_campaign_influencers():
    """Endpoint for fetching influencers associated with a specific campaign."""
    try:
        campaign_id = request.args.get('campaign_id')
        if not campaign_id:
            return jsonify({"error": "Campaign ID is required"}), 400

        # Log the campaign_id being passed
        logging.debug(f"Fetching influencers for campaign_id: {campaign_id}")

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                # First query: Fetch influencer IDs and their submission URLs where the status is "accepted"
                campaign_query = """
                    SELECT 
                        influencer_id,
                        submission_url
                    FROM 
                        influencer_campaign
                    WHERE 
                        campaign_id = %s AND influencer_status = 'accepted'
                """
                logging.debug(f"Executing campaign query: {campaign_query} with campaign_id: {campaign_id}")
                cursor.execute(campaign_query, (campaign_id,))
                influencer_campaign_data = cursor.fetchall()

                # Log campaign-related data
                logging.debug(f"Accepted campaign influencers found: {influencer_campaign_data}")

                if not influencer_campaign_data:
                    return jsonify({"influencers": []}), 200  # Return empty list if no influencers found

                # Second query: Fetch details for each influencer
                influencer_details = []
                for record in influencer_campaign_data:
                    influencer_id = record["influencer_id"]

                    profile_query = """
                        SELECT 
                            first_name,
                            last_name,
                            insta_id
                        FROM 
                            influencer_profile
                        WHERE 
                            user_id = %s
                    """
                    logging.debug(f"Executing profile query: {profile_query} with influencer_id: {influencer_id}")
                    cursor.execute(profile_query, (influencer_id,))
                    profile_data = cursor.fetchone()

                    if profile_data:
                        influencer_details.append({
                            "influencer_id": influencer_id,
                            "first_name": profile_data["first_name"],
                            "last_name": profile_data["last_name"],
                            "insta_id": profile_data["insta_id"],
                            "submission_url": record["submission_url"]
                        })

                # Log the final influencer details
                logging.debug(f"Final influencer details: {influencer_details}")

                return jsonify({"influencers": influencer_details}), 200

    except Exception as e:
        logging.error(f"Error fetching influencers: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/businessprofile', methods=['POST'])
def store_business():
    """
    Endpoint to add or update business profile details.
    Expects business details in JSON payload.
    """
    try:
        data = request.get_json()

        required_fields = [
            "name", "email", "website","country","city","state", "category","user_id", 
        ]

        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400

        # Optional fields
        insta_id = data.get("insta_id")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if the email exists in the table
                check_query = """
                    SELECT 1 FROM business_profile WHERE user_id = %s
                """
                cursor.execute(check_query, (data["user_id"],))
                existing_business = cursor.fetchone()

                if existing_business:
                    # If email exists, update the record
                    update_query = """
                        UPDATE business_profile
                        SET name = %s, website = %s, insta_id = %s,
                            country = %s, state = %s, city = %s, category = %s, email= %s
                        WHERE user_id = %s
                    """
                    cursor.execute(update_query, (
                        data["name"], data["website"], insta_id,
                        data["country"], data["state"],data["city"],data["category"],data["email"],
                        data["user_id"]
                    ))
                else:
                    # If email does not exist, insert a new record
                    insert_query = """
                        INSERT INTO business_profile (
                            name, email, website, insta_id,
                            country,state,city, category,user_id
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        data["name"], data["email"], data["website"], insta_id,
                        data["country"],data["state"],data["city"], data["category"],data["user_id"]
                    ))

                conn.commit()

        return jsonify({"message": "Business profile added/updated successfully"}), 200
    except Exception as e:
        logging.error(f"Error handling business profile: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500
        
@app.route('/getBusinessProfile/<user_id>', methods=['GET'])
def get_business_by_user_id(user_id):
    """
    Endpoint to get business profile details based on user_id.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Query to fetch the business profile details for the given user_id
                select_query = """
                    SELECT name, email, website, insta_id, country, state, city, category
                    FROM business_profile
                    WHERE user_id = %s
                """
                cursor.execute(select_query, (user_id,))
                business = cursor.fetchone()

                if business:
                    # Prepare response with the business profile data
                    business_data = {
                        "name": business[0],
                        "email": business[1],
                        "website": business[2],
                        "insta_id": business[3],
                        "country": business[4],
                        "state": business[5],
                        "city": business[6],
                        "category": business[7],
                    }
                    return jsonify(business_data), 200
                else:
                    return jsonify({"error": "Business profile not found"}), 404

    except Exception as e:
        logging.error(f"Error fetching business profile for user_id {user_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/addAccountDetails', methods=['POST'])
def add_payment():
    """
    Endpoint to add or update payment details.
    Expects payment details in JSON payload along with user_id.
    """
    try:
        data = request.get_json()

        required_fields = ["user_id", "account_number", "upi", "ifsc", "mici"]

        # Check for missing fields in the payload
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if the user_id exists in the payments table
                check_query = """
                    SELECT 1 FROM payments WHERE user_id = %s
                """
                cursor.execute(check_query, (data["user_id"],))
                existing_user = cursor.fetchone()

                if existing_user:
                    # If user_id exists, update the record
                    update_query = """
                        UPDATE payments
                        SET account_number = %s, upi = %s, ifsc = %s, mici = %s
                        WHERE user_id = %s
                    """
                    cursor.execute(update_query, (
                        data["account_number"], data["upi"], data["ifsc"], 
                        data["mici"], data["user_id"]
                    ))
                else:
                    # If user_id does not exist, insert a new record
                    insert_query = """
                        INSERT INTO payments (user_id, account_number, upi, ifsc, mici)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    cursor.execute(insert_query, (
                        data["user_id"], data["account_number"], data["upi"], 
                        data["ifsc"], data["mici"]
                    ))

                conn.commit()

        return jsonify({"message": "Payment details added/updated successfully"}), 200
    except Exception as e:
        logging.error(f"Error handling payment details: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/payment/<user_id>', methods=['GET'])
def get_payment(user_id):
    """
    Endpoint to get payment details based on user_id.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Query to fetch the payment details for the given user_id
                select_query = """
                    SELECT account_number, upi, ifsc, mici, balance
                    FROM payments
                    WHERE user_id = %s
                """
                cursor.execute(select_query, (user_id,))
                payment = cursor.fetchone()

                if payment:
                    # Prepare response with the payment data
                    payment_data = {
                        "account_number": payment[0],
                        "upi": payment[1],
                        "ifsc": payment[2],
                        "mici": payment[3],
                        "balance": payment[4]
                    }
                    return jsonify(payment_data), 200
                else:
                    return jsonify({"error": "Payment details not found"}), 404

    except Exception as e:
        logging.error(f"Error fetching payment details for user_id {user_id}: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/setOrCheckPassword', methods=['POST'])
def set_or_check_password():
    """
    Endpoint to set or check the password in the payments table.
    If the password is being set for the first time, store its hashed value.
    If the password already exists, check if it matches the stored hash.
    """
    try:
        data = request.get_json()

        required_fields = ["user_id", "password"]

        # Check for missing fields in the payload
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing fields: {', '.join(missing_fields)}"}), 400

        user_id = data["user_id"]
        password = data["password"]

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Check if the user_id exists and if a password is already set
                check_query = """
                    SELECT password FROM payments WHERE user_id = %s
                """
                cursor.execute(check_query, (user_id,))
                result = cursor.fetchone()

                if result:
                    # Password already exists, verify it
                    stored_password_hash = result[0]
                    if check_password_hash(stored_password_hash, password):
                        return jsonify({"message": "Password verified successfully."}), 200
                    else:
                        return jsonify({"error": "Incorrect password."}), 401
                else:
                    # Password not set, store the hashed password
                    hashed_password = generate_password_hash(password, method='sha256')
                    insert_query = """
                        INSERT INTO payments (user_id, password)
                        VALUES (%s, %s)
                    """
                    cursor.execute(insert_query, (user_id, hashed_password))
                    conn.commit()

                    return jsonify({"message": "Password set successfully."}), 200

    except Exception as e:
        logging.error(f"Error in set_or_check_password: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
