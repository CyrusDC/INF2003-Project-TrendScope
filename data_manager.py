import os
import psycopg2
import pymongo
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

class DataManager:
    """Handles raw database connections, queries, transactions, and rollbacks."""

    # ------------------------------------------------------------------
    # CONNECTION FACTORIES
    # ------------------------------------------------------------------
    @staticmethod
    def get_pg_connection():
        return psycopg2.connect(
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
            dbname=os.getenv("PG_DBNAME"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD")
        )

    @staticmethod
    def get_mongo_collection(collection_name="revenue"):
        client = pymongo.MongoClient(os.getenv("MONGO_URI"))
        db = client[os.getenv("MONGO_DB", "youtube_nosql")]
        return db[collection_name]

    @classmethod
    def _execute_transaction(cls, query, params):
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            result = cur.fetchone()[0]
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------
    # ANALYTICAL VIEWS (POSTGRESQL)
    # ------------------------------------------------------------------
    @classmethod
    def fetch_analytical_view(cls, view_name):
        valid_views = {
            "category_views": "SELECT * FROM get_category_views();",
            "channel_performance": "SELECT * FROM get_channel_performance();",
            "video_reach": "SELECT * FROM get_video_reach();",
            "reaction_ratios": "SELECT * FROM get_video_reaction_ratios();"
        }
        if view_name not in valid_views:
            raise ValueError("Invalid view identifier.")
        
        conn = cls.get_pg_connection()
        try:
            return pd.read_sql(valid_views[view_name], conn)
        finally:
            conn.close()
    # ------------------------------------------------------------------
    # VIDEO KEYWORD SEARCH (POSTGRESQL)
    # ------------------------------------------------------------------
    @classmethod
    def search_videos_with_keyword(cls, keyword):

        sql = """
            SELECT *
            FROM search_videos_with_keyword(%s::text);
        """

        conn = cls.get_pg_connection()

        try:
            return pd.read_sql(sql,conn,params=(keyword,))

        finally:
            conn.close()

    # ------------------------------------------------------------------
    # RELATIONAL CRUD OPERATIONS (POSTGRESQL)
    # ------------------------------------------------------------------
    @classmethod
    def insert_category(cls, cat_id, cat_name):
        return cls._execute_transaction("SELECT insert_category(%s, %s::text);", (cat_id, cat_name))

    @classmethod
    def insert_channel(cls, chan_id, chan_title):
        return cls._execute_transaction("SELECT insert_channel(%s, %s::text);", (chan_id, chan_title))

    @classmethod
    def insert_country(cls, code, name, pop):
        return cls._execute_transaction("SELECT insert_country(%s::text, %s::text, %s);", (code.upper(), name, pop))

    @classmethod
    def insert_video(cls, video_id, title, pub_dt, tag_count, chan_id, cat_id):
        return cls._execute_transaction(
            "SELECT insert_video(%s::text, %s::text, %s, %s, %s, %s);",
            (video_id, title, pub_dt, tag_count, chan_id, cat_id)
        )

    @classmethod
    def insert_channel_stats(cls, chan_id, c_code, rank, sub, views, uploads, dt_val, v30, s30):
        return cls._execute_transaction(
            "SELECT insert_channel_stats(%s, %s::text, %s, %s, %s, %s, %s, %s, %s);",
            (chan_id, c_code.upper(), rank, sub, views, uploads, dt_val, v30, s30)
        )

    @classmethod
    def insert_trending_record(cls, rec_id, vid_id, c_code, t_date, views, likes, dislikes, comments):
        return cls._execute_transaction(
            "SELECT insert_trending_record(%s, %s::text, %s::text, %s, %s, %s, %s, %s);",
            (rec_id, vid_id, c_code.upper(), t_date, views, likes, dislikes, comments)
        )

    @classmethod
    def read_record(cls, table, identifier):
        identifier = str(identifier).strip()
        if not identifier:
            return pd.DataFrame()

        try:
            if table == "Category":
                sql = "SELECT * FROM read_category(%s);"
                params = (int(identifier),)
            elif table == "Channel":
                sql = "SELECT * FROM read_channel(%s);"
                params = (int(identifier),)
            elif table == "Country":
                sql = "SELECT * FROM read_country(%s::text);"
                params = (identifier.upper(),)
            elif table == "Video":
                sql = "SELECT * FROM read_video(%s::text);"
                params = (identifier,)
            elif table == "Channel Stats":
                sql = "SELECT * FROM read_channel_stats(%s);"
                params = (int(identifier),)
            elif table == "Trending Record":
                sql = "SELECT * FROM read_trending_record(%s);"
                params = (int(identifier),)
            else:
                return pd.DataFrame()
        except ValueError:
            # Raised if an alphabetic string is passed for an integer ID (e.g. 'abc' for Category)
            return pd.DataFrame()

        conn = cls.get_pg_connection()
        try:
            return pd.read_sql(sql, conn, params=params)
        finally:
            conn.close()

    @classmethod
    def delete_record(cls, table, identifier):
        identifier = str(identifier).strip()
        if not identifier:
            return False

        try:
            if table == "Category":
                sql = "SELECT delete_category(%s);"
                params = (int(identifier),)
            elif table == "Channel":
                sql = "SELECT delete_channel(%s);"
                params = (int(identifier),)
            elif table == "Country":
                sql = "SELECT delete_country(%s::text);"
                params = (identifier.upper(),)
            elif table == "Video":
                sql = "SELECT delete_video(%s::text);"
                params = (identifier,)
            elif table == "Channel Stats":
                sql = "SELECT delete_channel_stats(%s);"
                params = (int(identifier),)
            elif table == "Trending Record":
                sql = "SELECT delete_trending_record(%s);"
                params = (int(identifier),)
            else:
                return False
        except ValueError:
            return False

        return cls._execute_transaction(sql, params)

    # ------------------------------------------------------------------
    # NON-RELATIONAL CRUD OPERATIONS (MONGODB)
    # ------------------------------------------------------------------
    @classmethod
    def insert_mongo_revenue(cls, document_dict):
        col = cls.get_mongo_collection("revenue")
        if col.count_documents({"video_id": document_dict.get("video_id")}) > 0:
            raise ValueError(f"Video ID '{document_dict.get('video_id')}' already exists in MongoDB.")
        return col.insert_one(document_dict).acknowledged

    @classmethod
    def read_mongo_revenue(cls, video_id=None):
        col = cls.get_mongo_collection("revenue")
        query = {"video_id": video_id} if video_id else {}
        cursor = col.find(query, {"_id": 0}).limit(100)
        return pd.DataFrame(list(cursor))

    @classmethod
    def delete_mongo_revenue(cls, video_id):
        col = cls.get_mongo_collection("revenue")
        res = col.delete_one({"video_id": video_id})
        return res.deleted_count > 0

    # ------------------------------------------------------------------
    # NON-RELATIONAL ANALYTICS (MONGODB)
    # ------------------------------------------------------------------
    @classmethod
    def aggregate_revenue_by_country(cls):
        """Unwinds nested country revenue and sums total estimated gross revenue."""
        col = cls.get_mongo_collection("revenue")
        pipeline = [
            {"$unwind": "$revenue_by_country"},
            {"$group": {
                "_id": "$revenue_by_country.country_code",
                "total_estimated_revenue": {"$sum": "$revenue_by_country.estimated_gross_usd"}
            }},
            {"$sort": {"total_estimated_revenue": -1}}
        ]
        results = list(col.aggregate(pipeline))
        df = pd.DataFrame(results)
        if not df.empty and "_id" in df.columns:
            df = df.rename(columns={"_id": "country_code"})
        return df

    @classmethod
    def aggregate_category_breakdown(cls):
        """Counts the total videos per category_id in MongoDB."""
        col = cls.get_mongo_collection("revenue")
        pipeline = [
            {"$group": {
                "_id": "$category_id",
                "total_videos": {"$sum": 1}
            }},
            {"$sort": {"total_videos": -1}}
        ]
        results = list(col.aggregate(pipeline))
        df = pd.DataFrame(results)
        if not df.empty:
            if "_id" in df.columns:
                df = df.rename(columns={"_id": "category_id"})
            # Ensure total_videos column is explicitly integer
            if "total_videos" in df.columns:
                df["total_videos"] = df["total_videos"].fillna(0).astype(int)
        return df
    
    @classmethod
    def filter_by_creator_tier(cls, tier="large", limit=None):
        col = cls.get_mongo_collection("revenue")
        pipeline = [
            {"$match": {"creator_tier": {"$regex": f"^{tier.strip()}$", "$options": "i"}}}
        ]
        if limit:
            pipeline.append({"$limit": limit})

        pipeline.extend([
            {"$project": {
                "_id": 0,
                "video_id": 1,
                "channel_id": 1,
                "creator_tier": 1,
                "category_id": 1,
                "monetization": 1,
                "sponsorships": 1,
                "revenue_by_country": 1,
                # Platform ad revenue
                "ad_revenue": {
                    "$reduce": {
                        "input": {"$ifNull": ["$revenue_by_country", []]},
                        "initialValue": 0.0,
                        "in": {"$add": ["$$value", {"$ifNull": ["$$this.estimated_gross_usd", 0.0]}]}
                    }
                },
                # Direct sponsorship revenue
                "sponsorship_revenue": {"$ifNull": ["$revenue_summary.total_sponsorship_usd", 0.0]},
                # Total combined revenue
                "total_video_revenue": {
                    "$add": [
                        {
                            "$reduce": {
                                "input": {"$ifNull": ["$revenue_by_country", []]},
                                "initialValue": 0.0,
                                "in": {"$add": ["$$value", {"$ifNull": ["$$this.estimated_gross_usd", 0.0]}]}
                            }
                        },
                        {"$ifNull": ["$revenue_summary.total_sponsorship_usd", 0.0]}
                    ]
                }
            }},
            {"$sort": {"total_video_revenue": -1}}
        ])
        results = list(col.aggregate(pipeline))
        return pd.DataFrame(results)

    @classmethod
    def get_video_stats_by_id(cls, video_id):
        """Fetches full monetization, ad format, and revenue stats for a single video."""
        col = cls.get_mongo_collection("revenue")
        doc = col.find_one({"video_id": str(video_id).strip()}, {"_id": 0})
        return doc if doc else {}

    @classmethod
    def compare_creator_tiers(cls):
        """
        Aggregates financial and monetization metrics across tiers:
        calculates total revenue, average revenue per video, average playback rate,
        and total videos to verify if higher tiers generate more revenue.
        """
        col = cls.get_mongo_collection("revenue")
        pipeline = [
            # 1. Compute total revenue and playback rate for each individual video document
            {"$project": {
                "creator_tier": {"$toLower": "$creator_tier"},
                "playback_rate": "$ads.monetized_playback_rate",
                "video_revenue": {
                    "$reduce": {
                        "input": {"$ifNull": ["$revenue_by_country", []]},
                        "initialValue": 0.0,
                        "in": {"$add": ["$$value", {"$ifNull": ["$$this.estimated_gross_usd", 0.0]}]}
                    }
                }
            }},
            # 2. Group by creator tier and calculate financial comparisons
            {"$group": {
                "_id": "$creator_tier",
                "total_videos": {"$sum": 1},
                "total_tier_revenue": {"$sum": "$video_revenue"},
                "avg_revenue_per_video": {"$avg": "$video_revenue"},
                "max_single_video_revenue": {"$max": "$video_revenue"},
                "avg_playback_rate": {"$avg": "$playback_rate"}
            }},
            # 3. Sort from highest grossing to lowest
            {"$sort": {"total_tier_revenue": -1}}
        ]
        results = list(col.aggregate(pipeline))
        df = pd.DataFrame(results)
        if not df.empty and "_id" in df.columns:
            df = df.rename(columns={"_id": "creator_tier"})
        return df


    @classmethod
    def get_metadata_lookup_maps(cls):
        """
        Fetches title/name mappings from PostgreSQL:
        - video_id -> video title
        - channel_id -> channel_title
        - category_id -> category_name
        """
        conn = cls.get_pg_connection()
        try:
            # 1. Video ID -> Title
            videos_df = pd.read_sql("SELECT video_id, title FROM Video;", conn)
            video_map = dict(zip(videos_df["video_id"], videos_df["title"]))

            # 2. Channel ID -> Channel Title
            channels_df = pd.read_sql("SELECT channel_id, channel_title FROM Channel;", conn)
            channel_map = dict(zip(channels_df["channel_id"], channels_df["channel_title"]))

            # 3. Category ID -> Category Name
            categories_df = pd.read_sql("SELECT category_id, category_name FROM Category;", conn)
            category_map = dict(zip(categories_df["category_id"], categories_df["category_name"]))

            return video_map, channel_map, category_map
        finally:
            conn.close()