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

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)