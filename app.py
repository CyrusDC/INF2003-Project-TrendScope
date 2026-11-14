import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash

from logic_manager import LogicManager

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_dev_secret")


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please authenticate to access the application.", "warning")
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Access denied: Administrative privileges required.", "danger")
            return redirect(url_for("dashboard"))
        return func(*args, **kwargs)
    return wrapper


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


@app.route("/")
@login_required
def dashboard():
    view_type = request.args.get("view", "category_views")
    columns, records, error = [], [], None
    try:
        columns, records = LogicManager.get_analytical_view(view_type)
    except Exception as e:
        error = f"Error executing analytical view: {e}"

    return render_template(
        "dashboard.html",
        columns=columns,
        records=records,
        current_view=view_type,
        error=error,
    )


# Admin-only page. One form per action, and the hidden "action" field says which one was submitted.
@app.route("/crud", methods=["GET", "POST"])
@login_required
@admin_required
def crud():
    search_results = None

    if request.method == "POST":
        action = request.form.get("action")
        table = request.form.get("table")

        if action == "read":
            try:
                df = LogicManager.read_record(table, request.form.get("identifier"))
                if df.empty:
                    search_results = "No matching record found."
                else:
                    search_results = df.to_html(classes="table table-bordered mt-3", index=False)
            except ValueError as e:
                flash(str(e), "warning")
            except Exception:
                app.logger.exception("Record lookup failed")
                flash("Unable to retrieve the record. Please try again.", "danger")

        elif action == "insert":
            success, msg = LogicManager.execute_insert(table, request.form)
            flash(msg, "success" if success else "danger")

        elif action == "bulk_insert":
            file = request.files.get("dataset_file")
            if not file or file.filename == "":
                flash("Please select a valid dataset file (.csv or .json) to upload.", "warning")
            else:
                success, msg = LogicManager.execute_bulk_insert(table, file)
                flash(msg, "success" if success else "danger")

        elif action == "delete":
            success, msg = LogicManager.execute_delete(table, request.form.get("identifier"))
            flash(msg, "success" if success else "danger")

    return render_template("crud.html", search_results=search_results)


@app.route("/search", methods=["GET"])
@login_required
def search_videos():
    keyword = request.args.get("keyword", "").strip()
    country = request.args.get("country", "all")
    category = request.args.get("category", "all")
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    videos, categories, countries, error = [], [], [], None
    try:
        categories, countries = LogicManager.get_filter_dropdown_options()

        # Opening the page with no filters shows just the form, not the whole table
        if keyword or country != "all" or category != "all" or start_date or end_date:
            df = LogicManager.explore_trending_videos(
                keyword=keyword,
                country=country,
                category_id=category,
                start_date=start_date,
                end_date=end_date,
            )
            videos = df.to_dict(orient="records")
    except ValueError as e:
        # A bad filter value from the user, not a crash
        error = f"Search query failed: {e}"
    except Exception as e:
        app.logger.exception("Video search failed")
        error = f"Search query failed: {e}"

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
        error=error,
    )


# MongoDB revenue page. The "action" query parameter picks which aggregation to run.
@app.route("/video-revenue", methods=["GET"])
@login_required
def video_revenue():
    action = request.args.get("action")
    selected_tier = LogicManager.clean_tier(request.args.get("selected_tier", "large"))
    policy = request.args.get("policy", "all")
    outcome = request.args.get("outcome", "all")
    video_a = request.args.get("video_a", "").strip()
    video_b = request.args.get("video_b", "").strip()

    results, error = [], None
    head_to_head, head_to_head_error = None, None

    # The video dropdowns are on the page whichever action is chosen
    video_options, video_error = [], None
    try:
        video_options = LogicManager.get_revenue_video_options()
    except Exception as e:
        app.logger.exception("Could not load video picker options")
        video_error = f"Could not load the video list: {e}"

    try:
        if action == "tier":
            results = LogicManager.filter_by_creator_tier(selected_tier)
        elif action == "country":
            results = LogicManager.aggregate_revenue_by_country()
        elif action == "categories":
            results = LogicManager.aggregate_category_breakdown()
        elif action == "claims":
            results = LogicManager.get_copyright_claims_summary(policy, outcome)
        elif action == "compare":
            results = LogicManager.compare_creator_tiers()

            # The head-to-head comparison only runs once both videos are picked
            if video_a and video_b:
                try:
                    head_to_head = LogicManager.compare_two_videos(video_a, video_b)
                except ValueError as e:
                    head_to_head_error = str(e)
                except Exception as e:
                    app.logger.exception("Head-to-head comparison failed")
                    head_to_head_error = f"Comparison failed: {e}"
    except Exception as e:
        error = f"Database error: {e}"

    return render_template(
        "video_revenue.html",
        action_type=action,
        selected_tier=selected_tier,
        results=results,
        selected_policy=policy,
        selected_outcome=outcome,
        video_options=video_options,
        video_error=video_error,
        video_a=video_a,
        video_b=video_b,
        head_to_head=head_to_head,
        head_to_head_error=head_to_head_error,
        error=error,
    )


# Called by the page's JavaScript to fill the video details pop-up
@app.route("/api/video-stats/<video_id>", methods=["GET"])
@login_required
def get_video_stats(video_id):
    stats = LogicManager.get_video_stats_by_id(video_id)
    if not stats:
        return {"error": "Video not found"}, 404
    return stats

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
