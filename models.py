import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Establishing a connection to the database
def get_db_connection():
    DB_URL = os.getenv('DATABASE_URL')
    return psycopg2.connect(DB_URL)

# Function to insert campaign details into the database
def create_campaign_in_db(campaign_details):
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(query, (
        campaign_details['brand_name'], campaign_details['brand_instagram_id'], campaign_details['product'],
        campaign_details['website'], campaign_details['email'], 
        campaign_details['caption'], campaign_details['hashtag'], campaign_details['tags'],
        campaign_details['content_type'], campaign_details['deadline'], campaign_details['target_followers'],
        campaign_details['influencer_gender'], campaign_details['influencer_location'], campaign_details['campaign_title'],
        campaign_details['target_reach'], campaign_details['budget'], campaign_details['goal'],
        campaign_details['manager_name'], campaign_details['contact_number'], campaign_details['rewards']
    ))
    campaign = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()
    return campaign