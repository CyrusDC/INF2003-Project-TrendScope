import re
import datetime

def validate_category(category_id, category_name):
    if not isinstance(category_id, int) or category_id < 1:
        return False, "Category ID must be an integer >= 1."
    if not category_name or len(category_name.strip()) == 0 or len(category_name) > 100:
        return False, "Category Name must be between 1 and 100 characters."
    return True, ""

def validate_channel(channel_id, channel_title):
    if not isinstance(channel_id, int) or channel_id < 1:
        return False, "Channel ID must be an integer >= 1."
    if not channel_title or len(channel_title.strip()) == 0 or len(channel_title) > 255:
        return False, "Channel Title must be between 1 and 255 characters."
    return True, ""

def validate_country(country_code, country_name, population):
    if not country_code or len(country_code) != 2 or not country_code.isalpha():
        return False, "Country Code must be exactly 2 alphabetic characters."
    if not country_name or len(country_name.strip()) == 0 or len(country_name) > 100:
        return False, "Country Name must be between 1 and 100 characters."
    if not isinstance(population, int) or population < 0:
        return False, "Population must be a non-negative integer (>= 0)."
    return True, ""

def validate_video(video_id, title, tag_count, channel_id, category_id):
    if not video_id or len(video_id) != 11:
        return False, "Video ID must be exactly 11 characters."
    if not title or len(title.strip()) == 0:
        return False, "Video Title cannot be empty."
    if not isinstance(tag_count, int) or tag_count < 0:
        return False, "Tag Count must be a non-negative integer."
    if not isinstance(channel_id, int) or channel_id < 1:
        return False, "Channel ID must be >= 1."
    if not isinstance(category_id, int) or category_id < 1:
        return False, "Category ID must be >= 1."
    return True, ""

def validate_channel_stats(channel_id, country_code, global_rank, subscriber, video_views, uploads, v_last_30, s_last_30):
    if not isinstance(channel_id, int) or channel_id < 1:
        return False, "Channel ID must be >= 1."
    if not country_code or len(country_code) != 2 or not country_code.isalpha():
        return False, "Country Code must be exactly 2 alphabetic characters."
    if not isinstance(global_rank, int) or global_rank < 1:
        return False, "Global Rank must be >= 1."
    if any(val < 0 for val in [subscriber, video_views, uploads, v_last_30, s_last_30]):
        return False, "Subscriber, Views, Uploads, and Last 30 Days stats must be >= 0."
    return True, ""

def validate_trending_record(record_id, video_id, country_code, views, likes, dislikes, comment_count):
    if not isinstance(record_id, int) or record_id < 1:
        return False, "Record ID must be >= 1."
    if not video_id or len(video_id) != 11:
        return False, "Video ID must be exactly 11 characters."
    if not country_code or len(country_code) != 2 or not country_code.isalpha():
        return False, "Country Code must be exactly 2 alphabetic characters."
    if any(val < 0 for val in [views, likes, dislikes, comment_count]):
        return False, "Views, Likes, Dislikes, and Comment Count must be >= 0."
    return True, ""
