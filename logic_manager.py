import datetime as dt
from data_manager import DataManager

class LogicManager:
    """Orchestrates business validation, security barriers, and coordinates with DataManager."""

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
            pop = int(data.get("population", 0))
            if len(code) != 2:
                return False, "Country Code must be exactly 2 characters (e.g. US, SG)."
            if not name:
                return False, "Country Name cannot be empty."
            if pop < 0:
                return False, "Population cannot be negative."
            return True, {"code": code, "name": name, "pop": pop}
        except Exception:
            return False, "Invalid data types for Country."

    @staticmethod
    def validate_video(data):
        vid_id = str(data.get("video_id", "")).strip()
        title = str(data.get("title", "")).strip()
        pub_date = data.get("pub_date")
        pub_time = data.get("pub_time", "00:00")

        if len(vid_id) != 11:
            return False, "Video ID must be exactly 11 characters."
        if not title:
            return False, "Title cannot be blank."
        if not pub_date:
            return False, "Publish Date is required."

        try:
            tag_count = int(data.get("tag_count", 0))
            chan_id = int(data.get("channel_id", 0))
            cat_id = int(data.get("category_id", 0))
            if tag_count < 0 or chan_id < 1 or cat_id < 1:
                return False, "IDs must be >= 1, tag count must be non-negative."
            pub_dt = dt.datetime.strptime(f"{pub_date} {pub_time}", "%Y-%m-%d %H:%M")
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
            rank = int(data.get("rank", 0))
            sub = int(data.get("subscribers", 0))
            views = int(data.get("views", 0))
            uploads = int(data.get("total_uploads", 0))
            s_date = data.get("stats_date")
            v30 = int(data.get("views_30", 0))
            s30 = int(data.get("subs_30", 0))

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
            rec_id = int(data.get("record_id", 0))
            vid_id = str(data.get("video_id", "")).strip()
            c_code = str(data.get("country_code", "")).strip().upper()
            t_date = data.get("trending_date")
            views = int(data.get("views", 0))
            likes = int(data.get("likes", 0))
            dislikes = int(data.get("dislikes", 0))
            comments = int(data.get("comment_count", 0))

            if rec_id < 1 or len(vid_id) != 11 or len(c_code) != 2 or not t_date:
                return False, "Invalid record ID, video ID (11 chars), country code (2 chars), or date."
            return True, {
                "rec_id": rec_id, "vid_id": vid_id, "c_code": c_code,
                "t_date": t_date, "views": views, "likes": likes,
                "dislikes": dislikes, "comments": comments
            }
        except Exception:
            return False, "Invalid numerical or date inputs in Trending Record."

    @staticmethod
    def validate_revenue_record(data):
        try:
            vid_id = str(data.get("video_id", "")).strip()
            rev = float(data.get("estimated_revenue", 0.0))
            playbacks = int(data.get("monetized_playbacks", 0))
            if len(vid_id) != 11 or rev < 0 or playbacks < 0:
                return False, "Video ID must be 11 chars; revenue and playbacks must be >= 0."
            return True, {
                "video_id": vid_id,
                "estimated_revenue": rev,
                "monetized_playbacks": playbacks
            }
        except Exception:
            return False, "Invalid inputs for Revenue Record."

    # ------------------------------------------------------------------
    # COORDINATION WITH DATA MANAGER
    # ------------------------------------------------------------------
    @classmethod
    def execute_insert(cls, table, payload):
        try:
            if table == "Category":
                valid, res = cls.validate_category(payload)
                if not valid: return False, res
                DataManager.insert_category(res["cat_id"], res["cat_name"])
                return True, f"Category '{res['cat_name']}' created successfully."

            elif table == "Channel":
                valid, res = cls.validate_channel(payload)
                if not valid: return False, res
                DataManager.insert_channel(res["chan_id"], res["chan_title"])
                return True, f"Channel '{res['chan_title']}' created successfully."

            elif table == "Country":
                valid, res = cls.validate_country(payload)
                if not valid: return False, res
                DataManager.insert_country(res["code"], res["name"], res["pop"])
                return True, f"Country '{res['name']}' added successfully."

            elif table == "Video":
                valid, res = cls.validate_video(payload)
                if not valid: return False, res
                DataManager.insert_video(
                    res["video_id"], res["title"], res["pub_dt"],
                    res["tag_count"], res["channel_id"], res["category_id"]
                )
                return True, f"Video '{res['video_id']}' added successfully."

            elif table == "Channel Stats":
                valid, res = cls.validate_channel_stats(payload)
                if not valid: return False, res
                DataManager.insert_channel_stats(
                    res["chan_id"], res["c_code"], res["rank"], res["sub"],
                    res["views"], res["uploads"], res["dt_val"], res["v30"], res["s30"]
                )
                return True, "Channel Stats record created successfully."

            elif table == "Trending Record":
                valid, res = cls.validate_trending_record(payload)
                if not valid: return False, res
                DataManager.insert_trending_record(
                    res["rec_id"], res["vid_id"], res["c_code"], res["t_date"],
                    res["views"], res["likes"], res["dislikes"], res["comments"]
                )
                return True, f"Trending Record #{res['rec_id']} added successfully."

            elif table == "Revenue Record":
                valid, res = cls.validate_revenue_record(payload)
                if not valid: return False, res
                DataManager.insert_mongo_revenue(res)
                return True, f"MongoDB Revenue Record for '{res['video_id']}' created successfully."

            return False, "Unsupported target table specified."
        except Exception as e:
            return False, f"Database insert failure: {str(e)}"

    @classmethod
    def execute_delete(cls, table, identifier):
        if not identifier:
            return False, "Primary key identifier must be provided."
        try:
            if table == "Revenue Record":
                success = DataManager.delete_mongo_revenue(identifier)
            else:
                success = DataManager.delete_record(table, identifier)
            return (True, f"Record '{identifier}' deleted.") if success else (False, "Record not found.")
        except Exception as e:
            return False, f"Integrity error: {str(e)}"