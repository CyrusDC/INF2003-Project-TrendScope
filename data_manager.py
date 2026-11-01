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