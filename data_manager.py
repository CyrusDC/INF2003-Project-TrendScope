import os
from contextlib import contextmanager

import pandas as pd
import psycopg2
import pymongo
from dotenv import load_dotenv

load_dotenv()


# One upsert call per table. Single inserts and bulk uploads share these, so the
# parameter names are the column names that the validators in LogicManager return.
UPSERT_SQL = {
    "Category": """
        SELECT public.upsert_category(%(category_id)s::integer, %(category_name)s::text);
    """,
    "Channel": """
        SELECT public.upsert_channel(%(channel_id)s::integer, %(channel_title)s::text);
    """,
    "Country": """
        SELECT public.upsert_country(%(country_code)s::text, %(country_name)s::text);
    """,
    "Video": """
        SELECT public.upsert_video(
            %(video_id)s::text, %(title)s::text, %(publish_time)s::timestamptz,
            %(tag_count)s::integer, %(channel_id)s::integer, %(category_id)s::integer);
    """,
    "Channel Stats": """
        SELECT public.upsert_channel_stats(
            %(channel_id)s::integer, %(country_code)s::text, %(subscriber)s::bigint,
            %(video_views)s::bigint, %(uploads)s::integer, %(created_date)s::date,
            %(video_views_last_30_days)s::bigint, %(subscribers_last_30_days)s::bigint);
    """,
    "Trending Record": """
        SELECT public.upsert_trending_record(
            %(record_id)s::integer, %(video_id)s::text, %(country_code)s::text,
            %(trending_date)s::date, %(views)s::bigint, %(likes)s::bigint,
            %(dislikes)s::bigint, %(comment_count)s::bigint);
    """,
}

READ_SQL = {
    "Category": "SELECT * FROM read_category(%s);",
    "Channel": "SELECT * FROM read_channel(%s);",
    "Country": "SELECT * FROM read_country(%s::text);",
    "Video": "SELECT * FROM read_video(%s::text);",
    "Channel Stats": "SELECT * FROM read_channel_stats(%s);",
    "Trending Record": "SELECT * FROM read_trending_record(%s);",
}

# delete_video and delete_channel remove their dependent rows inside the function.
# Category and Country have no cascade, so the foreign keys block a delete that is still in use.
DELETE_SQL = {
    "Category": "SELECT public.delete_category(%s);",
    "Channel": "SELECT public.delete_channel(%s);",
    "Country": "SELECT public.delete_country(%s::text);",
    "Video": "SELECT public.delete_video(%s::text);",
    "Trending Record": "SELECT public.delete_trending_record(%s);",
}

ANALYTICAL_VIEWS = {
    "category_views": "SELECT * FROM get_category_views();",
    "channel_performance": "SELECT * FROM get_channel_performance();",
    "video_reach": "SELECT * FROM get_video_reach();",
    "reaction_ratios": "SELECT * FROM get_video_reaction_ratios();",
}

# The SQL functions return snake_case names; these are the headers shown on the dashboard.
COLUMN_LABELS = {
    "category_name": "Category Name",
    "channel_title": "Channel Name",
    "video_title": "Video Title",
    "video_count": "Video Count",
    "total_views": "Total Views",
    "avg_views_per_video": "Avg Views / Video",
    "share_of_all_views_pct": "Share of Views (%)",
    "top_video_views": "Top Video Views",
    "countries": "Countries Reached",
    "country_list": "Country List",
    "trending_records": "Trending Records",
    "views": "Views",
    "likes": "Likes",
    "dislikes": "Dislikes",
    "dislike_percentage": "Dislike Rate (%)",
    "likes_per_dislike": "Likes Per Dislike",
}

# A video's ad revenue is the sum of its per-country estimates. Sponsorship is stored
# once in the summary and is missing for videos without a sponsor.
AD_REVENUE = {"$sum": "$revenue_by_country.estimated_gross_usd"}
SPONSORSHIP = {"$ifNull": ["$revenue_summary.total_sponsorship_usd", 0]}


class DataManager:
    """All database access: PostgreSQL through psycopg2 and MongoDB through pymongo."""

    _mongo_client = None

    @staticmethod
    def get_pg_connection():
        return psycopg2.connect(
            host=os.getenv("PG_HOST"),
            port=os.getenv("PG_PORT"),
            dbname=os.getenv("PG_DBNAME"),
            user=os.getenv("PG_USER"),
            password=os.getenv("PG_PASSWORD"),
        )

    @classmethod
    def get_mongo_collection(cls, collection_name="revenue"):
        # MongoClient keeps its own connection pool, so we create it once and reuse it
        # instead of doing a new handshake with Atlas on every query.
        if cls._mongo_client is None:
            cls._mongo_client = pymongo.MongoClient(os.getenv("MONGO_URI"))
        db = cls._mongo_client[os.getenv("MONGO_DB", "youtube_nosql")]
        return db[collection_name]

    @classmethod
    @contextmanager
    def _pg_cursor(cls, commit=False):
        """Hand out a cursor and always close the connection afterwards.

        With commit=True everything done inside the block is one transaction:
        it is committed at the end, or rolled back if anything raises.
        """
        conn = cls.get_pg_connection()
        try:
            with conn.cursor() as cur:
                yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @classmethod
    def _query_df(cls, sql, params=None):
        with cls._pg_cursor() as cur:
            cur.execute(sql, params)
            columns = [col[0] for col in cur.description]
            # coerce_float turns NUMERIC results into floats, same as pd.read_sql does
            return pd.DataFrame.from_records(cur.fetchall(), columns=columns, coerce_float=True)

    # PostgreSQL: dashboard and search

    @classmethod
    def fetch_analytical_view(cls, view_name):
        if view_name not in ANALYTICAL_VIEWS:
            raise ValueError("Invalid view identifier.")

        df = cls._query_df(ANALYTICAL_VIEWS[view_name])
        # Viewers only need names and titles, not the internal IDs
        df = df.drop(columns=["channel_id", "video_id"], errors="ignore")
        return df.rename(columns=COLUMN_LABELS)

    @classmethod
    def get_filter_dropdown_options(cls):
        with cls._pg_cursor() as cur:
            cur.execute("SELECT category_id, category_name FROM public.get_category_options();")
            categories = [{"category_id": cid, "category_name": name} for cid, name in cur.fetchall()]
            cur.execute("SELECT country_code, country_name FROM public.get_country_options();")
            countries = [{"country_code": code, "country_name": name} for code, name in cur.fetchall()]
        return categories, countries

    @classmethod
    def explore_trending_videos(cls, keyword=None, country=None, category_id=None,
                                start_date=None, end_date=None):
        sql = """
            SELECT *
            FROM public.explore_trending_videos(%s::text, %s::text, %s::integer, %s::date, %s::date)
        """
        return cls._query_df(sql, (keyword, country, category_id, start_date, end_date))

    @classmethod
    def get_metadata_lookup_maps(cls):
        """Return id -> name dicts for videos, channels and categories.

        MongoDB only stores the IDs, so these are used to show readable names
        next to the revenue documents.
        """
        with cls._pg_cursor() as cur:
            cur.execute("SELECT video_id, title FROM video;")
            video_map = dict(cur.fetchall())
            cur.execute("SELECT channel_id, channel_title FROM channel;")
            channel_map = dict(cur.fetchall())
            cur.execute("SELECT category_id, category_name FROM category;")
            category_map = dict(cur.fetchall())
        return video_map, channel_map, category_map

    # PostgreSQL: insert, read, delete

    @classmethod
    def upsert_postgres(cls, table, records):
        """Upsert a list of validated records and return how many were written.

        The whole list is one transaction, so a bad row in a bulk upload
        rolls back every row before it as well.
        """
        if table not in UPSERT_SQL:
            raise ValueError(f"Bulk import not supported for {table}")

        with cls._pg_cursor(commit=True) as cur:
            for record in records:
                cur.execute(UPSERT_SQL[table], record)
        return len(records)

    @classmethod
    def read_record(cls, table, key):
        return cls._query_df(READ_SQL[table], (key,))

    @classmethod
    def delete_record(cls, table, key):
        """Return True if a row was deleted, False if the key did not exist."""
        with cls._pg_cursor(commit=True) as cur:
            cur.execute(DELETE_SQL[table], (key,))
            return cur.fetchone()[0]

    # MongoDB: insert and delete

    @classmethod
    def upsert_revenue(cls, documents):
        """Upsert revenue documents by video_id and return how many were written."""
        operations = [
            pymongo.UpdateOne({"video_id": doc["video_id"]}, {"$set": doc}, upsert=True)
            for doc in documents
        ]
        result = cls.get_mongo_collection().bulk_write(operations)
        # matched_count already includes the modified documents, so only new ones are added on top
        return result.upserted_count + result.matched_count

    @classmethod
    def delete_revenue(cls, video_id):
        result = cls.get_mongo_collection().delete_one({"video_id": video_id})
        return result.deleted_count > 0

    # MongoDB: revenue analytics

    @classmethod
    def aggregate_revenue_by_country(cls):
        pipeline = [
            {"$unwind": "$revenue_by_country"},
            {"$group": {
                "_id": "$revenue_by_country.country_code",
                "total_estimated_revenue": {"$sum": "$revenue_by_country.estimated_gross_usd"},
            }},
            {"$sort": {"total_estimated_revenue": -1}},
            {"$project": {"_id": 0, "country_code": "$_id", "total_estimated_revenue": 1}},
        ]
        return list(cls.get_mongo_collection().aggregate(pipeline))

    @classmethod
    def aggregate_category_breakdown(cls):
        pipeline = [
            {"$group": {"_id": "$category_id", "total_videos": {"$sum": 1}}},
            {"$sort": {"total_videos": -1}},
            {"$project": {"_id": 0, "category_id": "$_id", "total_videos": 1}},
        ]
        return list(cls.get_mongo_collection().aggregate(pipeline))

    @classmethod
    def filter_by_creator_tier(cls, tier):
        pipeline = [
            # Case-insensitive so older documents saved as "Large" still match.
            # The tier comes from a fixed list in LogicManager, so it is safe inside a regex.
            {"$match": {"creator_tier": {"$regex": f"^{tier}$", "$options": "i"}}},
            {"$project": {
                "_id": 0,
                "video_id": 1,
                "channel_id": 1,
                "creator_tier": 1,
                "category_id": 1,
                "monetization": 1,
                "sponsorships": 1,
                "revenue_by_country": 1,
                "ad_revenue": AD_REVENUE,
                "sponsorship_revenue": SPONSORSHIP,
                "total_video_revenue": {"$add": [AD_REVENUE, SPONSORSHIP]},
            }},
            {"$sort": {"total_video_revenue": -1}},
        ]
        return list(cls.get_mongo_collection().aggregate(pipeline))

    @classmethod
    def compare_creator_tiers(cls):
        pipeline = [
            {"$project": {
                "creator_tier": {"$toLower": "$creator_tier"},
                "playback_rate": "$ads.monetized_playback_rate",
                "video_revenue": AD_REVENUE,
            }},
            {"$group": {
                "_id": "$creator_tier",
                "total_videos": {"$sum": 1},
                "total_tier_revenue": {"$sum": "$video_revenue"},
                "avg_revenue_per_video": {"$avg": "$video_revenue"},
                "max_single_video_revenue": {"$max": "$video_revenue"},
                # videos without ads have no playback rate and are skipped by $avg
                "avg_playback_rate": {"$avg": "$playback_rate"},
            }},
            {"$sort": {"total_tier_revenue": -1}},
            {"$project": {
                "_id": 0,
                "creator_tier": "$_id",
                "total_videos": 1,
                "total_tier_revenue": 1,
                "avg_revenue_per_video": 1,
                "max_single_video_revenue": 1,
                "avg_playback_rate": 1,
            }},
        ]
        return list(cls.get_mongo_collection().aggregate(pipeline))

    @classmethod
    def get_copyright_claims_summary(cls, policy=None, outcome=None):
        """Group copyright claims by claimant, optionally filtered by policy and dispute outcome."""
        pipeline = [
            {"$match": {"copyright_claims": {"$exists": True, "$ne": []}}},
            # claims are a nested array, so each claim becomes its own row first
            {"$unwind": "$copyright_claims"},
        ]

        filters = {}
        if policy:
            filters["copyright_claims.policy"] = policy
        if outcome:
            # only disputed claims have a "dispute" sub-document
            filters["copyright_claims.dispute.outcome"] = outcome
        if filters:
            pipeline.append({"$match": filters})

        pipeline += [
            {"$group": {
                "_id": "$copyright_claims.claimant",
                "total_claims": {"$sum": 1},
                "policies": {"$addToSet": "$copyright_claims.policy"},
                "dispute_outcomes": {"$addToSet": "$copyright_claims.dispute.outcome"},
                "claimed_videos": {"$addToSet": "$video_id"},
            }},
            {"$project": {
                "_id": 0,
                "claimant": "$_id",
                "total_claims": 1,
                "policies": 1,
                "dispute_outcomes": 1,
                "video_count": {"$size": "$claimed_videos"},
            }},
            {"$sort": {"total_claims": -1}},
        ]
        return list(cls.get_mongo_collection().aggregate(pipeline))

    # MongoDB: single video lookups

    @classmethod
    def get_video_stats_by_id(cls, video_id):
        doc = cls.get_mongo_collection().find_one({"video_id": video_id}, {"_id": 0})
        return doc or {}

    @classmethod
    def get_video_comparison_item(cls, video_id):
        """Revenue totals for one video, or None if it has no revenue document."""
        pipeline = [
            {"$match": {"video_id": video_id}},
            {"$project": {
                "_id": 0,
                "video_id": 1,
                "channel_id": 1,
                "category_id": 1,
                "creator_tier": {"$toLower": "$creator_tier"},
                "playback_rate": "$ads.monetized_playback_rate",
                "ad_gross_usd": AD_REVENUE,
                "sponsorship_usd": SPONSORSHIP,
                "total_revenue": {"$add": [AD_REVENUE, SPONSORSHIP]},
            }},
        ]
        docs = list(cls.get_mongo_collection().aggregate(pipeline))
        return docs[0] if docs else None

    @classmethod
    def list_revenue_video_ids(cls, limit=500):
        cursor = cls.get_mongo_collection().find(
            {}, {"_id": 0, "video_id": 1, "creator_tier": 1}
        ).limit(limit)
        return [
            {"video_id": doc["video_id"], "creator_tier": (doc.get("creator_tier") or "").lower()}
            for doc in cursor
            if "video_id" in doc
        ]
