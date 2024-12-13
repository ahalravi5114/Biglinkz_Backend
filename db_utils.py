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
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            query = "SELECT user_id FROM user_data WHERE email = %s"
            cursor.execute(query, (email,))
            result = cursor.fetchone()
            return result[0] if result else None

def create_campaign_in_db(data):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            query = """
                INSERT INTO campaigns (
                    user_id, brand_name, brand_instagram_id, product, website, email,
                    caption, hashtag, tags, content_type, deadline, target_followers,
                    influencer_gender, influencer_location, campaign_title, target_reach,
                    budget, goal, manager_name, contact_number, rewards, start_date, end_date
                ) VALUES (
                    %(user_id)s, %(brand_name)s, %(brand_instagram_id)s, %(product)s, %(website)s, %(email)s,
                    %(caption)s, %(hashtag)s, %(tags)s, %(content_type)s, %(deadline)s, %(target_followers)s,
                    %(influencer_gender)s, %(influencer_location)s, %(campaign_title)s, %(target_reach)s,
                    %(budget)s, %(goal)s, %(manager_name)s, %(contact_number)s, %(rewards)s, %(start_date)s, %(end_date)s
                )
            """
            cursor.execute(query, data)
            conn.commit()
            
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
