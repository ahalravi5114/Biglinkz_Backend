import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

# Get the database URL from environment variables
DB_URL = os.getenv('DATABASE_URL')
if not DB_URL:
    raise ValueError("DATABASE_URL environment variable is not set.")

# Establishing a connection to Neon DB
def get_db_connection():
    return psycopg2.connect(DB_URL)

def get_user_id_by_email(email):
    """Fetch the user_id for a given email."""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            query = "SELECT user_id FROM user_data WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        print(f"Error fetching user_id for email {email}: {e}")
        return None
    finally:
        conn.close()

def create_campaign_in_db(campaign_details):
    """Insert campaign details into the database and return the created campaign."""
    # Parse the start_date and end_date into datetime objects
    start_date = datetime.strptime(campaign_details['start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(campaign_details['end_date'], '%Y-%m-%d')

    query = """
    INSERT INTO campaigns (
        brand_name, brand_instagram_id, product, website, email, 
        caption, hashtag, tags, content_type, deadline, target_followers,
        influencer_gender, influencer_location, campaign_title, target_reach,
        budget, goal, manager_name, contact_number, rewards, user_id, start_date, end_date, status
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active'
    ) RETURNING *
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            campaign_details['status'] = 'active'
            cursor.execute(query, (
                campaign_details['brand_name'], campaign_details['brand_instagram_id'], campaign_details['product'],
                campaign_details['website'], campaign_details['email'], 
                campaign_details['caption'], campaign_details['hashtag'], campaign_details['tags'],
                campaign_details['content_type'], campaign_details['deadline'], campaign_details['target_followers'],
                campaign_details['influencer_gender'], campaign_details['influencer_location'], 
                campaign_details['campaign_title'], campaign_details['target_reach'], 
                campaign_details['budget'], campaign_details['goal'], 
                campaign_details['manager_name'], campaign_details['contact_number'], campaign_details['rewards'],
                campaign_details['user_id'], start_date, end_date, campaign_details['status']
            ))

            campaign = cursor.fetchone()
            conn.commit()
            return campaign
    except Exception as e:
        conn.rollback()
        raise Exception(f"Error creating campaign: {str(e)}")
    finally:
        conn.close()
