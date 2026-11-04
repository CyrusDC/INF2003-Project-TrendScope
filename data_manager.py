import os
import psycopg2
import pymongo
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

class DataManager:
    """Handles raw database connections, queries, transactions, and rollbacks."""

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
    # ANALYTICAL VIEWS & SEARCH
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

        rename_mappings = {
            "category_views": {
                "category_name": "Category Name",
                "video_count": "Video Count",
                "total_views": "Total Views",
                "avg_views_per_video": "Avg Views / Video",
                "share_of_all_views_pct": "Share of Views (%)"
            },
            "channel_performance": {
                "channel_id": "Channel ID",
                "channel_name": "Channel Name",
                "video_count": "Video Count",
                "total_views": "Total Views",
                "avg_views_per_video": "Avg Views / Video",
                "top_video_views": "Top Video Views"
            },
            "video_reach": {
                "video_id": "Video ID",
                "video_title": "Video Title",
                "countries": "Countries Reached",
                "country_list": "Country List",
                "trending_records": "Trending Records"
            },
            "reaction_ratios": {
                "video_id": "Video ID",
                "video_title": "Video Title",
                "views": "Views",
                "Views": "Views",
                "likes": "Likes",
                "Likes": "Likes",
                "dislikes": "Dislikes",
                "Dislikes": "Dislikes",
                "dislike_percentage": "Dislike Rate (%)",
                "likes_per_dislike": "Likes Per Dislike"
            }
        }
        
        conn = cls.get_pg_connection()
        try:
            df = pd.read_sql(valid_views[view_name], conn)
            if not df.empty and view_name in rename_mappings:
                df = df.rename(columns=rename_mappings[view_name])
            return df
        finally:
            conn.close()

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
    # INDIVIDUAL RELATIONAL CRUD (UPSERT BEHAVIOR)
    # ------------------------------------------------------------------
    @classmethod
    def insert_category(cls, cat_id, cat_name):
        sql = """
            INSERT INTO Category (category_id, category_name)
            VALUES (%s, %s::text)
            ON CONFLICT (category_id) DO UPDATE SET category_name = EXCLUDED.category_name;
        """
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, (cat_id, cat_name))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @classmethod
    def insert_channel(cls, chan_id, chan_title):
        sql = """
            INSERT INTO Channel (channel_id, channel_title)
            VALUES (%s, %s::text)
            ON CONFLICT (channel_id) DO UPDATE SET channel_title = EXCLUDED.channel_title;
        """
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, (chan_id, chan_title))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @classmethod
    def insert_country(cls, code, name, pop):
        sql = """
            INSERT INTO Country (country_code, country_name, population)
            VALUES (%s::text, %s::text, %s)
            ON CONFLICT (country_code) DO UPDATE 
            SET country_name = EXCLUDED.country_name, population = EXCLUDED.population;
        """
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, (code.upper(), name, pop))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @classmethod
    def insert_video(cls, video_id, title, pub_dt, tag_count, chan_id, cat_id):
        sql = """
            INSERT INTO Video (video_id, title, publish_time, tag_count, channel_id, category_id)
            VALUES (%s::text, %s::text, %s, %s, %s, %s)
            ON CONFLICT (video_id) DO UPDATE SET
                title = EXCLUDED.title,
                publish_time = EXCLUDED.publish_time,
                tag_count = EXCLUDED.tag_count,
                channel_id = EXCLUDED.channel_id,
                category_id = EXCLUDED.category_id;
        """
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, (video_id, title, pub_dt, tag_count, chan_id, cat_id))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @classmethod
    def insert_channel_stats(cls, chan_id, c_code, rank, sub, views, uploads, dt_val, v30, s30):
        # Assumes primary key or unique constraint on (channel_id, country_code, stats_date)
        sql = """
            INSERT INTO Channel_Stats (channel_id, country_code, rank, subscribers, views, total_uploads, stats_date, views_30, subs_30)
            VALUES (%s, %s::text, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (channel_id) DO UPDATE SET
                country_code = EXCLUDED.country_code,
                rank = EXCLUDED.rank,
                subscribers = EXCLUDED.subscribers,
                views = EXCLUDED.views,
                total_uploads = EXCLUDED.total_uploads,
                stats_date = EXCLUDED.stats_date,
                views_30 = EXCLUDED.views_30,
                subs_30 = EXCLUDED.subs_30;
        """
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, (chan_id, c_code.upper(), rank, sub, views, uploads, dt_val, v30, s30))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @classmethod
    def insert_trending_record(cls, rec_id, vid_id, c_code, t_date, views, likes, dislikes, comments):
        sql = """
            INSERT INTO Trending_Record (record_id, video_id, country_code, trending_date, views, likes, dislikes, comment_count)
            VALUES (%s, %s::text, %s::text, %s, %s, %s, %s, %s)
            ON CONFLICT (record_id) DO UPDATE SET
                video_id = EXCLUDED.video_id,
                country_code = EXCLUDED.country_code,
                trending_date = EXCLUDED.trending_date,
                views = EXCLUDED.views,
                likes = EXCLUDED.likes,
                dislikes = EXCLUDED.dislikes,
                comment_count = EXCLUDED.comment_count;
        """
        conn = cls.get_pg_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql, (rec_id, vid_id, c_code.upper(), t_date, views, likes, dislikes, comments))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    # ------------------------------------------------------------------
    # BULK UPSERT OPERATIONS (POSTGRESQL & MONGODB)
    # ------------------------------------------------------------------
    @classmethod
    def bulk_upsert_postgres(cls, table, records):
        """
        Bulk upsert list of dicts into PostgreSQL with ON CONFLICT DO UPDATE.
        Overwrites any existing records that share the same primary key.
        """
        if not records:
            return 0

        conn = cls.get_pg_connection()
        cur = conn.cursor()

        queries = {
            "Category": """
                INSERT INTO Category (category_id, category_name)
                VALUES (%(cat_id)s, %(cat_name)s)
                ON CONFLICT (category_id) DO UPDATE SET category_name = EXCLUDED.category_name;
            """,
            "Channel": """
                INSERT INTO Channel (channel_id, channel_title)
                VALUES (%(chan_id)s, %(chan_title)s)
                ON CONFLICT (channel_id) DO UPDATE SET channel_title = EXCLUDED.channel_title;
            """,
            "Country": """
                INSERT INTO Country (country_code, country_name, population)
                VALUES (%(code)s, %(name)s, %(pop)s)
                ON CONFLICT (country_code) DO UPDATE 
                SET country_name = EXCLUDED.country_name, population = EXCLUDED.population;
            """,
            "Video": """
                INSERT INTO Video (video_id, title, publish_time, tag_count, channel_id, category_id)
                VALUES (%(video_id)s, %(title)s, %(pub_dt)s, %(tag_count)s, %(channel_id)s, %(category_id)s)
                ON CONFLICT (video_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    publish_time = EXCLUDED.publish_time,
                    tag_count = EXCLUDED.tag_count,
                    channel_id = EXCLUDED.channel_id,
                    category_id = EXCLUDED.category_id;
            """,
            "Channel Stats": """
                INSERT INTO Channel_Stats (channel_id, country_code, rank, subscribers, views, total_uploads, stats_date, views_30, subs_30)
                VALUES (%(chan_id)s, %(c_code)s, %(rank)s, %(sub)s, %(views)s, %(uploads)s, %(dt_val)s, %(v30)s, %(s30)s)
                ON CONFLICT (channel_id) DO UPDATE SET
                    country_code = EXCLUDED.country_code,
                    rank = EXCLUDED.rank,
                    subscribers = EXCLUDED.subscribers,
                    views = EXCLUDED.views,
                    total_uploads = EXCLUDED.total_uploads,
                    stats_date = EXCLUDED.stats_date,
                    views_30 = EXCLUDED.views_30,
                    subs_30 = EXCLUDED.subs_30;
            """,
            "Trending Record": """
                INSERT INTO Trending_Record (record_id, video_id, country_code, trending_date, views, likes, dislikes, comment_count)
                VALUES (%(rec_id)s, %(vid_id)s, %(c_code)s, %(t_date)s, %(views)s, %(likes)s, %(dislikes)s, %(comments)s)
                ON CONFLICT (record_id) DO UPDATE SET
                    video_id = EXCLUDED.video_id,
                    country_code = EXCLUDED.country_code,
                    trending_date = EXCLUDED.trending_date,
                    views = EXCLUDED.views,
                    likes = EXCLUDED.likes,
                    dislikes = EXCLUDED.dislikes,
                    comment_count = EXCLUDED.comment_count;
            """
        }

        query = queries.get(table)
        if not query:
            raise ValueError(f"Bulk insert not supported for {table}")

        try:
            for rec in records:
                cur.execute(query, rec)
            conn.commit()
            return len(records)
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @classmethod
    def bulk_upsert_mongo_revenue(cls, documents):
        """
        Bulk upsert list of dicts into MongoDB using UpdateOne(..., upsert=True).
        Overwrites any document with the same video_id.
        """
        if not documents:
            return 0
        col = cls.get_mongo_collection("revenue")
        ops = [
            pymongo.UpdateOne(
                {"video_id": doc.get("video_id")},
                {"$set": doc},
                upsert=True
            )
            for doc in documents
        ]
        res = col.bulk_write(ops)
        return (res.upserted_count or 0) + (res.modified_count or 0) + (res.matched_count or 0)

    # ------------------------------------------------------------------
    # MONGO CRUD (SINGLE)
    # ------------------------------------------------------------------
    @classmethod
    def insert_mongo_revenue(cls, document_dict):
        """Single upsert into MongoDB based on video_id."""
        col = cls.get_mongo_collection("revenue")
        col.update_one(
            {"video_id": document_dict.get("video_id")},
            {"$set": document_dict},
            upsert=True
        )
        return True

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
    # READ & DELETE HELPERS
    # ------------------------------------------------------------------
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
    # ANALYTICS & LOOKUP
    # ------------------------------------------------------------------
    @classmethod
    def aggregate_revenue_by_country(cls):
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
                "ad_revenue": {
                    "$reduce": {
                        "input": {"$ifNull": ["$revenue_by_country", []]},
                        "initialValue": 0.0,
                        "in": {"$add": ["$$value", {"$ifNull": ["$$this.estimated_gross_usd", 0.0]}]}
                    }
                },
                "sponsorship_revenue": {"$ifNull": ["$revenue_summary.total_sponsorship_usd", 0.0]},
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
        col = cls.get_mongo_collection("revenue")
        doc = col.find_one({"video_id": str(video_id).strip()}, {"_id": 0})
        return doc if doc else {}

    @classmethod
    def compare_creator_tiers(cls):
        col = cls.get_mongo_collection("revenue")
        pipeline = [
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
            {"$group": {
                "_id": "$creator_tier",
                "total_videos": {"$sum": 1},
                "total_tier_revenue": {"$sum": "$video_revenue"},
                "avg_revenue_per_video": {"$avg": "$video_revenue"},
                "max_single_video_revenue": {"$max": "$video_revenue"},
                "avg_playback_rate": {"$avg": "$playback_rate"}
            }},
            {"$sort": {"total_tier_revenue": -1}}
        ]
        results = list(col.aggregate(pipeline))
        df = pd.DataFrame(results)
        if not df.empty and "_id" in df.columns:
            df = df.rename(columns={"_id": "creator_tier"})
        return df

    @classmethod
    def get_metadata_lookup_maps(cls):
        conn = cls.get_pg_connection()
        try:
            videos_df = pd.read_sql("SELECT video_id, title FROM Video;", conn)
            video_map = dict(zip(videos_df["video_id"], videos_df["title"]))

            channels_df = pd.read_sql("SELECT channel_id, channel_title FROM Channel;", conn)
            channel_map = dict(zip(channels_df["channel_id"], channels_df["channel_title"]))

            categories_df = pd.read_sql("SELECT category_id, category_name FROM Category;", conn)
            category_map = dict(zip(categories_df["category_id"], categories_df["category_name"]))

            return video_map, channel_map, category_map
        finally:
            conn.close()
            
    @classmethod
    def search_records_by_name(cls, entity_type, term):
        """
        Viewer-facing search: Queries entities by human-readable names/titles
        using case-insensitive partial matching (ILIKE).
        """
        term = f"%{str(term).strip()}%"
        conn = cls.get_pg_connection()

        queries = {
            "Category": """
                SELECT category_id, category_name 
                FROM Category 
                WHERE category_name ILIKE %s 
                ORDER BY category_name LIMIT 50;
            """,
            "Channel": """
                SELECT channel_id, channel_title 
                FROM Channel 
                WHERE channel_title ILIKE %s 
                ORDER BY channel_title LIMIT 50;
            """,
            "Country": """
                SELECT country_code, country_name, population 
                FROM Country 
                WHERE country_name ILIKE %s OR country_code ILIKE %s 
                ORDER BY country_name LIMIT 50;
            """,
            "Video": """
                SELECT v.video_id, v.title, v.publish_time, v.tag_count,
                       c.channel_title, cat.category_name
                FROM Video v
                LEFT JOIN Channel c ON v.channel_id = c.channel_id
                LEFT JOIN Category cat ON v.category_id = cat.category_id
                WHERE v.title ILIKE %s
                ORDER BY v.publish_time DESC LIMIT 50;
            """
        }

        # Mapping raw database columns to dashboard titles
        rename_mappings = {
            "Category": {
                "category_id": "Category ID",
                "category_name": "Category Name"
            },
            "Channel": {
                "channel_id": "Channel ID",
                "channel_title": "Channel Title"
            },
            "Country": {
                "country_code": "Country Code",
                "country_name": "Country Name",
                "population": "Population"
            },
            "Video": {
                "video_id": "Video ID",
                "title": "Video Title",
                "publish_time": "Publish Time",
                "tag_count": "Tag Count",
                "channel_title": "Channel Name",
                "category_name": "Category"
            }
        }

        sql = queries.get(entity_type)
        if not sql:
            conn.close()
            return pd.DataFrame()

        try:
            params = (term, term) if entity_type == "Country" else (term,)
            df = pd.read_sql(sql, conn, params=params)

            # Apply friendly header names
            if not df.empty and entity_type in rename_mappings:
                df = df.rename(columns=rename_mappings[entity_type])

            return df
        finally:
            conn.close()
    
    @classmethod
    def get_copyright_claims_summary(cls, policy_filter=None, outcome_filter=None):
        """
        Unwinds the nested copyright_claims array, filters by policy/outcome,
        and aggregates claims grouped by claimant.
        Satisfies Proposal 4.2: $unwind, $match, and $group.
        """
        col = cls.get_mongo_collection("revenue")

        pipeline = [
            # 1. Only include documents with copyright_claims
            {"$match": {"copyright_claims": {"$exists": True, "$ne": []}}},
            # 2. Flatten the nested array of claims
            {"$unwind": "$copyright_claims"}
        ]

        # 3. Dynamic $match for policy and dispute outcome filters
        match_conditions = {}
        if policy_filter and policy_filter != "all":
            match_conditions["copyright_claims.policy"] = policy_filter
        if outcome_filter and outcome_filter != "all":
            match_conditions["copyright_claims.dispute_outcome"] = outcome_filter

        if match_conditions:
            pipeline.append({"$match": match_conditions})

        # 4. Group by claimant to aggregate total disputes and claims
        pipeline.extend([
            {"$group": {
                "_id": "$copyright_claims.claimant",
                "total_claims": {"$sum": 1},
                "policies": {"$addToSet": "$copyright_claims.policy"},
                "dispute_outcomes": {"$addToSet": "$copyright_claims.dispute_outcome"},
                "claimed_videos": {"$addToSet": "$video_id"}
            }},
            {"$project": {
                "_id": 0,
                "claimant": "$_id",
                "total_claims": 1,
                "policies": 1,
                "dispute_outcomes": 1,
                "video_count": {"$size": "$claimed_videos"}
            }},
            {"$sort": {"total_claims": -1}}
        ])

        results = list(col.aggregate(pipeline))
        return pd.DataFrame(results)
    
    @classmethod
    def get_filter_dropdown_options(cls):
        """Fetches distinct categories and countries to populate filter dropdowns."""
        conn = cls.get_pg_connection()
        try:
            cats = pd.read_sql("SELECT category_id, category_name FROM Category ORDER BY category_name;", conn)
            countries = pd.read_sql("SELECT country_code, country_name FROM Country ORDER BY country_name;", conn)
            return cats.to_dict(orient="records"), countries.to_dict(orient="records")
        finally:
            conn.close()

    @classmethod
    def explore_trending_videos(cls, keyword=None, country=None, category_id=None, start_date=None, end_date=None):
        """
        Multi-table join (Video, Category, Channel, Trending_Record) with indexed range queries.
        Satisfies Proposal 4.1: Trending Explorer.
        """
        conditions = ["1=1"]
        params = []

        if keyword:
            conditions.append("v.title ILIKE %s")
            params.append(f"%{keyword.strip()}%")

        if country and country != "all":
            conditions.append("tr.country_code = %s")
            params.append(country.strip().upper())

        if category_id and category_id != "all":
            conditions.append("v.category_id = %s")
            params.append(int(category_id))

        if start_date:
            conditions.append("tr.trending_date >= %s")
            params.append(start_date)

        if end_date:
            conditions.append("tr.trending_date <= %s")
            params.append(end_date)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT 
                v.video_id,
                v.title,
                c.channel_title,
                cat.category_name,
                tr.country_code,
                tr.trending_date,
                tr.views,
                tr.likes,
                tr.dislikes
            FROM Trending_Record tr
            JOIN Video v ON tr.video_id = v.video_id
            JOIN Channel c ON v.channel_id = c.channel_id
            JOIN Category cat ON v.category_id = cat.category_id
            WHERE {where_clause}
            ORDER BY tr.views DESC
            LIMIT 100;
        """

        conn = cls.get_pg_connection()
        try:
            return pd.read_sql(sql, conn, params=tuple(params))
        finally:
            conn.close()