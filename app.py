import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from data_manager import DataManager
from logic_manager import LogicManager

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_dev_secret")

# ------------------------------------------------------------------
# SESSION & ROLE MIDDLEWARE
# ------------------------------------------------------------------
def login_required(func):
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please authenticate to access the application.", "warning")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

def admin_required(func):
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Access denied: Administrative privileges required.", "danger")
            return redirect(url_for("dashboard"))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# ------------------------------------------------------------------
# AUTHENTICATION ROUTES
# ------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form.get("username", "")
        pwd = request.form.get("password", "")
        success, role = LogicManager.authenticate(user, pwd)
        if success:
            session["user"] = user
            session["role"] = role
            flash(f"Logged in as {user} ({role} role)", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials supplied.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Successfully signed out.", "info")
    return redirect(url_for("login"))

# ------------------------------------------------------------------
# APPLICATION VIEWS
# ------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    view_type = request.args.get("view", "category_views")
    try:
        df = DataManager.fetch_analytical_view(view_type)
        html_table = df.to_html(classes="table table-striped table-hover align-middle", index=False)
    except Exception as e:
        html_table = f"<p class='text-danger'>Error executing analytical view: {str(e)}</p>"
    return render_template("dashboard.html", table=html_table, current_view=view_type)

@app.route("/crud", methods=["GET", "POST"])
@login_required
def crud():
    search_results = None
    if request.method == "POST":
        action = request.form.get("action")

        # Read operation (Viewer & Admin allowed)
        if action == "read":
            table = request.form.get("table")
            identifier = request.form.get("identifier")
            df = DataManager.read_record(table, identifier)
            search_results = df.to_html(classes="table table-bordered mt-3", index=False) if not df.empty else "No matching record found."

        # Create/Delete operations (Admin only)
        elif action in ["insert", "delete"]:
            if not LogicManager.verify_role_access(session.get("role"), "admin"):
                flash("Unauthorized operation attempt blocked.", "danger")
                return redirect(url_for("crud"))

            if action == "insert":
                table = request.form.get("table")
                success, msg = LogicManager.execute_insert(table, request.form)
                flash(msg, "success" if success else "danger")

            elif action == "delete":
                table = request.form.get("table")
                identifier = request.form.get("identifier")
                success, msg = LogicManager.execute_delete(table, identifier)
                flash(msg, "success" if success else "danger")

    return render_template("crud.html", search_results=search_results)

# ------------------------------------------------------------------
# VIDEO KEYWORD SEARCH (VIEWER & ADMIN)
# ------------------------------------------------------------------

@app.route("/search", methods=["GET"])
@login_required
def search_videos():

    # Get keyword entered in HTML search bar
    keyword = request.args.get("keyword", "").strip()

    # Initialise results
    videos = []
    error = None

    if keyword:
        try:
            # Search PostgreSQL using DataManager
            df = DataManager.search_videos_with_keyword(keyword)

            # Convert DataFrame into dictionaries for HTML
            videos = df.to_dict(orient="records")

        except Exception:
            app.logger.exception("Video keyword search failed")
            error = "Unable to search videos. Please try again."

    # Display results in search.html
    return render_template(
        "search.html",
        keyword=keyword,
        videos=videos,
        error=error
    )

# ------------------------------------------------------------------
# MONGODB REVENUE ANALYTICS (VIEWER & ADMIN)
# ------------------------------------------------------------------

@app.route('/video-revenue', methods=['GET'])
def video_revenue():
    action = request.args.get('action')
    selected_tier = request.args.get('selected_tier', 'large')
    results = []
    error = None

    try:
        if action == 'tier':
            # 1. Fetch raw tier data from MongoDB
            df = DataManager.filter_by_creator_tier(tier=selected_tier)
            results = df.to_dict(orient="records")

            # 2. Cross-reference PostgreSQL for Titles and Names
            if results:
                video_map, channel_map, category_map = DataManager.get_metadata_lookup_maps()
                for item in results:
                    v_id = item.get("video_id")
                    c_id = item.get("channel_id")
                    cat_id = item.get("category_id")

                    # Attach readable names from PostgreSQL (fallback to ID if not found)
                    item["video_title"] = video_map.get(v_id, f"Video {v_id}")
                    item["channel_name"] = channel_map.get(c_id, f"Channel {c_id}")
                    item["category_name"] = category_map.get(cat_id, f"Category {cat_id}")

        elif action == 'country':
            df = DataManager.aggregate_revenue_by_country()
            results = df.to_dict(orient="records")

        elif action == 'categories':
            df = DataManager.aggregate_category_breakdown()
            results = df.to_dict(orient="records")
            
            # Enrich with PostgreSQL Category Names while preserving counts
            if results:
                try:
                    _, _, category_map = DataManager.get_metadata_lookup_maps()
                    for item in results:
                        cat_id = item.get("category_id") or item.get("_id")
                        # Match integer key with postgres map
                        item["category_name"] = category_map.get(int(cat_id) if cat_id is not None else None, f"Category {cat_id}")
                except Exception as ex:
                    print(f"Error enriching categories: {ex}")

        elif action == 'compare':
            df = DataManager.compare_creator_tiers()
            results = df.to_dict(orient="records")

    except Exception as e:
        error = f"Database error: {str(e)}"

    return render_template(
        'video_revenue.html',
        action_type=action,
        selected_tier=selected_tier,
        results=results,
        error=error
    )

@app.route('/api/video-stats/<video_id>', methods=['GET'])
def get_video_stats(video_id):
    stats = DataManager.get_video_stats_by_id(video_id)
    if not stats:
        return {"error": "Video not found"}, 404

    # Cross-reference Postgres for titles
    try:
        video_map, channel_map, category_map = DataManager.get_metadata_lookup_maps()
        stats["video_title"] = video_map.get(stats.get("video_id"), "Unknown Title")
        stats["channel_name"] = channel_map.get(stats.get("channel_id"), "Unknown Channel")
        stats["category_name"] = category_map.get(stats.get("category_id"), "Unknown Category")
    except Exception:
        pass

    return stats

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)