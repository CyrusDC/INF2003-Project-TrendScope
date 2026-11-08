import io
import json
import pandas as pd
import datetime as dt
import re
from data_manager import DataManager
from datetime import date


class LogicManager:
    """Orchestrates business validation, security barriers, and coordinates with DataManager."""

    # Creator tiers from smallest to biggest. Edit to match the values in your data.
    # Any tier not listed here is shown but left out of the "does bigger earn more?" check.
    TIER_ORDER = ["small", "medium", "large", "mega"]

    @staticmethod
    def authenticate(username, password):
        users = {
            "admin": {"password": "admin123", "role": "admin"},
            "viewer": {"password": "viewer123", "role": "viewer"}
        }
        user = users.get(username.strip().lower())
        if user and user["password"] == password:
            return True, user["role"]
        return False, None

    @staticmethod
    def verify_role_access(role, required_role="admin"):
        return role == required_role

    # ------------------------------------------------------------------
    # VALIDATION LOGIC FOR ALL TABLES
    # ------------------------------------------------------------------
    @staticmethod
    def validate_category(data):
        try:
            cid = int(data.get("category_id", 0))
            name = str(data.get("category_name", "")).strip()
            if cid < 1:
                return False, "Category ID must be a positive integer."
            if not (1 <= len(name) <= 100):
                return False, "Category Name must be 1 to 100 characters."
            return True, {"cat_id": cid, "cat_name": name}
        except Exception:
            return False, "Invalid numeric or text values for Category."

    @staticmethod
    def validate_channel(data):
        try:
            cid = int(data.get("channel_id", 0))
            title = str(data.get("channel_title", "")).strip()
            if cid < 1:
                return False, "Channel ID must be a positive integer."
            if not (1 <= len(title) <= 255):
                return False, "Channel Title must be 1 to 255 characters."
            return True, {"chan_id": cid, "chan_title": title}
        except Exception:
            return False, "Invalid numeric or text values for Channel."

    @staticmethod
    def validate_country(data):
        try:
            code = str(data.get("country_code", "")).strip().upper()
            name = str(data.get("country_name", "")).strip()
            if len(code) != 2:
                return False, "Country Code must be exactly 2 characters (e.g. US, SG)."
            if not name:
                return False, "Country Name cannot be empty."
            return True, {"code": code, "name": name}
        except Exception:
            return False, "Invalid data types for Country."

    @staticmethod
    def validate_video(data):
        vid_id = str(data.get("video_id", "")).strip()
        title = str(data.get("title", "")).strip()
        pub_date = data.get("pub_date")
        pub_time = data.get("pub_time", "00:00")
        publish_time_raw = data.get("publish_time")

        if len(vid_id) != 11:
            return False, "Video ID must be exactly 11 characters."
        if not title:
            return False, "Title cannot be blank."

        try:
            tag_count = int(data.get("tag_count", 0))
            chan_id = int(data.get("channel_id", 0))
            cat_id = int(data.get("category_id", 0))
            if tag_count < 0 or chan_id < 1 or cat_id < 1:
                return False, "IDs must be >= 1, tag count must be non-negative."

            if publish_time_raw:
                pub_dt = pd.to_datetime(publish_time_raw).to_pydatetime()
            elif pub_date:
                pub_dt = dt.datetime.strptime(f"{pub_date} {pub_time}", "%Y-%m-%d %H:%M")
            else:
                return False, "Publish time or date is required."

            return True, {
                "video_id": vid_id, "title": title, "pub_dt": pub_dt,
                "tag_count": tag_count, "channel_id": chan_id, "category_id": cat_id
            }
        except Exception:
            return False, "Invalid numerical inputs or timestamp format."

    @staticmethod
    def validate_channel_stats(data):
        try:
            chan_id = int(data.get("channel_id", 0))
            c_code = str(data.get("country_code", "")).strip().upper()
            rank = int(data.get("global_rank", 0))
            sub = int(data.get("subscriber", 0))
            views = int(data.get("video_views", 0))
            uploads = int(data.get("uploads", 0))
            s_date = data.get("created_date")
            v30 = int(data.get("video_views_last_30_days", 0))
            s30 = int(data.get("subscribers_last_30_days", 0))

            if chan_id < 1 or rank < 1 or len(c_code) != 2 or not s_date:
                return False, "Invalid identifiers, country code, or missing date."
            return True, {
                "chan_id": chan_id, "c_code": c_code, "rank": rank, "sub": sub,
                "views": views, "uploads": uploads, "dt_val": s_date, "v30": v30, "s30": s30
            }
        except Exception:
            return False, "Invalid numerical inputs in Channel Stats."

    @staticmethod
    def validate_trending_record(data):
        try:
            # Helper to safely parse ints with empty-string fallback to default
            def to_int(val, default=0):
                v = str(val).strip() if val is not None else ""
                return int(v) if v != "" else default

            rec_id_val = data.get("record_id")
            if not rec_id_val or str(rec_id_val).strip() == "":
                return False, "Record ID is required."
            
            rec_id = int(str(rec_id_val).strip())
            vid_id = str(data.get("video_id", "")).strip()
            c_code = str(data.get("country_code", "")).strip().upper()
            t_date = data.get("trending_date", "").strip() if data.get("trending_date") else ""

            views = to_int(data.get("views"), 0)
            likes = to_int(data.get("likes"), 0)
            dislikes = to_int(data.get("dislikes"), 0)
            comments = to_int(data.get("comment_count"), 0)

            if rec_id < 1:
                return False, "Record ID must be an integer greater than 0."
            if len(vid_id) != 11:
                return False, f"Video ID must be exactly 11 characters (you entered {len(vid_id)})."
            if len(c_code) != 2:
                return False, f"Country Code must be 2 characters (e.g. US, SG). Received '{c_code}'."
            if not t_date:
                return False, "Trending Date is required."

            return True, {
                "rec_id": rec_id, "vid_id": vid_id, "c_code": c_code,
                "t_date": t_date, "views": views, "likes": likes,
                "dislikes": dislikes, "comments": comments
            }
        except (ValueError, TypeError) as e:
            return False, f"Invalid numerical value entered: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def validate_revenue_record(data):
        try:
            vid_id = str(data.get("video_id", "")).strip()
            if len(vid_id) != 11:
                return False, "Video ID must be exactly 11 characters."

            # Whitelist creator tiers (matching TIER_ORDER)
            tier = str(data.get("creator_tier", "")).strip().lower()
            valid_tiers = {"small", "medium", "large", "mega"}
            if tier and tier not in valid_tiers:
                return False, f"Creator tier must be one of: {', '.join(sorted(valid_tiers))}."

            # Verify non-negative values in nested country revenue if provided
            country_revenue = data.get("revenue_by_country", [])
            if isinstance(country_revenue, list):
                for entry in country_revenue:
                    usd = float(entry.get("estimated_gross_usd", 0.0))
                    if usd < 0:
                        return False, "Estimated gross USD cannot be negative."

            # Clean dict copy for MongoDB
            clean_doc = dict(data)
            clean_doc["video_id"] = vid_id
            if tier:
                clean_doc["creator_tier"] = tier
            clean_doc.pop("_id", None)
            return True, clean_doc
        except (ValueError, TypeError) as e:
            return False, f"Invalid numerical inputs for Revenue Record: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    # ------------------------------------------------------------------
    # SINGLE INSERT EXECUTION (UPSERT)
    # ------------------------------------------------------------------
    @classmethod
    def execute_insert(cls, table, payload):
        try:
            if table == "Category":
                valid, res = cls.validate_category(payload)
                if not valid: return False, res
                DataManager.insert_category(res["cat_id"], res["cat_name"])
                return True, f"Category '{res['cat_name']}' saved/overwritten successfully."

            elif table == "Channel":
                valid, res = cls.validate_channel(payload)
                if not valid: return False, res
                DataManager.insert_channel(res["chan_id"], res["chan_title"])
                return True, f"Channel '{res['chan_title']}' saved/overwritten successfully."

            elif table == "Country":
                valid, res = cls.validate_country(payload)
                if not valid: return False, res
                DataManager.insert_country(res["code"], res["name"])
                return True, f"Country '{res['name']}' saved/overwritten successfully."

            elif table == "Video":
                valid, res = cls.validate_video(payload)
                if not valid: return False, res
                DataManager.insert_video(
                    res["video_id"], res["title"], res["pub_dt"],
                    res["tag_count"], res["channel_id"], res["category_id"]
                )
                return True, f"Video '{res['video_id']}' saved/overwritten successfully."

            elif table == "Channel Stats":
                valid, res = cls.validate_channel_stats(payload)
                if not valid: return False, res
                DataManager.insert_channel_stats(
                    res["chan_id"], res["c_code"], res["rank"], res["sub"],
                    res["views"], res["uploads"], res["dt_val"], res["v30"], res["s30"]
                )
                return True, "Channel Stats record saved/overwritten successfully."

            elif table == "Trending Record":
                valid, res = cls.validate_trending_record(payload)
                if not valid: return False, res
                DataManager.insert_trending_record(
                    res["rec_id"], res["vid_id"], res["c_code"], res["t_date"],
                    res["views"], res["likes"], res["dislikes"], res["comments"]
                )
                return True, f"Trending Record #{res['rec_id']} saved/overwritten successfully."

            elif table == "Revenue Record":
                valid, res = cls.validate_revenue_record(payload)
                if not valid: return False, res
                DataManager.insert_mongo_revenue(res)
                return True, f"MongoDB Revenue Record for '{res['video_id']}' saved/overwritten successfully."

            return False, "Unsupported target table specified."
        except Exception as e:
            err_msg = str(e)
            if "Constraint Violation:" in err_msg:
                # Strip PostgreSQL internal context lines and show just the violation
                clean_err = err_msg.split("CONTEXT:")[0].replace("ERROR:", "").strip()
                return False, clean_err
            return False, f"Database operation failure: {err_msg}"

    # ------------------------------------------------------------------
    # BULK FILE INSERTION (CSV & JSON)
    # ------------------------------------------------------------------
    @classmethod
    def execute_bulk_insert(cls, table, file_obj):
        """Parses CSV or JSON file upload, validates each record, and performs upsert."""
        filename = file_obj.filename.lower()
        try:
            if filename.endswith(".csv"):
                if table == "Revenue Record":
                    df = pd.read_csv(file_obj)
                    records = df.where(pd.notnull(df), None).to_dict(orient="records")
                else:
                    df = pd.read_csv(file_obj, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                    records = df.to_dict(orient="records")
            elif filename.endswith(".json"):
                data = json.load(file_obj)
                records = data if isinstance(data, list) else [data]
            else:
                return False, "Unsupported file format. Please upload a .csv or .json dataset."

            if not records:
                return False, "Uploaded file contains no rows or data."

            validators = {
                "Category": cls.validate_category,
                "Channel": cls.validate_channel,
                "Country": cls.validate_country,
                "Video": cls.validate_video,
                "Channel Stats": cls.validate_channel_stats,
                "Trending Record": cls.validate_trending_record,
                "Revenue Record": cls.validate_revenue_record
            }

            validator = validators.get(table)
            if not validator:
                return False, f"Unsupported table '{table}' for bulk insert."

            valid_records = []
            for idx, r in enumerate(records, start=1):
                is_valid, cleaned_or_err = validator(r)
                if not is_valid:
                    return False, f"Row {idx} failed validation: {cleaned_or_err}"
                valid_records.append(cleaned_or_err)

            # Route to MongoDB or PostgreSQL
            if table == "Revenue Record":
                count = DataManager.bulk_upsert_mongo_revenue(valid_records)
                return True, f"Successfully processed/overwrote {count} document(s) in MongoDB Atlas."
            else:
                count = DataManager.bulk_upsert_postgres(table, valid_records)
                return True, f"Successfully processed/overwrote {count} record(s) in PostgreSQL."

        except Exception as e:
            return False, f"Bulk import error: {str(e)}"

    @staticmethod
    def read_record(table, identifier):
        valid_tables = {"Category", "Channel", "Country", "Video", "Channel Stats", "Trending Record",}

        if table not in valid_tables:
            raise ValueError("Invalid table selected.")

        identifier = str(identifier or "").strip()

        if not identifier:
            raise ValueError("Please enter a record ID.")

        numeric_id_tables = {"Category", "Channel", "Channel Stats", "Trending Record",}

        if table in numeric_id_tables:
            try:
                identifier = str(int(identifier))
            except ValueError:
                raise ValueError(
                    "The record ID must be an integer."
                ) from None

        elif table == "Country":
            identifier = identifier.upper()

        return DataManager.read_record(table, identifier)


    @classmethod
    def execute_delete(cls, table, identifier):
        if not identifier:
            return False, "Primary key identifier must be provided."
        try:
            if table == "Revenue Record":
                if len(identifier) != 11:
                    return False, "Video ID must be exactly 11 characters."
                success = DataManager.delete_mongo_revenue(identifier)
            else:
                success = DataManager.delete_record(table, identifier)
            return (True, f"Record '{identifier}' deleted.") if success else (False, "Record not found.")
        except Exception as e:
            return False, f"Integrity error: {str(e)}"
        
    @staticmethod
    def get_filter_dropdown_options():
        return DataManager.get_filter_dropdown_options()

    @staticmethod
    def explore_trending_videos(keyword=None, country=None, category_id=None, start_date=None, end_date=None):
        def clean_optional(value):
            if value is None:
                return None
            value = str(value).strip()
            return value if value else None

        keyword = clean_optional(keyword)
        country = clean_optional(country)
        category_id = clean_optional(category_id)

        if country and country.lower() == "all":
            country = None
        if category_id and category_id.lower() == "all":
            category_id = None
        if country is not None:
            country = country.upper()

            if not re.fullmatch(r"[A-Z]{2}", country):
                raise ValueError(
                    "Country code must contain two letters."
                )

        if category_id is not None:
            try:
                category_id = int(category_id)
            except ValueError:
                raise ValueError(
                    "Category ID must be an integer."
                ) from None

        def parse_date(value, label):
            value = clean_optional(value)
            if value is None:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise ValueError(
                    f"{label} must use YYYY-MM-DD format."
                ) from None
        start_date = parse_date(start_date, "Start date")
        end_date = parse_date(end_date, "End date")
        if (
            start_date is not None
            and end_date is not None
            and start_date > end_date
        ):
            raise ValueError(
                "Start date cannot be later than end date."
            )
        return DataManager.explore_trending_videos(keyword=keyword, country=country, category_id=category_id, start_date=start_date, end_date=end_date
        )


    # ------------------------------------------------------------------
    # MONGODB VALIDATION
    # ------------------------------------------------------------------

    @staticmethod
    def get_video_stats_by_id(video_id):
        clean_id = str(video_id or "").strip()
        if len(clean_id) != 11:
            return {}
        return DataManager.get_video_stats_by_id(clean_id)
    
    @staticmethod
    def filter_by_creator_tier(tier="large", limit=None):
        clean_tier = str(tier or "").strip().lower()
        valid_tiers = {"small", "medium", "large", "mega"}
        if clean_tier not in valid_tiers:
            clean_tier = "large"
        return DataManager.filter_by_creator_tier(clean_tier, limit)

    @staticmethod
    def aggregate_revenue_by_country():
        return DataManager.aggregate_revenue_by_country()

    @staticmethod
    def aggregate_category_breakdown():
        return DataManager.aggregate_category_breakdown()

    @staticmethod
    def compare_creator_tiers():
        return DataManager.compare_creator_tiers()

    @staticmethod
    def get_copyright_claims_summary(policy_filter=None, outcome_filter=None):
        return DataManager.get_copyright_claims_summary(policy_filter, outcome_filter)

    @staticmethod
    def get_metadata_lookup_maps():
        return DataManager.get_metadata_lookup_maps()

    @staticmethod
    def validate_video_id(video_id):
        vid = str(video_id or "").strip()
        if len(vid) != 11:
            raise ValueError("Video ID must be exactly 11 characters.")
        return vid

    @staticmethod
    def get_revenue_video_options(limit=500):
        """Builds sorted video list with titles and tiers for the dropdown selectors."""
        video_docs = DataManager.list_revenue_video_ids(limit)
        video_map, _, _ = DataManager.get_metadata_lookup_maps()
        options = [
            {
                "video_id": item["video_id"],
                "creator_tier": item["creator_tier"],
                "title": video_map.get(item["video_id"], "")
            }
            for item in video_docs
        ]
        return sorted(options, key=lambda o: (o["title"] or o["video_id"]).lower())

    @staticmethod
    def get_revenue_channel_options(limit=500):
        """Builds sorted channel list with titles for channel dropdown selectors."""
        ids = DataManager.list_revenue_channel_ids(limit)
        _, channel_map, _ = DataManager.get_metadata_lookup_maps()
        options = [{"channel_id": c, "title": channel_map.get(c, "")} for c in ids]
        return sorted(options, key=lambda o: (o["title"] or str(o["channel_id"])).lower())

    @classmethod
    def compare_two_videos(cls, video_a_id, video_b_id):
        """
        Validates and compares two distinct videos across tiers and total earnings.
        """
        vid_a = cls.validate_video_id(video_a_id)
        vid_b = cls.validate_video_id(video_b_id)

        if vid_a == vid_b:
            raise ValueError("Please select two different videos to compare.")

        doc_a = DataManager.get_video_comparison_item(vid_a)
        doc_b = DataManager.get_video_comparison_item(vid_b)

        if not doc_a:
            raise ValueError(f"No revenue record found for Video A ({vid_a}).")
        if not doc_b:
            raise ValueError(f"No revenue record found for Video B ({vid_b}).")

        # Enrich with titles from PostgreSQL
        video_map, channel_map, category_map = DataManager.get_metadata_lookup_maps()
        for doc in (doc_a, doc_b):
            vid = doc["video_id"]
            doc["video_title"] = video_map.get(vid, f"Video {vid}")
            doc["channel_name"] = channel_map.get(doc.get("channel_id"), f"Channel {doc.get('channel_id')}")
            doc["category_name"] = category_map.get(doc.get("category_id"), f"Category {doc.get('category_id')}")

        # Compute differences
        diff_rev = doc_a["total_revenue"] - doc_b["total_revenue"]
        higher_earner = "A" if diff_rev > 0 else ("B" if diff_rev < 0 else "Tie")

        # Evaluate Tier impact
        tier_rank = {t: i for i, t in enumerate(cls.TIER_ORDER)}
        rank_a = tier_rank.get(doc_a["creator_tier"], -1)
        rank_b = tier_rank.get(doc_b["creator_tier"], -1)

        tier_comparison = None
        if rank_a > rank_b:
            if higher_earner == "A":
                tier_verdict = f"Expected Outcome: Video A is in a higher tier ({doc_a['creator_tier'].capitalize()} vs {doc_b['creator_tier'].capitalize()}) and earned ${abs(diff_rev):,.2f} more."
            else:
                tier_verdict = f"Anomaly: Despite Video A being a higher tier ({doc_a['creator_tier'].capitalize()} vs {doc_b['creator_tier'].capitalize()}), Video B earned ${abs(diff_rev):,.2f} more."
        elif rank_b > rank_a:
            if higher_earner == "B":
                tier_verdict = f"Expected Outcome: Video B is in a higher tier ({doc_b['creator_tier'].capitalize()} vs {doc_a['creator_tier'].capitalize()}) and earned ${abs(diff_rev):,.2f} more."
            else:
                tier_verdict = f"Anomaly: Despite Video B being a higher tier ({doc_b['creator_tier'].capitalize()} vs {doc_a['creator_tier'].capitalize()}), Video A earned ${abs(diff_rev):,.2f} more."
        else:
            tier_verdict = f"Both videos belong to the same tier ({doc_a['creator_tier'].capitalize()}). Revenue difference is ${abs(diff_rev):,.2f}."

        return {
            "video_a": doc_a,
            "video_b": doc_b,
            "revenue_difference": abs(diff_rev),
            "higher_earner": higher_earner,
            "tier_verdict": tier_verdict
        }