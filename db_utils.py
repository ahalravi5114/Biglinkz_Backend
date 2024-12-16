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


logger = logging.getLogger(__name__)


# Get the database URL from environment variables
DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Establishing a connection to Neon DB
def get_db_connection():
    return psycopg2.connect(DB_URL)

def generate_otp():
    import random
    return str(random.randint(100000, 999999))

# Function to send OTP email
def send_otp_via_email(sender_email, app_password, recipient_email, otp):
    try:
        # Set up SMTP server
        mail = smtplib.SMTP('smtp.gmail.com', 587)
        mail.starttls()

        # Log in with App Password
        mail.login(sender_email, app_password)

        # Prepare the email content
        subject = "Your OTP Code"
        body = f"Your OTP code is: {otp}. It will expire in 5 minutes."
        message = MIMEText(body, 'plain')
        message['Subject'] = subject
        message['From'] = sender_email
        message['To'] = recipient_email

        # Send the email
        mail.sendmail(sender_email, recipient_email, message.as_string())
        mail.quit()
    except Exception as e:
        raise Exception(f"Failed to send email: {str(e)}")

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
            caption, hashtag, tags, content_type, deadline, target_followers,
            influencer_gender, influencer_location, campaign_title, target_reach,
            budget, goal, manager_name, contact_number, rewards, start_date, end_date, status
        ) VALUES (
            %(user_id)s, %(brand_name)s, %(brand_instagram_id)s, %(product)s, %(website)s, %(email)s,
            %(caption)s, %(hashtag)s, %(tags)s, %(content_type)s, %(deadline)s, %(target_followers)s,
            %(influencer_gender)s, %(influencer_location)s, %(campaign_title)s, %(target_reach)s,
            %(budget)s, %(goal)s, %(manager_name)s, %(contact_number)s, %(rewards)s, %(start_date)s, %(end_date)s, %(status)s
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