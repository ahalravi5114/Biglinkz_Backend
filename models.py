import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_db_connection():
    """Establish a connection to the database."""
    DB_URL = os.getenv('DATABASE_URL')
    if not DB_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    return psycopg2.connect(DB_URL)

def create_campaign_in_db(campaign_details):
    """Insert campaign details into the database and return the created campaign."""
    query = """
    INSERT INTO campaigns (
        brand_name, brand_instagram_id, product, website, email, 
        caption, hashtag, tags, content_type, deadline, target_followers,
        influencer_gender, influencer_location, campaign_title, target_reach,
        budget, goal, manager_name, contact_number, rewards
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    ) RETURNING *
    """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (
                campaign_details['brand_name'], campaign_details['brand_instagram_id'], campaign_details['product'],
                campaign_details['website'], campaign_details['email'], 
                campaign_details['caption'], campaign_details['hashtag'], campaign_details['tags'],
                campaign_details['content_type'], campaign_details['deadline'], campaign_details['target_followers'],
                campaign_details['influencer_gender'], campaign_details['influencer_location'], 
                campaign_details['campaign_title'], campaign_details['target_reach'], 
                campaign_details['budget'], campaign_details['goal'], 
                campaign_details['manager_name'], campaign_details['contact_number'], campaign_details['rewards']
            ))
            campaign = cursor.fetchone()
            conn.commit()
            return campaign
    except Exception as e:
        conn.rollback()
        raise Exception(f"Error creating campaign: {str(e)}")
    finally:
        conn.close()

def get_user_id_by_email(email):
    """Retrieve user ID based on email."""
    query = "SELECT id FROM user_data WHERE email = %s"
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (email,))
            user = cursor.fetchone()
            return user['id'] if user else None
    except Exception as e:
        raise Exception(f"Error fetching user ID: {str(e)}")
    finally:
        conn.close()
