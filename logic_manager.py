import json
import re
from datetime import date, datetime

import pandas as pd

from data_manager import DataManager, DELETE_SQL, READ_SQL

# Demo accounts for the two roles. Fine for a class project, not for a real deployment.
USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "viewer": {"password": "viewer123", "role": "viewer"},
}

# Tables whose primary key is an integer (the others use text keys)
NUMERIC_KEY_TABLES = {"Category", "Channel", "Channel Stats", "Trending Record"}

# What the success message calls the record that was just saved
SAVED_LABELS = {
    "Category": "Category '{category_name}'",
    "Channel": "Channel '{channel_title}'",
    "Country": "Country '{country_name}'",
    "Video": "Video '{video_id}'",
    "Channel Stats": "Channel Stats record",
    "Trending Record": "Trending Record #{record_id}",
    "Revenue Record": "MongoDB Revenue Record for '{video_id}'",
}

# The claims dropdown uses short labels, but MongoDB stores the full outcome names
DISPUTE_OUTCOMES = {
    "upheld": "claim_upheld",
    "released": "released_to_creator",
    "pending": "pending",
}


class LogicManager:
    """Validates input and applies the business rules before anything reaches DataManager."""

    # Creator tiers from smallest to biggest, used to decide which video "should" earn more
    TIER_ORDER = ["small", "medium", "large", "mega"]

    @staticmethod
    def authenticate(username, password):
        user = USERS.get(username.strip().lower())
        if user and user["password"] == password:
            return True, user["role"]
        return False, None

    # Validators. Each returns (True, cleaned_record) or (False, error_message).
    # They take either a submitted form or one row of an uploaded file.

    @staticmethod
    def validate_category(data):
        try:
            category_id = int(data.get("category_id", 0))
        except (ValueError, TypeError):
            return False, "Invalid numeric or text values for Category."
        name = str(data.get("category_name", "")).strip()

        if category_id < 1:
            return False, "Category ID must be a positive integer."
        if not 1 <= len(name) <= 100:
            return False, "Category Name must be 1 to 100 characters."
        return True, {"category_id": category_id, "category_name": name}

    @staticmethod
    def validate_channel(data):
        try:
            channel_id = int(data.get("channel_id", 0))
        except (ValueError, TypeError):
            return False, "Invalid numeric or text values for Channel."
        title = str(data.get("channel_title", "")).strip()

        if channel_id < 1:
            return False, "Channel ID must be a positive integer."
        if not 1 <= len(title) <= 255:
            return False, "Channel Title must be 1 to 255 characters."
        return True, {"channel_id": channel_id, "channel_title": title}

    @staticmethod
    def validate_country(data):
        code = str(data.get("country_code", "")).strip().upper()
        name = str(data.get("country_name", "")).strip()

        # Same rule as the CHECK constraint, so the user gets this message instead of a database error
        if not re.fullmatch(r"[A-Z]{2}", code):
            return False, "Country Code must be exactly 2 letters (e.g. US, SG)."
        if not name:
            return False, "Country Name cannot be empty."
        return True, {"country_code": code, "country_name": name}

    @staticmethod
    def validate_video(data):
        video_id = str(data.get("video_id", "")).strip()
        title = str(data.get("title", "")).strip()

        if len(video_id) != 11:
            return False, "Video ID must be exactly 11 characters."
        if not title:
            return False, "Title cannot be blank."

        try:
            tag_count = int(data.get("tag_count", 0))
            channel_id = int(data.get("channel_id", 0))
            category_id = int(data.get("category_id", 0))
            if tag_count < 0 or channel_id < 1 or category_id < 1:
                return False, "IDs must be >= 1, tag count must be non-negative."

            # Uploaded files give one publish_time column; the form gives a separate date and time
            if data.get("publish_time"):
                publish_time = pd.to_datetime(data.get("publish_time")).to_pydatetime()
            elif data.get("pub_date"):
                publish_time = datetime.strptime(
                    f"{data.get('pub_date')} {data.get('pub_time', '00:00')}", "%Y-%m-%d %H:%M"
                )
            else:
                return False, "Publish time or date is required."
        except Exception:
            return False, "Invalid numerical inputs or timestamp format."

        return True, {
            "video_id": video_id,
            "title": title,
            "publish_time": publish_time,
            "tag_count": tag_count,
            "channel_id": channel_id,
            "category_id": category_id,
        }

    @staticmethod
    def validate_channel_stats(data):
        # The insert form and the CSV files name these columns differently, so accept either
        def field(column_name, form_name, default=0):
            return data.get(column_name, data.get(form_name, default))

        try:
            record = {
                "channel_id": int(data.get("channel_id", 0)),
                "country_code": str(data.get("country_code", "")).strip().upper(),
                "subscriber": int(field("subscriber", "subscribers")),
                "video_views": int(field("video_views", "views")),
                "uploads": int(field("uploads", "total_uploads")),
                "created_date": field("created_date", "stats_date", None),
                "video_views_last_30_days": int(field("video_views_last_30_days", "views_30")),
                "subscribers_last_30_days": int(field("subscribers_last_30_days", "subs_30")),
            }
        except (ValueError, TypeError):
            return False, "Invalid numerical inputs in Channel Stats."

        if record["channel_id"] < 1 or len(record["country_code"]) != 2 or not record["created_date"]:
            return False, "Invalid identifiers, country code, or missing date."
        return True, record

    @staticmethod
    def validate_trending_record(data):
        def text(key):
            value = data.get(key)
            return "" if value is None else str(value).strip()

        if not text("record_id"):
            return False, "Record ID is required."

        try:
            record_id = int(text("record_id"))
            # the count fields may be left blank, which we treat as 0
            counts = {key: int(text(key) or 0) for key in ("views", "likes", "dislikes", "comment_count")}
        except ValueError as e:
            return False, f"Invalid numerical value entered: {e}"

        video_id = text("video_id")
        country_code = text("country_code").upper()

        if record_id < 1:
            return False, "Record ID must be an integer greater than 0."
        if len(video_id) != 11:
            return False, f"Video ID must be exactly 11 characters (you entered {len(video_id)})."
        if len(country_code) != 2:
            return False, f"Country Code must be 2 characters (e.g. US, SG). Received '{country_code}'."
        if not text("trending_date"):
            return False, "Trending Date is required."

        return True, {
            "record_id": record_id,
            "video_id": video_id,
            "country_code": country_code,
            "trending_date": text("trending_date"),
            **counts,
        }

    @classmethod
    def validate_revenue_record(cls, data):
        try:
            video_id = str(data.get("video_id", "")).strip()
            if len(video_id) != 11:
                return False, "Video ID must be exactly 11 characters."

            tier = str(data.get("creator_tier", "")).strip().lower()
            if tier and tier not in cls.TIER_ORDER:
                return False, f"Creator tier must be one of: {', '.join(sorted(cls.TIER_ORDER))}."

            country_revenue = data.get("revenue_by_country", [])
            if isinstance(country_revenue, list):
                for entry in country_revenue:
                    if float(entry.get("estimated_gross_usd", 0.0)) < 0:
                        return False, "Estimated gross USD cannot be negative."

            # MongoDB stores whatever we pass, so leave out its own _id and the two
            # hidden fields the insert form uses to tell Flask what to do
            doc = {key: value for key, value in dict(data).items() if key not in ("_id", "action", "table")}
            doc["video_id"] = video_id
            if tier:
                doc["creator_tier"] = tier

            # Form values arrive as text; keep the numeric ones as numbers
            for key, cast in (("estimated_revenue", float), ("monetized_playbacks", int)):
                if doc.get(key) == "":
                    del doc[key]
                elif key in doc:
                    doc[key] = cast(doc[key])
            return True, doc
        except (ValueError, TypeError) as e:
            return False, f"Invalid numerical inputs for Revenue Record: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

    @classmethod
    def _validators(cls):
        return {
            "Category": cls.validate_category,
            "Channel": cls.validate_channel,
            "Country": cls.validate_country,
            "Video": cls.validate_video,
            "Channel Stats": cls.validate_channel_stats,
            "Trending Record": cls.validate_trending_record,
            "Revenue Record": cls.validate_revenue_record,
        }

    @staticmethod
    def _save(table, records):
        # Revenue documents live in MongoDB, every other table is in PostgreSQL
        if table == "Revenue Record":
            return DataManager.upsert_revenue(records)
        return DataManager.upsert_postgres(table, records)

    # Insert, read and delete for the admin page

    @classmethod
    def execute_insert(cls, table, payload):
        validator = cls._validators().get(table)
        if validator is None:
            return False, "Unsupported target table specified."

        valid, result = validator(payload)
        if not valid:
            return False, result

        try:
            cls._save(table, [result])
        except Exception as e:
            message = str(e)
            if "Constraint Violation:" in message:
                # Raised by our trigger. Keep its message and drop PostgreSQL's CONTEXT lines.
                return False, message.split("CONTEXT:")[0].replace("ERROR:", "").strip()
            return False, f"Database operation failure: {message}"

        return True, SAVED_LABELS[table].format(**result) + " saved/overwritten successfully."

    @classmethod
    def execute_bulk_insert(cls, table, file_obj):
        """Validate every row of an uploaded CSV or JSON file, then upsert them all together."""
        validator = cls._validators().get(table)
        if validator is None:
            return False, f"Unsupported table '{table}' for bulk insert."

        filename = file_obj.filename.lower()
        try:
            if filename.endswith(".csv"):
                if table == "Revenue Record":
                    df = pd.read_csv(file_obj)
                    records = df.where(pd.notnull(df), None).to_dict(orient="records")
                else:
                    # Read everything as text so IDs keep their exact form; the validators do the conversion
                    df = pd.read_csv(file_obj, dtype=str, keep_default_na=False, encoding="utf-8-sig")
                    records = df.to_dict(orient="records")
            elif filename.endswith(".json"):
                data = json.load(file_obj)
                records = data if isinstance(data, list) else [data]
            else:
                return False, "Unsupported file format. Please upload a .csv or .json dataset."

            if not records:
                return False, "Uploaded file contains no rows or data."

            # Check every row first so a bad file is rejected before anything is written
            cleaned = []
            for row_number, row in enumerate(records, start=1):
                valid, result = validator(row)
                if not valid:
                    return False, f"Row {row_number} failed validation: {result}"
                cleaned.append(result)

            count = cls._save(table, cleaned)
            if table == "Revenue Record":
                return True, f"Successfully processed/overwrote {count} document(s) in MongoDB Atlas."
            return True, f"Successfully processed/overwrote {count} record(s) in PostgreSQL."
        except Exception as e:
            return False, f"Bulk import error: {e}"

    @staticmethod
    def _clean_key(table, identifier):
        """Convert a typed-in primary key to the form the table expects."""
        identifier = str(identifier or "").strip()
        if not identifier:
            raise ValueError("Please enter a record ID.")

        if table in NUMERIC_KEY_TABLES:
            try:
                return int(identifier)
            except ValueError:
                raise ValueError("The record ID must be an integer.") from None
        if table == "Country":
            return identifier.upper()
        return identifier

    @classmethod
    def read_record(cls, table, identifier):
        if table not in READ_SQL:
            raise ValueError("Invalid table selected.")
        return DataManager.read_record(table, cls._clean_key(table, identifier))

    @classmethod
    def execute_delete(cls, table, identifier):
        identifier = str(identifier or "").strip()
        if not identifier:
            return False, "Primary key identifier must be provided."

        try:
            if table == "Revenue Record":
                if len(identifier) != 11:
                    return False, "Video ID must be exactly 11 characters."
                deleted = DataManager.delete_revenue(identifier)
            elif table in DELETE_SQL:
                deleted = DataManager.delete_record(table, cls._clean_key(table, identifier))
            else:
                return False, f"Deletion is not supported for {table}."
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            # Usually a foreign key: the row is still referenced by another table
            return False, f"Integrity error: {e}"

        if deleted:
            return True, f"Record '{identifier}' deleted."
        return False, "Record not found."

    # PostgreSQL dashboard and trending search

    @staticmethod
    def get_analytical_view(view_name):
        df = DataManager.fetch_analytical_view(view_name)
        # SQL NULLs become NaN in pandas, which the page would print as "nan"
        records = df.astype(object).where(df.notna(), None).to_dict(orient="records")
        return df.columns.tolist(), records

    @staticmethod
    def get_filter_dropdown_options():
        return DataManager.get_filter_dropdown_options()

    @staticmethod
    def explore_trending_videos(keyword=None, country=None, category_id=None,
                                start_date=None, end_date=None):
        # Empty boxes and the "all" option both mean "no filter", which the SQL function expects as NULL
        def optional(value):
            value = str(value).strip() if value is not None else ""
            return None if value == "" or value.lower() == "all" else value

        def parse_date(value, label):
            value = optional(value)
            if value is None:
                return None
            try:
                return date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"{label} must use YYYY-MM-DD format.") from None

        keyword = optional(keyword)
        country = optional(country)
        category_id = optional(category_id)

        if country is not None:
            country = country.upper()
            if not re.fullmatch(r"[A-Z]{2}", country):
                raise ValueError("Country code must contain two letters.")

        if category_id is not None:
            try:
                category_id = int(category_id)
            except ValueError:
                raise ValueError("Category ID must be an integer.") from None

        start_date = parse_date(start_date, "Start date")
        end_date = parse_date(end_date, "End date")
        if start_date and end_date and start_date > end_date:
            raise ValueError("Start date cannot be later than end date.")

        return DataManager.explore_trending_videos(
            keyword=keyword,
            country=country,
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
        )

    # MongoDB revenue analytics

    @staticmethod
    def _add_names(rows):
        """Add the title/name from PostgreSQL to rows that only carry MongoDB IDs."""
        video_map, channel_map, category_map = DataManager.get_metadata_lookup_maps()
        for row in rows:
            if "video_id" in row:
                row["video_title"] = video_map.get(row["video_id"], f"Video {row['video_id']}")
            if "channel_id" in row:
                row["channel_name"] = channel_map.get(row["channel_id"], f"Channel {row['channel_id']}")
            if "category_id" in row:
                row["category_name"] = category_map.get(row["category_id"], f"Category {row['category_id']}")
        return rows

    @classmethod
    def clean_tier(cls, tier):
        tier = str(tier or "").strip().lower()
        return tier if tier in cls.TIER_ORDER else "large"

    @classmethod
    def filter_by_creator_tier(cls, tier="large"):
        rows = DataManager.filter_by_creator_tier(cls.clean_tier(tier))
        return cls._add_names(rows) if rows else rows

    @staticmethod
    def aggregate_revenue_by_country():
        return DataManager.aggregate_revenue_by_country()

    @classmethod
    def aggregate_category_breakdown(cls):
        rows = DataManager.aggregate_category_breakdown()
        try:
            cls._add_names(rows)
        except Exception:
            # Without PostgreSQL the page still works and shows "Category <id>" instead of the name
            pass
        return rows

    @staticmethod
    def compare_creator_tiers():
        return DataManager.compare_creator_tiers()

    @staticmethod
    def get_copyright_claims_summary(policy_filter=None, outcome_filter=None):
        policy = None if policy_filter in (None, "", "all") else policy_filter
        outcome = None if outcome_filter in (None, "", "all") else outcome_filter
        rows = DataManager.get_copyright_claims_summary(policy, DISPUTE_OUTCOMES.get(outcome, outcome))

        # Show the same short labels as the dropdown
        short_labels = {stored: short for short, stored in DISPUTE_OUTCOMES.items()}
        for row in rows:
            outcomes = [o for o in row.get("dispute_outcomes", []) if o]
            row["dispute_outcomes"] = sorted(short_labels.get(o, o) for o in outcomes)
            row["policies"] = sorted(row.get("policies", []))
        return rows

    @staticmethod
    def get_video_stats_by_id(video_id):
        video_id = str(video_id or "").strip()
        if len(video_id) != 11:
            return {}

        stats = DataManager.get_video_stats_by_id(video_id)
        if stats:
            try:
                video_map, channel_map, category_map = DataManager.get_metadata_lookup_maps()
                stats["video_title"] = video_map.get(stats.get("video_id"), "Unknown Title")
                stats["channel_name"] = channel_map.get(stats.get("channel_id"), "Unknown Channel")
                stats["category_name"] = category_map.get(stats.get("category_id"), "Unknown Category")
            except Exception:
                # The revenue numbers are still worth showing if PostgreSQL is unreachable
                pass
        return stats

    @staticmethod
    def get_revenue_video_options(limit=500):
        """Videos that have a revenue document, sorted by title, for the video dropdowns."""
        videos = DataManager.list_revenue_video_ids(limit)
        video_map, _, _ = DataManager.get_metadata_lookup_maps()
        for video in videos:
            video["title"] = video_map.get(video["video_id"], "")
        return sorted(videos, key=lambda v: (v["title"] or v["video_id"]).lower())

    @classmethod
    def compare_two_videos(cls, video_a_id, video_b_id):
        """Compare the revenue of two videos and say whether the result matches their tiers."""
        video_ids = []
        for video_id in (video_a_id, video_b_id):
            video_id = str(video_id or "").strip()
            if len(video_id) != 11:
                raise ValueError("Video ID must be exactly 11 characters.")
            video_ids.append(video_id)

        if video_ids[0] == video_ids[1]:
            raise ValueError("Please select two different videos to compare.")

        video_a = DataManager.get_video_comparison_item(video_ids[0])
        video_b = DataManager.get_video_comparison_item(video_ids[1])
        if not video_a:
            raise ValueError(f"No revenue record found for Video A ({video_ids[0]}).")
        if not video_b:
            raise ValueError(f"No revenue record found for Video B ({video_ids[1]}).")
        cls._add_names([video_a, video_b])

        difference = video_a["total_revenue"] - video_b["total_revenue"]
        amount = f"${abs(difference):,.2f}"
        if difference > 0:
            higher_earner = "A"
        elif difference < 0:
            higher_earner = "B"
        else:
            higher_earner = "Tie"

        # A tier we do not know about sits below all of the known ones
        level = {tier: position for position, tier in enumerate(cls.TIER_ORDER)}
        level_a = level.get(video_a["creator_tier"], -1)
        level_b = level.get(video_b["creator_tier"], -1)
        tier_a = video_a["creator_tier"].capitalize()
        tier_b = video_b["creator_tier"].capitalize()

        if level_a == level_b:
            verdict = f"Both videos belong to the same tier ({tier_a}). Revenue difference is {amount}."
        else:
            # "top" is the video in the higher tier, which we expect to earn more
            if level_a > level_b:
                top, low, tiers = "A", "B", f"{tier_a} vs {tier_b}"
            else:
                top, low, tiers = "B", "A", f"{tier_b} vs {tier_a}"

            if higher_earner == top:
                verdict = f"Expected Outcome: Video {top} is in a higher tier ({tiers}) and earned {amount} more."
            elif higher_earner == "Tie":
                verdict = f"Video {top} is in a higher tier ({tiers}), but both videos earned the same amount."
            else:
                verdict = f"Anomaly: Despite Video {top} being a higher tier ({tiers}), Video {low} earned {amount} more."

        return {
            "video_a": video_a,
            "video_b": video_b,
            "revenue_difference": abs(difference),
            "higher_earner": higher_earner,
            "tier_verdict": verdict,
        }
