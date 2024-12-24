import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime, timedelta
import secrets
import string
from flask_mail import Message, Mail
import logging
from email.mime.text import MIMEText
import smtplib
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import time  
import pytz

logger = logging.getLogger(__name__)

# Get the database URL from environment variables
DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Establishing a connection to Neon DB
def get_db_connection():
    return psycopg2.connect(DB_URL)

# Get the user ID by email
def get_user_id_by_email(email):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            query = "SELECT user_id FROM user_data WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return result[0] if result else None

# Create a campaign in the database
def create_campaign_in_db(data):
    # Ensure status, start_date, and end_date are included in data
    data['status'] = 'active'
    data['start_date'] = data.get('start_date', datetime.now())
    data['end_date'] = data.get('end_date', datetime.now())
    
    # Log data to ensure it's a dictionary before insertion
    logging.debug(f"Creating campaign with data: {data}")

    query = """
        INSERT INTO campaigns (
            user_id, brand_name, brand_instagram_id, product, website, email,
            caption, hashtag, tags, content_type, target_followers,
            influencer_gender, influencer_location, campaign_title, target_reach,
            budget, goal, manager_name, contact_number, rewards, start_date, end_date, status, brand_logo, campaign_assets, description, deadline
        ) VALUES (
            %(user_id)s, %(brand_name)s, %(brand_instagram_id)s, %(product)s, %(website)s, %(email)s,
            %(caption)s, %(hashtag)s, %(tags)s, %(content_type)s, %(target_followers)s,
            %(influencer_gender)s, %(influencer_location)s, %(campaign_title)s, %(target_reach)s,
            %(budget)s, %(goal)s, %(manager_name)s, %(contact_number)s, %(rewards)s, %(start_date)s, %(end_date)s, %(status)s, %(brand_logo)s, %(campaign_assets)s, %(description)s, %(deadline)s
        )
        RETURNING *;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Execute the query with data
                cursor.execute(query,data)
                
                # Fetch the inserted campaign data
                campaign = cursor.fetchone()
                
                # Log the inserted campaign data
                logging.debug(f"Inserted campaign: {campaign}")
                
                # Commit transaction
                conn.commit()

                return campaign
    except Exception as e:
        # Log error for more details
        logging.error(f"Error creating campaign: {str(e)}")
        raise Exception(f"Error creating campaign: {str(e)}")

def update_campaign_status():
    try:
        # Get the current IST time
        ist_timezone = pytz.timezone("Asia/Kolkata")
        current_time = datetime.now(ist_timezone)
        logging.info(f"Campaign status update started at {current_time}")

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Fetch all campaigns
                query = """
                    SELECT id, start_date, end_date, status
                    FROM campaigns
                """
                cursor.execute(query)
                campaigns = cursor.fetchall()

                for campaign in campaigns:
                    campaign_id, start_date, end_date, status = campaign

                    # Convert to IST if not already timezone-aware
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=pytz.UTC).astimezone(ist_timezone)
                    if end_date.tzinfo is None:
                        end_date = end_date.replace(tzinfo=pytz.UTC).astimezone(ist_timezone)

                    # Determine the new status
                    if current_time < start_date:
                        new_status = 'upcoming'
                    elif start_date <= current_time <= end_date:
                        new_status = 'active'
                    else:
                        new_status = 'expired'

                    # Update the status if it has changed
                    if new_status != status:
                        update_query = """
                            UPDATE campaigns
                            SET status = %s
                            WHERE id = %s
                        """
                        cursor.execute(update_query, (new_status, campaign_id))
                        conn.commit()
                        logging.info(f"Campaign ID {campaign_id} updated to status {new_status}")

                # Update influencer_campaign status
                influencer_query = """
                    SELECT campaign_id, campaign_status, submission_url, deadline, start_date
                    FROM influencer_campaign
                """
                cursor.execute(influencer_query)
                influencer_campaigns = cursor.fetchall()

                for campaign in influencer_campaigns:
                    campaign_id, campaign_status, submission_url, deadline, start_date = campaign

                    # Convert to IST if not already timezone-aware
                    if start_date.tzinfo is None:
                        start_date = start_date.replace(tzinfo=pytz.UTC).astimezone(ist_timezone)
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=pytz.UTC).astimezone(ist_timezone)

                    # Determine new campaign_status
                    if current_time < start_date:
                        new_campaign_status = 'submissiondue'
                    elif start_date <= current_time <= deadline:
                        new_campaign_status = 'live' if submission_url else 'submissiondue'
                    elif current_time > deadline and not submission_url:
                        new_campaign_status = 'rejected'
                    elif current_time > deadline and submission_url:
                        new_campaign_status = 'past'
                    else:
                        new_campaign_status = 'expired'

                    # Update if status has changed
                    if new_campaign_status != campaign_status:
                        update_query = """
                            UPDATE influencer_campaign
                            SET campaign_status = %s
                            WHERE campaign_id = %s
                        """
                        cursor.execute(update_query, (new_campaign_status, campaign_id))
                        conn.commit()
                        logging.info(f"Influencer Campaign ID {campaign_id} updated to status {new_campaign_status}")

        logging.info("Campaign status update completed.")

    except Exception as e:
        logging.error(f"Error updating campaign status: {e}")

# Function to continuously check and update campaign statuses
def run_continuously():
    logging.info("Starting continuous campaign status updates.")
    while True:
        update_campaign_status()
        time.sleep(60) 
