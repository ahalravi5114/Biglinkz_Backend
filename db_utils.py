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
            data['status'] = 'active'
            cursor.execute(query, (
                data['brand_name'], data['brand_instagram_id'], data['product'],
                data['website'], data['email'], 
                data['caption'], data['hashtag'], data['tags'],
                data['content_type'], data['deadline'], data['target_followers'],
                data['influencer_gender'], data['influencer_location'], 
                data['campaign_title'], data['target_reach'], 
                data['budget'], data['goal'], 
                data['manager_name'], data['contact_number'], data['rewards'],
                data['user_id'], start_date, end_date, data['status']
            ))

            campaign = cursor.fetchone()
            conn.commit()
            return campaign
    except Exception as e:
        conn.rollback()
        raise Exception(f"Error creating campaign: {str(e)}")
    finally:
        conn.close()
