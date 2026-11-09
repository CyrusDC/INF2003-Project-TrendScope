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
    columns = []
    records = []
    error = None
    try:
        df = DataManager.fetch_analytical_view(view_type)
        if not df.empty:
            columns = df.columns.tolist()
            records = df.to_dict(orient="records")
    except Exception as e:
        error = f"Error executing analytical view: {str(e)}"
        
    return render_template(
        "dashboard.html",
        columns=columns,
        records=records,
        current_view=view_type,
        error=error
    )

@app.route("/crud", methods=["GET", "POST"])
@login_required
@admin_required
def crud():
    search_results = None
    role = session.get("role")

    if request.method == "POST":
        action = request.form.get("action")

        # Admin-facing lookup by primary key
        if action == "read" and role == "admin":
            table = request.form.get("table")
            identifier = request.form.get("identifier")

            try:
                df = LogicManager.read_record(table, identifier)

                search_results = (
                    df.to_html(classes="table table-bordered mt-3", index=False)
                    if not df.empty
                    else "No matching record found."
                )
            except ValueError as e:
                flash(str(e), "warning")

            except Exception:
                app.logger.exception("Record lookup failed")
                flash(
                    "Unable to retrieve the record. Please try again.",
                    "danger"
                )

        # Admin-only mutations
        elif action in ["insert", "delete", "bulk_insert"]:
            if not LogicManager.verify_role_access(role, "admin"):
                flash("Unauthorized operation attempt blocked.", "danger")
                return redirect(url_for("crud"))

            if action == "insert":
                table = request.form.get("table")
                success, msg = LogicManager.execute_insert(table, request.form)
                flash(msg, "success" if success else "danger")

            elif action == "bulk_insert":
                table = request.form.get("table")
                file = request.files.get("dataset_file")

                if not file or file.filename == "":
                    flash(
                        "Please select a valid dataset file "
                        "(.csv or .json) to upload.",
                        "warning"
                    )
                else:
                    success, msg = LogicManager.execute_bulk_insert(
                        table, file
                    )
                    flash(msg, "success" if success else "danger")

            elif action == "delete":
                table = request.form.get("table")
                identifier = request.form.get("identifier")
                success, msg = LogicManager.execute_delete(
                    table, identifier
                )
                flash(msg, "success" if success else "danger")

    return render_template("crud.html", search_results=search_results)

# ------------------------------------------------------------------
# VIDEO KEYWORD SEARCH (VIEWER & ADMIN)
# ------------------------------------------------------------------
@app.route("/search", methods=["GET"])
@login_required
def search_videos():
    keyword = request.args.get("keyword", "").strip()
    country = request.args.get("country", "all")
    category = request.args.get("category", "all")
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    
    videos = []
    error = None
    categories = []
    countries = []

    try:
        categories, countries = LogicManager.get_filter_dropdown_options()
        
        # Run search if any filter parameter is specified
        if keyword or country != "all" or category != "all" or start_date or end_date:
            df = LogicManager.explore_trending_videos(
                keyword=keyword,
                country=country,
                category_id=category,
                start_date=start_date or None,
                end_date=end_date or None
            )
            videos = df.to_dict(orient="records")
    except Exception as e:
        app.logger.exception("Video search failed")
        error = f"Search query failed: {str(e)}"

    return render_template(
        "search.html",
        keyword=keyword,
        selected_country=country,
        selected_category=category,
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        countries=countries,
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

    # 1. ALWAYS populate dropdown options for video pickers
    video_options = []
    channel_options = []
    video_error = None
    channel_error = None

    try:
        video_options = LogicManager.get_revenue_video_options()
    except Exception as e:
        app.logger.exception("Could not load video picker options")
        video_error = f"Could not load the video list: {e}"

    try:
        channel_options = LogicManager.get_revenue_channel_options()
    except Exception as e:
        app.logger.exception("Could not load channel picker options")
        channel_error = f"Could not load the channel list: {e}"

    selected_video = request.args.get('video_id', '').strip()
    selected_channel = request.args.get('channel_id', '').strip()
    video_comparison = None
    channel_comparison = None

    # Head-to-Head Video Comparison variables
    video_a = request.args.get('video_a', '').strip()
    video_b = request.args.get('video_b', '').strip()
    head_to_head = None
    head_to_head_error = None

    try:
        if action == 'tier':
            df = LogicManager.filter_by_creator_tier(tier=selected_tier)
            results = df.to_dict(orient="records")

            if results:
                video_map, channel_map, category_map = LogicManager.get_metadata_lookup_maps()
                for item in results:
                    v_id = item.get("video_id")
                    c_id = item.get("channel_id")
                    cat_id = item.get("category_id")

                    item["video_title"] = video_map.get(v_id, f"Video {v_id}")
                    item["channel_name"] = channel_map.get(c_id, f"Channel {c_id}")
                    item["category_name"] = category_map.get(cat_id, f"Category {cat_id}")

        elif action == 'country':
            df = LogicManager.aggregate_revenue_by_country()
            results = df.to_dict(orient="records")

        elif action == 'categories':
            df = LogicManager.aggregate_category_breakdown()
            results = df.to_dict(orient="records")
            if results:
                try:
                    _, _, category_map = LogicManager.get_metadata_lookup_maps()
                    for item in results:
                        cat_id = item.get("category_id") or item.get("_id")
                        item["category_name"] = category_map.get(int(cat_id) if cat_id is not None else None, f"Category {cat_id}")
                except Exception as ex:
                    print(f"Error enriching categories: {ex}")

        elif action == 'compare':
            df = LogicManager.compare_creator_tiers()
            results = df.to_dict(orient="records")

            # Execute Head-to-Head Comparison if both videos are supplied
            if video_a and video_b:
                try:
                    head_to_head = LogicManager.compare_two_videos(video_a, video_b)
                except ValueError as e:
                    head_to_head_error = str(e)
                except Exception as e:
                    app.logger.exception("Head-to-head comparison failed")
                    head_to_head_error = f"Comparison failed: {e}"

        elif action == 'claims':
            policy = request.args.get('policy', 'all')
            outcome = request.args.get('outcome', 'all')
            df = LogicManager.get_copyright_claims_summary(policy_filter=policy, outcome_filter=outcome)
            results = df.to_dict(orient="records")

    except Exception as e:
        error = f"Database error: {str(e)}"

    return render_template(
        'video_revenue.html',
        action_type=action,
        selected_tier=selected_tier,
        results=results,
        selected_policy=request.args.get('policy', 'all'),
        selected_outcome=request.args.get('outcome', 'all'),
        video_options=video_options,
        selected_video=selected_video,
        video_comparison=video_comparison,
        video_error=video_error,
        channel_options=channel_options,
        selected_channel=selected_channel,
        channel_comparison=channel_comparison,
        channel_error=channel_error,
        video_a=video_a,
        video_b=video_b,
        head_to_head=head_to_head,
        head_to_head_error=head_to_head_error,
        error=error
    )

@app.route('/api/video-stats/<video_id>', methods=['GET'])
def get_video_stats(video_id):
    stats = LogicManager.get_video_stats_by_id(video_id)
    if not stats:
        return {"error": "Video not found"}, 404

    try:
        video_map, channel_map, category_map = LogicManager.get_metadata_lookup_maps()
        stats["video_title"] = video_map.get(stats.get("video_id"), "Unknown Title")
        stats["channel_name"] = channel_map.get(stats.get("channel_id"), "Unknown Channel")
        stats["category_name"] = category_map.get(stats.get("category_id"), "Unknown Category")
    except Exception:
        pass

    return stats

# ------------------------------------------------------------------
# PERFORMANCE BENCHMARK VIEW
# ------------------------------------------------------------------
@app.route("/benchmark", methods=["GET", "POST"])
@login_required
def benchmark():
    results = None
    if request.method == "POST":
        try:
            from benchmark import run_benchmarks
            df = run_benchmarks(iterations=10) # 10 runs for fast UI response
            results = df.to_dict(orient="records")
            flash("Benchmark run completed successfully!", "success")
        except Exception as e:
            flash(f"Benchmark run failed: {str(e)}", "danger")

    return render_template("benchmark.html", results=results)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)