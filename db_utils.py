import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import secrets
import string
from flask_mail import Message, Mail
import logging
from email.mime.text import MIMEText
import smtplib
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler


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

    query = """
        INSERT INTO campaigns (
            user_id, brand_name, brand_instagram_id, product, website, email,
            caption, hashtag, tags, content_type,target_followers,
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
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, data)
                campaign = cursor.fetchone()
                conn.commit()
                return campaign
    except Exception as e:
        raise Exception(f"Error creating campaign: {str(e)}")

def update_campaign_status():
    try:
        # Get the current IST time
        ist_timezone = pytz.timezone("Asia/Kolkata")
        current_time = datetime.now(ist_timezone)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Fetch all campaigns that have start_date and end_date
                query = """
                    SELECT id, start_date, end_date, status
                    FROM campaigns
                """
                cursor.execute(query)
                campaigns = cursor.fetchall()

                for campaign in campaigns:
                    campaign_id = campaign[0]
                    start_date = campaign[1]
                    end_date = campaign[2]

                    # Convert the campaign's start_date and end_date to IST if necessary
                    start_date = start_date.astimezone(ist_timezone)
                    end_date = end_date.astimezone(ist_timezone)

                    # Determine the new status based on current time and campaign dates
                    if current_time < start_date:
                        new_status = 'upcoming'
                    elif start_date <= current_time <= end_date:
                        new_status = 'active'
                    else:
                        new_status = 'expired'

                    # If the status needs to be updated, update it in the database
                    if new_status != campaign[3]:  # Only update if status is different
                        update_query = """
                            UPDATE campaigns
                            SET status = %s
                            WHERE id = %s
                        """
                        cursor.execute(update_query, (new_status, campaign_id))
                        conn.commit()

                logging.info(f"Campaign status update completed at {current_time}")

                # Update influencer_campaign status based on additional logic
                query_influencer_campaign = """
                    SELECT campaign_id, campaign_status, submission_url, deadline, start_date
                    FROM influencer_campaign
                    WHERE campaign_status = 'submissiondue'
                """
                cursor.execute(query_influencer_campaign)
                influencer_campaigns = cursor.fetchall()

                for influencer_campaign in influencer_campaigns:
                    campaign_id = influencer_campaign[0]
                    submission_url = influencer_campaign[2]
                    deadline = influencer_campaign[3]
                    start_date = influencer_campaign[4]

                    # Convert the start_date and deadline to IST if necessary
                    deadline = deadline.astimezone(ist_timezone)
                    start_date = start_date.astimezone(ist_timezone)

                    # Determine the new campaign_status for the influencer_campaign
                    if current_time < start_date and current_time < deadline:
                        # Campaign is not started and the deadline is not over
                        new_campaign_status = 'submissiondue'

                    elif start_date <= current_time <= deadline:
                        # Campaign has started, check if submission_url is filled
                        if submission_url:
                            new_campaign_status = 'live'  # Campaign is live and URL is submitted
                        else:
                            new_campaign_status = 'submissiondue'  # Campaign is active but URL not yet submitted

                    elif current_time > deadline and submission_url is None:
                        # Deadline is over and submission URL is not filled
                        new_campaign_status = 'rejected'  # Rejected because submission URL is not filled

                    elif current_time > deadline and submission_url:
                        # Campaign is over and submission URL is filled
                        new_campaign_status = 'past'  # Campaign ended and URL was submitted

                    elif current_time > start_date:
                        # Campaign has ended, no submission URL or the deadline passed
                        new_campaign_status = 'expired'

                    # Only update the campaign_status if it needs to be changed
                    if new_campaign_status != influencer_campaign[1]:  # Check if status is different
                        update_query_influencer_campaign = """
                            UPDATE influencer_campaign
                            SET campaign_status = %s
                            WHERE campaign_id = %s
                        """
                        cursor.execute(update_query_influencer_campaign, (new_campaign_status, campaign_id))
                        conn.commit()

    except Exception as e:
        logging.error(f"Error updating campaign status: {str(e)}")

# APScheduler to schedule the update periodically
def schedule_campaign_status_update():
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(update_campaign_status, 'interval', hours=24)  # Runs every 24 hours
    scheduler.start()