from flask import Flask, render_template, request, redirect, flash, session
import sqlite3
import os
import re
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import math
from flask import jsonify
from datetime import datetime
import requests
import random
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from random import uniform

app = Flask(__name__)
app.secret_key = 'secret_key'

DB_PATH = "users.db"

# CREATE DATABASES AND TABLES
def init_databases():
    if not os.path.exists(DB_PATH):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute('''
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    firstname TEXT NOT NULL,
                    lastname TEXT NOT NULL,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL
                );
            ''')

    # Initialize readings.db
    if not os.path.exists("readings.db"):
        with sqlite3.connect("readings.db") as conn:
            conn.execute('''
                CREATE TABLE readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT CHECK(source IN ('inside','outside')) NOT NULL,
                    temperature REAL NOT NULL,
                    humidity REAL NOT NULL,
                    apparent REAL NOT NULL
                );
            ''')

    # CREATE settings.db WITH THRESHOLDS TABLE
    if not os.path.exists("settings.db"):
        with sqlite3.connect("settings.db") as conn:
            # Create thresholds table
            conn.execute('''
                CREATE TABLE thresholds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    temperature_from REAL NOT NULL,
                    temperature_to REAL NOT NULL,
                    threshold_level TEXT NOT NULL
                );
            ''')
            # Insert default threshold ranges
            conn.executemany('''
                INSERT INTO thresholds (temperature_from, temperature_to, threshold_level)
                VALUES (?, ?, ?)
            ''', [
                (18, 26, 'Safe'),
                (26, 30, 'Moderate Risk'),
                (30, 35, 'High Risk'),
                (35, 100, 'Very High Risk')
            ])

            # Create settings table (if you need it)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    safe_threshold REAL NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            ''')
            conn.execute('''
                INSERT OR IGNORE INTO settings (id, safe_threshold, updated_by, updated_at)
                VALUES (1, 34.0, 'system', ?)
            ''', (datetime.now().isoformat(),))
    else:
        # If settings.db exists but thresholds table doesn't
        with sqlite3.connect("settings.db") as conn:
            # Check if thresholds table exists
            table_exists = conn.execute('''
                SELECT count(*) FROM sqlite_master 
                WHERE type='table' AND name='thresholds'
            ''').fetchone()[0]

            if not table_exists:
                # Create thresholds table if it doesn't exist
                conn.execute('''
                    CREATE TABLE thresholds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        temperature_from REAL NOT NULL,
                        temperature_to REAL NOT NULL,
                        threshold_level TEXT NOT NULL
                    );
                ''')
                # Insert default threshold ranges
                conn.executemany('''
                    INSERT INTO thresholds (temperature_from, temperature_to, threshold_level)
                    VALUES (?, ?, ?)
                ''', [
                    (18, 26, 'Safe'),
                    (26, 30, 'Moderate Risk'),
                    (30, 35, 'High Risk'),
                    (35, 100, 'Very High Risk')
                ])


# Call the initialization function at startup
init_databases()

# REGEX FOR PASSWORD VALIDATION
PASSWORD_REGEX = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$'
)

# ROUTES
@app.route("/")
def index():
    return redirect("/signin")

# Route for handling the sign-in page
@app.route("/signin", methods=["GET", "POST"])
def signin():
    # Handle form submission
    if request.method == "POST":
        # Get and clean form input
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        # Validate that both fields are filled
        if not email or not password:
            flash("Both fields are required.", "danger")  # Show error message
            return render_template("signin.html", form=request.form)  # Keep user's input
        # Connect to the SQLite database
        with sqlite3.connect(DB_PATH) as conn:
            # Query the user with the given email
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        # If no user found with the given email
        if user is None:
            flash("Account not found. Check your email.", "danger")
            return render_template("signin.html", form=request.form)
        # Extract the stored hashed password (assumes it's at index 5)
        hashed_password = user[5]
        # Verify the entered password against the hashed one
        if not check_password_hash(hashed_password, password):
            flash("Incorrect password.", "danger")
            return render_template("signin.html", form=request.form)
        # If credentials are valid, store session variables
        session["user_id"] = user[0]      # Store user's ID
        session["username"] = user[3]     # Store user's username
        flash(f"Welcome back, {user[1]}!", "success")  # Show welcome message using first name
        # Redirect to main application page
        return redirect("/dashboard")
    # If request method is GET, render sign-in form with empty values
    return render_template("signin.html", form={})



# Route for logging the user out
@app.route("/logout")
def logout():
    session.clear()  # Clears all session data (user_id, username, etc.)
    flash("Logged out successfully.", "success")  # Display logout message
    return redirect("/signin")  # Redirect to the sign-in page


# Route to ingest weather data from BOM for "outside" source
@app.route("/ingest/outside", methods=["POST"])
def ingest_outside():
    try:
        # URL to fetch BOM JSON weather data for a specific station
        url = "http://reg.bom.gov.au/fwo/IDQ60901/IDQ60901.94576.json"
        response = requests.get(url, timeout=10)  # Make a GET request with 10s timeout
        response.raise_for_status()  # Raise exception for HTTP errors
        bom_data = response.json()  # Parse the response as JSON
    except Exception as e:
        # Catch network or JSON parsing errors
        return jsonify({"error": f"Failed to fetch BOM data: {str(e)}"}), 500
    try:
        # Access the latest observation (first item in data array)
        latest = bom_data["observations"]["data"][0]
        temp = float(latest["air_temp"])             # Current air temperature
        rh = float(latest["rel_hum"])                # Relative humidity
        ts_raw = latest["local_date_time_full"]      # Raw timestamp string (e.g., 20250711143000)
        # Convert raw timestamp to ISO 8601 format (e.g., "2025-07-11T14:30:00")
        timestamp = datetime.strptime(ts_raw, "%Y%m%d%H%M%S").isoformat()
    except (KeyError, ValueError, IndexError) as e:
        # Catch missing fields or formatting issues
        return jsonify({"error": f"Invalid BOM data structure: {str(e)}"}), 500
    # Compute apparent temperature using custom formula
    apparent = calc_apparent(temp, rh)
    # Store data into SQLite database if the timestamp doesn't already exist
    with sqlite3.connect("readings.db") as conn:
        # Check if this exact timestamp already exists for 'outside'
        exists = conn.execute('''
            SELECT 1 FROM readings 
            WHERE timestamp = ? AND source = 'outside'
        ''', (timestamp,)).fetchone()
        if not exists:
            # Insert the new reading into the database
            conn.execute('''
                INSERT INTO readings (timestamp, source, temperature, humidity, apparent)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, "outside", temp, rh, apparent))
            message = "New external data ingested"
        else:
            # Skip insertion if data already exists
            message = "Data already exists (not stored)"
    # Return a JSON response with summary
    return jsonify({
        "message": message,
        "timestamp": timestamp,
        "temperature": temp,
        "humidity": rh,
        "apparent": apparent
    }), 201

# Route for displaying the dashboard page
@app.route("/dashboard")
def dashboard():
    # Connect to readings database and fetch the latest "inside" reading
    with sqlite3.connect("readings.db") as conn:
        inside = conn.execute('''
            SELECT timestamp, temperature, humidity, apparent
            FROM readings
            WHERE source = 'inside'
            ORDER BY timestamp DESC
            LIMIT 1
        ''').fetchone()

        # Fetch the latest "outside" reading
        outside = conn.execute('''
            SELECT timestamp, temperature, humidity, apparent
            FROM readings
            WHERE source = 'outside'
            ORDER BY timestamp DESC
            LIMIT 1
        ''').fetchone()

    # Get the maximum safe apparent temperature from thresholds table
    threshold = get_threshold()

    # Logic to determine if an alert should be shown
    alert = None
    if inside and inside[3] > threshold:
        # inside[3] is the apparent temperature
        alert = "⚠️ Internal Apparent Temperature is above safe threshold!"
    elif outside and outside[3] > threshold:
        alert = "⚠️ External Apparent Temperature is above safe threshold!"
    else:
        alert = "✅ No critical warning or alert at this point."

    # Render dashboard template with latest readings and alert message
    return render_template("dashboard.html", inside=inside, outside=outside, alert=alert)


# Helper function to get the "safe" temperature threshold
def get_threshold():
    with sqlite3.connect("settings.db") as conn:
        cursor = conn.execute('''
            SELECT temperature_from, temperature_to, threshold_level
            FROM thresholds
            ORDER BY temperature_from ASC
        ''')
        thresholds = cursor.fetchall()
    # Find and return the upper bound (temperature_to) for the "safe" range
    for row in thresholds:
        if row[2].lower() == "safe":  # threshold_level
            return row[1]  # Return temperature_to as the upper safe limit

    # Default fallback threshold if "Safe" is not found
    return 26

@app.route("/temperature-log")
def temperature_log():
    with sqlite3.connect("readings.db") as conn:
        # Enable dictionary-style access for rows (e.g., row['temperature'])
        conn.row_factory = sqlite3.Row
        # Query the 50 most recent internal (inside) readings
        internal = conn.execute('''
            SELECT timestamp, temperature, humidity, apparent
            FROM readings
            WHERE source = 'inside'
            ORDER BY timestamp DESC
            LIMIT 50
        ''').fetchall()
        # Query the 50 most recent external (outside) readings
        external = conn.execute('''
            SELECT timestamp, temperature, humidity, apparent
            FROM readings
            WHERE source = 'outside'
            ORDER BY timestamp DESC
            LIMIT 50
        ''').fetchall()
    # Pass both datasets to the temperature_log.html template for display
    return render_template("temperature_log.html", internal=internal, external=external)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fname = request.form.get("firstname", "").strip()
        lname = request.form.get("lastname", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        role = request.form.get("role", "").strip()
        errors = []
        if not all([fname, lname, username, email, password, confirm, role]):
            errors.append("All fields are required.")
        # Check if password and confirmation match
        if password != confirm:
            errors.append("Passwords do not match.")
        # Validate password strength using a regular expression
        if not PASSWORD_REGEX.match(password):
            errors.append("Password must be at least 8 characters, with upper-case, lower-case, and a number.")
        # Validate role
        if role not in ["worker", "manager", "supervisor"]:
            errors.append("Invalid role selected.")
        # Check for existing user with the same username or email
        with sqlite3.connect(DB_PATH) as conn:
            existing_user = conn.execute(
                "SELECT * FROM users WHERE username = ? OR email = ?", (username, email)
            ).fetchone()
            if existing_user:
                errors.append("Username or email already exists.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("signup.html", form={**request.form})
        hashed_pw = generate_password_hash(password)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO users (firstname, lastname, username, email, password, role) VALUES (?, ?, ?, ?, ?, ?)",
                (fname, lname, username, email, hashed_pw, role)
            )
        flash("Signup successful. You can now log in.", "success")
        return redirect("/signup")
    return render_template("signup.html", form={})


@app.route("/simulate/internal", methods=["POST"])
def simulate_internal():
    # Simulate a base internal temperature (e.g., factory environment)
    base_temp = random.uniform(28.0, 35.0)  # base temperature range in °C
    temp_variation = random.uniform(-1.0, 1.0)  # small variation to add realism
    humidity = random.uniform(45.0, 60.0)  # simulated relative humidity (%)

    # Combine base temperature and variation to get the final simulated value
    temp = base_temp + temp_variation

    # Calculate apparent temperature using a helper function
    apparent = calc_apparent(temp, humidity)

    # Generate a current timestamp in ISO 8601 format (e.g., "2025-07-11T15:35:22")
    timestamp = datetime.now().isoformat()

    # Store the simulated reading into the database as an "inside" source
    with sqlite3.connect("readings.db") as conn:
        conn.execute('''
            INSERT INTO readings (timestamp, source, temperature, humidity, apparent)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, "inside", temp, humidity, apparent))

    # Return a JSON response confirming the simulation and showing the values
    return jsonify({
        "message": "Simulated internal data added",
        "timestamp": timestamp,
        "temperature": temp,
        "humidity": humidity,
        "apparent": apparent
    }), 201  # HTTP 201 Created

@app.route("/threshold", methods=["GET", "POST"])
def threshold_page():
    user_role = None
    if "user_id" in session:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute("SELECT role FROM users WHERE id = ?", (session["user_id"],))
            row = cursor.fetchone()
            if row:
                user_role = row[0]
    # Handle POST only if user is manager or supervisor
    if request.method == "POST":
        if user_role not in ("supervisor", "manager"):
            flash("You do not have permission to update thresholds.", "danger")
            return redirect("/threshold")
        try:
            thresholds = []
            previous_to = None
            for i in range(4):
                t_from = float(request.form.get(f"from_{i}"))
                t_to = float(request.form.get(f"to_{i}"))
                label = request.form.get(f"label_{i}")
                if t_from >= t_to:
                    flash("'From' temperature must be less than 'To' temperature", "danger")
                    return redirect("/threshold")
                if previous_to is not None and t_from != previous_to:
                    flash("Temperature ranges must be continuous (end of one range equals start of next)", "danger")
                    return redirect("/threshold")
                thresholds.append({"from": t_from, "to": t_to, "label": label})
                previous_to = t_to
            with sqlite3.connect("settings.db") as conn:
                conn.execute("DELETE FROM thresholds")
                conn.executemany('''
                    INSERT INTO thresholds (temperature_from, temperature_to, threshold_level)
                    VALUES (?, ?, ?)
                ''', [(t["from"], t["to"], t["label"]) for t in thresholds])
            flash("Thresholds updated successfully!", "success")
        except ValueError:
            flash("Please enter valid temperature values", "danger")
            return redirect("/threshold")

    # If GET or after POST, fetch current thresholds
    try:
        with sqlite3.connect("settings.db") as conn:
            conn.row_factory = sqlite3.Row
            thresholds = conn.execute('''
                SELECT temperature_from as "from", temperature_to as "to", threshold_level as "label"
                FROM thresholds
                ORDER BY temperature_from ASC
            ''').fetchall()

            if not thresholds:
                thresholds = [
                    {"from": 18, "to": 26, "label": "Safe"},
                    {"from": 26, "to": 30, "label": "Moderate Risk"},
                    {"from": 30, "to": 35, "label": "High Risk"},
                    {"from": 35, "to": 100, "label": "Very High Risk"}
                ]

        return render_template("threshold.html", thresholds=thresholds, user_role=user_role)

    except sqlite3.OperationalError:
        return render_template("threshold.html", thresholds=[
            {"from": 18, "to": 26, "label": "Safe"},
            {"from": 26, "to": 30, "label": "Moderate Risk"},
            {"from": 30, "to": 35, "label": "High Risk"},
            {"from": 35, "to": 100, "label": "Very High Risk"}
        ], user_role=user_role)


@app.route("/threshold", methods=["POST"])
def update_thresholds():
    updated = []
    for i in range(4):
        t_from = float(request.form.get(f"from_{i}"))  # Lower bound of range
        t_to = float(request.form.get(f"to_{i}"))      # Upper bound of range
        label = request.form.get(f"label_{i}")         # Risk level label (e.g. Safe, High Risk)
        updated.append((t_from, t_to, label))          # Store tuple for future use (e.g., database)

    flash("Thresholds updated successfully!", "success")
    return redirect("/threshold")  # Redirect back to the threshold page


def calc_apparent(temp: float, rh: float) -> float:
    """
    Calculates apparent temperature based on temp (°C) and relative humidity (%),
    using formula provided in IA3 stimulus.
    """
    # Calculate water vapor pressure (rho) using a standard humidity formula
    rho = (rh / 100.0) * 6.105 * math.exp((17.27 * temp) / (237.7 + temp))

    # Apparent temperature formula: real temp adjusted by humidity effect
    apparent = temp + 0.33 * rho - 4

    return round(apparent, 1)  # Round to 1 decimal place for display

@app.context_processor
def utility_processor():
    def get_threshold_value():
        # Fetch the "Safe" upper bound from database
        with sqlite3.connect("settings.db") as conn:
            cursor = conn.execute('''
                SELECT temperature_to FROM thresholds 
                WHERE threshold_level = 'Safe'
                ORDER BY temperature_from ASC
                LIMIT 1
            ''')
            return cursor.fetchone()[0] if cursor else 26  # Default fallback is 26°C

    # Makes get_threshold() available in all Jinja templates
    return dict(get_threshold=get_threshold_value)

@app.route("/ingest/inside", methods=["POST"])
def ingest_inside():
    # Expect JSON data from the client
    data = request.get_json()

    # If no JSON provided, return error
    if not data:
        return jsonify({"error": "Missing JSON data"}), 400

    try:
        # Extract temperature and humidity from JSON
        temp = float(data["temperature"])
        rh = float(data["humidity"])
    except (KeyError, ValueError):
        # Return error if fields are missing or not numeric
        return jsonify({"error": "Invalid or missing fields"}), 400

    # Calculate apparent temperature based on provided inputs
    apparent = calc_apparent(temp, rh)

    # Use current timestamp for the reading
    timestamp = datetime.now().isoformat()

    # Insert the reading into the 'readings' database under source = 'inside'
    with sqlite3.connect("readings.db") as conn:
        conn.execute('''
            INSERT INTO readings (timestamp, source, temperature, humidity, apparent)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, "inside", temp, rh, apparent))

    # Respond with confirmation and inserted values
    return jsonify({
        "message": "Internal data ingested successfully",
        "timestamp": timestamp,
        "temperature": temp,
        "humidity": rh,
        "apparent": apparent
    }), 201  # HTTP 201 Created

def load_historical_bom_data():
    try:
        # BOM JSON feed URL for Brisbane Airport
        url = "http://reg.bom.gov.au/fwo/IDQ60901/IDQ60901.94576.json"
        response = requests.get(url, timeout=10)  # Timeout after 10s
        response.raise_for_status()
        bom_data = response.json()

        with sqlite3.connect("readings.db") as conn:
            # Insert last 24 hours of data (assume 48 half-hourly entries)
            for reading in bom_data["observations"]["data"][:48]:
                try:
                    # Extract raw data
                    temp = float(reading["air_temp"])
                    rh = float(reading["rel_hum"])
                    ts_raw = reading["local_date_time_full"]

                    # Convert raw timestamp to ISO format
                    timestamp = datetime.strptime(ts_raw, "%Y%m%d%H%M%S").isoformat()
                    apparent = calc_apparent(temp, rh)

                    # Only insert if not already in the DB (prevent duplication)
                    exists = conn.execute('''
                        SELECT 1 FROM readings 
                        WHERE timestamp = ? AND source = 'outside'
                    ''', (timestamp,)).fetchone()

                    if not exists:
                        conn.execute('''
                            INSERT INTO readings (timestamp, source, temperature, humidity, apparent)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (timestamp, "outside", temp, rh, apparent))

                except (KeyError, ValueError):
                    continue  # Skip malformed entries

        print("Loaded historical BOM data successfully")

    except Exception as e:
        # Print error (used instead of flash/log due to early-stage script execution)
        print(f"Error loading historical data: {str(e)}")

# Call this once to populate initial data
load_historical_bom_data()

def simulate_factory_conditions():
    with app.app_context():
        # Randomly simulate internal environment like a hot factory
        temp = random.uniform(28.0, 38.0)
        humidity = random.uniform(40.0, 65.0)
        apparent = calc_apparent(temp, humidity)
        timestamp = datetime.now().isoformat()

        # Insert the simulated reading
        with sqlite3.connect("readings.db") as conn:
            conn.execute('''
                INSERT INTO readings (timestamp, source, temperature, humidity, apparent)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, "inside", temp, humidity, apparent))

# Start scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(simulate_factory_conditions, 'interval', minutes=5)
scheduler.start()

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
