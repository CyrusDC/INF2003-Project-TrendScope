import os
from flask import Flask, jsonify
from pymongo import MongoClient
from dotenv import load_dotenv

# Load connection strings from the .env file
load_dotenv()

app = Flask(__name__)

# ==========================================
# ESTABLISH MONGODB CONNECTION
# ==========================================
mongo_client = MongoClient(os.environ.get("MONGO_URI"))
# IMPORTANT: This must match Compass exactly (e.g. 'youtube' or 'Youtube')
mongo_db = mongo_client["Youtube"] 
print("Connected to MongoDB Atlas successfully!")


@app.route('/api/debug', methods=['GET'])
def debug():
    try:
        mongo_client.admin.command("ping")  # real connection test
        info = {}
        for db_name in mongo_client.list_database_names():
            db = mongo_client[db_name]
            info[db_name] = {
                col: db[col].count_documents({})
                for col in db.list_collection_names()
            }
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# View Raw JSON Data
@app.route('/api/nosql/revenue', methods=['GET'])
def get_nosql_revenue():
    """Queries the flexible JSON documents from MongoDB."""
    try:
        revenue_collection = mongo_db["mongodb_revenue"]
        data = list(revenue_collection.find({}, {"_id": 0}).limit(10))
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# 1. Ad Revenue for Different Countries
# ==========================================
@app.route('/api/revenue/country', methods=['GET'])
def get_revenue_by_country():
    """Calculates total estimated revenue grouped by country_code."""
    try:
        revenue_collection = mongo_db["mongodb_revenue"]
        pipeline = [
            {"$unwind": "$revenue_by_country"},
            {"$group": {
                "_id": "$revenue_by_country.country_code",
                "total_estimated_revenue": {"$sum": "$revenue_by_country.estimated_gross_usd"}
            }},
            {"$sort": {"total_estimated_revenue": -1}}
        ]
        results = list(revenue_collection.aggregate(pipeline))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# 2. Filter by Creator Tier
# ==========================================
@app.route('/api/videos/tier/<tier>', methods=['GET'])
def get_videos_by_tier(tier):
    """Finds all videos matching a specific creator tier (e.g., 'large')."""
    try:
        revenue_collection = mongo_db["mongodb_revenue"]
        query = {"creator_tier": tier}
        projection = {"_id": 0, "video_id": 1, "creator_tier": 1, "channel_id": 1}
        results = list(revenue_collection.find(query, projection).limit(10))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# 3. Analyzing Categories
# ==========================================

@app.route('/api/analytics/categories', methods=['GET'])
def analyze_categories():
    """Analyzes document counts per category_id."""
    try:
        revenue_collection = mongo_db["mongodb_revenue"]
        pipeline = [
            {"$group": {
                "_id": "$category_id",
                "total_videos": {"$sum": 1}
            }},
            {"$sort": {"total_videos": -1}}
        ]
        results = list(revenue_collection.aggregate(pipeline))
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Run the Flask server
if __name__ == '__main__':
    # print(app.url_map)
    app.run(debug=True, port=5000)