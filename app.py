from flask import Flask, render_template, render_template_string, request, redirect, session, jsonify
from datetime import date, datetime, timedelta
import os
import tempfile

import psycopg2
from psycopg2.extras import RealDictCursor

import boto3
from boto3.s3.transfer import TransferConfig

from werkzeug.utils import secure_filename


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

app.secret_key = "student-study-planner-secret"

# Allow large uploads from browser
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024


# =========================================================
# DATABASE
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():

    if not DATABASE_URL:
        raise Exception(
            "DATABASE_URL is not configured in Render Environment."
        )

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


# =========================================================
# BACKBLAZE B2
# =========================================================

B2_KEY_ID = os.environ.get("B2_KEY_ID")
B2_APPLICATION_KEY = os.environ.get("B2_APPLICATION_KEY")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME")
B2_ENDPOINT = os.environ.get("B2_ENDPOINT")


def get_b2_client():

    if not B2_KEY_ID:
        raise Exception("B2_KEY_ID is not configured.")

    if not B2_APPLICATION_KEY:
        raise Exception("B2_APPLICATION_KEY is not configured.")

    if not B2_ENDPOINT:
        raise Exception("B2_ENDPOINT is not configured.")

    return boto3.client(
        "s3",
        endpoint_url=B2_ENDPOINT,
        region_name="us-east-005",
        aws_access_key_id=B2_KEY_ID,
        aws_secret_access_key=B2_APPLICATION_KEY
    )


# Multipart upload configuration
B2_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,
    multipart_chunksize=8 * 1024 * 1024,
    max_concurrency=4,
    use_threads=True
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db()
    cur = conn.cursor()

    # =====================================================
    # USERS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    # =====================================================
    # SUBJECTS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)

    # =====================================================
    # ASSIGNMENTS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    # =====================================================
    # EXAMS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            exam_date TEXT NOT NULL,
            exam_time TEXT NOT NULL
        )
    """)

    # =====================================================
    # TIMETABLE
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            study_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            topic TEXT NOT NULL
        )
    """)

    # =====================================================
    # STUDY TOPICS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS study_topics (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            topic TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        ALTER TABLE study_topics
        ADD COLUMN IF NOT EXISTS completed_at DATE
    """)

    # =====================================================
    # DAILY GOALS
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_goals (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            goal INTEGER DEFAULT 1
        )
    """)

    # =====================================================
    # PDF FILES
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pdf_files (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            subject TEXT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Old Cloudinary support
    cur.execute("""
        ALTER TABLE pdf_files
        ADD COLUMN IF NOT EXISTS public_id TEXT
    """)

    # New Backblaze object key
    cur.execute("""
        ALTER TABLE pdf_files
        ADD COLUMN IF NOT EXISTS storage_key TEXT
    """)

    # =====================================================
    # ACCOUNT-WISE DATA MIGRATION
    # =====================================================

    # Add username columns to old tables.
    # Existing old records will initially be NULL.
    # New records will always contain the logged-in username.

    cur.execute("""
        ALTER TABLE subjects
        ADD COLUMN IF NOT EXISTS username TEXT
    """)

    cur.execute("""
        ALTER TABLE assignments
        ADD COLUMN IF NOT EXISTS username TEXT
    """)

    cur.execute("""
        ALTER TABLE exams
        ADD COLUMN IF NOT EXISTS username TEXT
    """)

    cur.execute("""
        ALTER TABLE timetable
        ADD COLUMN IF NOT EXISTS username TEXT
    """)

    cur.execute("""
        ALTER TABLE study_topics
        ADD COLUMN IF NOT EXISTS username TEXT
    """)

    # =====================================================
    # TO-DO LIST
    # =====================================================

    cur.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_datetime TIMESTAMP,
            completed INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        ALTER TABLE todos
        ADD COLUMN IF NOT EXISTS notified INTEGER DEFAULT 0
    """)

    conn.commit()

    cur.close()
    conn.close()


init_db()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template("index.html")


# =========================================================
# SIGNUP
# =========================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        if not username or not password:

            return "Please enter username and password."

        conn = get_db()
        cur = conn.cursor()

        try:

            cur.execute("""
                INSERT INTO users
                (username, password)
                VALUES (%s, %s)
            """, (
                username,
                password
            ))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/login")

        except psycopg2.IntegrityError:

            conn.rollback()

            cur.close()
            conn.close()

            return "Username already exists!"

    return render_template("signup.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM users
            WHERE username = %s
            AND password = %s
        """, (
            username,
            password
        ))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:

            session["username"] = username

            return redirect("/dashboard")

        return "Invalid username or password!"

    return render_template("login.html")


# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        new_password = request.form.get(
            "new_password",
            ""
        ).strip()

        if not username or not new_password:

            return "Please enter username and new password."

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM users
            WHERE username = %s
        """, (username,))

        user = cur.fetchone()

        if user:

            cur.execute("""
                UPDATE users
                SET password = %s
                WHERE username = %s
            """, (
                new_password,
                username
            ))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/login")

        cur.close()
        conn.close()

        return "Username not found!"

    return render_template("forgot_password.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    # SUBJECT COUNT
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM subjects
        WHERE username = %s
    """, (username,))

    subjects_count = cur.fetchone()["count"]

    # PENDING ASSIGNMENTS
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM assignments
        WHERE username = %s
        AND completed = 0
    """, (username,))

    assignments_count = cur.fetchone()["count"]

    # EXAM COUNT
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM exams
        WHERE username = %s
    """, (username,))

    exams_count = cur.fetchone()["count"]

    # COMPLETED TOPICS
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM study_topics
        WHERE username = %s
        AND completed = 1
    """, (username,))

    completed_topics = cur.fetchone()["count"]

    # TOTAL TOPICS
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM study_topics
        WHERE username = %s
    """, (username,))

    total_topics = cur.fetchone()["count"]

    # TODAY
    today = date.today()

    # STUDY STREAK
    cur.execute("""
        SELECT DISTINCT completed_at
        FROM study_topics
        WHERE username = %s
        AND completed = 1
        AND completed_at IS NOT NULL
        ORDER BY completed_at DESC
    """, (username,))

    completed_dates = cur.fetchall()

    completed_date_set = set()

    for row in completed_dates:

        completed_at = row["completed_at"]

        if isinstance(completed_at, str):

            try:
                completed_at = datetime.strptime(
                    completed_at,
                    "%Y-%m-%d"
                ).date()

            except ValueError:
                continue

        completed_date_set.add(completed_at)

    streak = 0
    check_date = today

    while check_date in completed_date_set:

        streak += 1
        check_date -= timedelta(days=1)

    # DAILY STUDY GOAL
    cur.execute("""
        SELECT goal
        FROM daily_goals
        WHERE username = %s
    """, (username,))

    goal_data = cur.fetchone()

    daily_goal = (
        goal_data["goal"]
        if goal_data
        else 1
    )

    # TODAY COMPLETED
    cur.execute("""
        SELECT COUNT(*) AS count
        FROM study_topics
        WHERE username = %s
        AND completed = 1
        AND completed_at = %s
    """, (
        username,
        today
    ))

    today_completed = cur.fetchone()["count"]

    # PENDING ASSIGNMENTS
    cur.execute("""
        SELECT *
        FROM assignments
        WHERE username = %s
        AND completed = 0
        ORDER BY due_date
        LIMIT 5
    """, (username,))

    pending_assignments = cur.fetchall()

    # UPCOMING EXAMS
    cur.execute("""
        SELECT *
        FROM exams
        WHERE username = %s
        AND exam_date::date >= %s
        ORDER BY exam_date::date
        LIMIT 5
    """, (
        username,
        today
    ))

    upcoming_exams = cur.fetchall()

    # EXAM COUNTDOWN
    for exam in upcoming_exams:

        exam_day = exam["exam_date"]

        if isinstance(exam_day, str):

            exam_day = datetime.strptime(
                exam_day,
                "%Y-%m-%d"
            ).date()

        elif hasattr(exam_day, "date"):

            exam_day = exam_day.date()

        exam["days_left"] = (
            exam_day - today
        ).days

    # SUBJECT-WISE PROGRESS
    cur.execute("""
        SELECT
            subject,
            COUNT(*) AS total,
            SUM(completed) AS completed
        FROM study_topics
        WHERE username = %s
        GROUP BY subject
    """, (username,))

    progress_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dashboard.html",
        username=username,
        subjects_count=subjects_count,
        assignments_count=assignments_count,
        exams_count=exams_count,
        completed_topics=completed_topics,
        total_topics=total_topics,
        pending_assignments=pending_assignments,
        upcoming_exams=upcoming_exams,
        progress=progress_data,
        today=today.isoformat(),
        streak=streak,
        daily_goal=daily_goal,
        today_completed=today_completed
    )


# =========================================================
# DAILY STUDY GOAL
# =========================================================

@app.route("/daily_goal", methods=["POST"])
def daily_goal():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    try:

        goal = int(
            request.form.get(
                "goal",
                1
            )
        )

    except ValueError:

        goal = 1

    if goal < 1:

        goal = 1

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO daily_goals
        (username, goal)
        VALUES (%s, %s)
        ON CONFLICT (username)
        DO UPDATE SET goal = EXCLUDED.goal
    """, (
        username,
        goal
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/dashboard")


# =========================================================
# SUBJECTS
# =========================================================

@app.route("/subjects", methods=["GET", "POST"])
def subjects():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        if name:

            cur.execute("""
                INSERT INTO subjects
                (name, username)
                VALUES (%s, %s)
            """, (
                name,
                username
            ))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM subjects
        WHERE username = %s
        ORDER BY id DESC
    """, (username,))

    subjects_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "subjects.html",
        subjects=subjects_data
    )


# =========================================================
# DELETE SUBJECT
# =========================================================

@app.route("/delete_subject/<int:id>", methods=["POST"])
def delete_subject(id):

    if "username" not in session:

        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM subjects
        WHERE id = %s
        AND username = %s
    """, (
        id,
        session["username"]
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/subjects")


# =========================================================
# ASSIGNMENTS
# =========================================================

@app.route("/assignments", methods=["GET", "POST"])
def assignments():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        due_date = request.form.get(
            "due_date",
            ""
        )

        if subject and title and due_date:

            cur.execute("""
                INSERT INTO assignments
                (subject, title, due_date, completed, username)
                VALUES (%s, %s, %s, 0, %s)
            """, (
                subject,
                title,
                due_date,
                username
            ))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM assignments
        WHERE username = %s
        ORDER BY due_date
    """, (username,))

    assignments_data = cur.fetchall()

    today = date.today().isoformat()

    cur.close()
    conn.close()

    return render_template(
        "assignments.html",
        assignments=assignments_data,
        today=today
    )


# =========================================================
# COMPLETE ASSIGNMENT
# =========================================================

@app.route("/complete_assignment/<int:id>", methods=["POST"])
def complete_assignment(id):

    if "username" not in session:

        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM assignments
        WHERE id = %s
        AND username = %s
    """, (
        id,
        session["username"]
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/assignments")


# =========================================================
# EDIT ASSIGNMENT
# =========================================================

@app.route("/edit_assignment/<int:id>", methods=["GET", "POST"])
def edit_assignment(id):

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        title = request.form.get(
            "title",
            ""
        ).strip()

        due_date = request.form.get(
            "due_date",
            ""
        )

        if subject and title and due_date:

            cur.execute("""
                UPDATE assignments
                SET subject = %s,
                    title = %s,
                    due_date = %s
                WHERE id = %s
                AND username = %s
            """, (
                subject,
                title,
                due_date,
                id,
                username
            ))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/assignments")

    cur.execute("""
        SELECT *
        FROM assignments
        WHERE id = %s
        AND username = %s
    """, (
        id,
        username
    ))

    assignment = cur.fetchone()

    cur.close()
    conn.close()

    if assignment is None:

        return "Assignment not found!"

    return render_template(
        "edit_assignment.html",
        assignment=assignment
    )


# =========================================================
# EXAMS
# =========================================================

@app.route("/exams", methods=["GET", "POST"])
def exams():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        exam_date = request.form.get(
            "exam_date",
            ""
        )

        if subject and exam_date:

            cur.execute("""
                INSERT INTO exams
                (subject, exam_date, exam_time, username)
                VALUES (%s, %s, %s, %s)
            """, (
                subject,
                exam_date,
                "",
                username
            ))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM exams
        WHERE username = %s
        ORDER BY exam_date
    """, (username,))

    exams_data = cur.fetchall()

    today = date.today()

    for exam in exams_data:

        exam_day = exam["exam_date"]

        if isinstance(exam_day, str):

            exam_day = datetime.strptime(
                exam_day,
                "%Y-%m-%d"
            ).date()

        elif hasattr(exam_day, "date"):

            exam_day = exam_day.date()

        exam["days_left"] = (
            exam_day - today
        ).days

    cur.close()
    conn.close()

    return render_template(
        "exams.html",
        exams=exams_data,
        today=today.isoformat()
    )


# =========================================================
# EDIT EXAM
# =========================================================

@app.route("/edit_exam/<int:id>", methods=["GET", "POST"])
def edit_exam(id):

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        exam_date = request.form.get(
            "exam_date",
            ""
        )

        if subject and exam_date:

            cur.execute("""
                UPDATE exams
                SET subject = %s,
                    exam_date = %s
                WHERE id = %s
                AND username = %s
            """, (
                subject,
                exam_date,
                id,
                username
            ))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/exams")

    cur.execute("""
        SELECT *
        FROM exams
        WHERE id = %s
        AND username = %s
    """, (
        id,
        username
    ))

    exam = cur.fetchone()

    cur.close()
    conn.close()

    if exam is None:

        return "Exam not found!"

    return render_template(
        "edit_exam.html",
        exam=exam
    )


# =========================================================
# DELETE EXAM
# =========================================================

@app.route("/delete_exam/<int:id>", methods=["POST"])
def delete_exam(id):

    if "username" not in session:

        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM exams
        WHERE id = %s
        AND username = %s
    """, (
        id,
        session["username"]
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/exams")


# =========================================================
# TIMETABLE
# =========================================================

@app.route("/timetable", methods=["GET", "POST"])
def timetable():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        study_date = request.form.get(
            "study_date",
            ""
        )

        start_time = request.form.get(
            "start_time",
            ""
        )

        end_time = request.form.get(
            "end_time",
            ""
        )

        topic = request.form.get(
            "topic",
            ""
        ).strip()

        if (
            subject
            and study_date
            and start_time
            and end_time
            and topic
        ):

            cur.execute("""
                INSERT INTO timetable
                (
                    subject,
                    study_date,
                    start_time,
                    end_time,
                    topic,
                    username
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                subject,
                study_date,
                start_time,
                end_time,
                topic,
                username
            ))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM timetable
        WHERE username = %s
        ORDER BY study_date, start_time
    """, (username,))

    timetable_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "timetable.html",
        timetable=timetable_data
    )


# =========================================================
# PROGRESS
# =========================================================

@app.route("/progress", methods=["GET", "POST"])
def progress():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        try:

            total_topics = int(
                request.form.get(
                    "total_topics",
                    0
                )
            )

        except ValueError:

            total_topics = 0

        for i in range(
            1,
            total_topics + 1
        ):

            topic = request.form.get(
                f"topic{i}",
                ""
            ).strip()

            completed = (
                1
                if request.form.get(
                    f"complete{i}"
                )
                else 0
            )

            if subject and topic:

                completed_at = (
                    date.today()
                    if completed
                    else None
                )

                cur.execute("""
                    INSERT INTO study_topics
                    (
                        subject,
                        topic,
                        completed,
                        completed_at,
                        username
                    )
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    subject,
                    topic,
                    completed,
                    completed_at,
                    username
                ))

        conn.commit()

    # SUBJECT-WISE PROGRESS
    cur.execute("""
        SELECT
            subject,
            COUNT(*) AS total,
            SUM(completed) AS completed
        FROM study_topics
        WHERE username = %s
        GROUP BY subject
    """, (username,))

    progress_data = cur.fetchall()

    # OVERALL PROGRESS
    overall_total = sum(
        int(item["total"])
        for item in progress_data
    )

    overall_completed = sum(
        int(item["completed"] or 0)
        for item in progress_data
    )

    if overall_total > 0:

        overall_percentage = round(
            (
                overall_completed
                / overall_total
            ) * 100
        )

    else:

        overall_percentage = 0

    # ALL TOPICS
    cur.execute("""
        SELECT *
        FROM study_topics
        WHERE username = %s
        ORDER BY id DESC
    """, (username,))

    topics = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "progress.html",
        progress=progress_data,
        topics=topics,
        overall_total=overall_total,
        overall_completed=overall_completed,
        overall_percentage=overall_percentage
    )


# =========================================================
# UPDATE PROGRESS
# =========================================================

@app.route("/update_progress/<int:id>", methods=["POST"])
def update_progress(id):

    if "username" not in session:

        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE study_topics
        SET completed = 1,
            completed_at = %s
        WHERE id = %s
        AND username = %s
    """, (
        date.today(),
        id,
        session["username"]
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/progress")


# =========================================================
# PDF NOTES - BACKBLAZE B2
# =========================================================

@app.route("/pdfs", methods=["GET", "POST"])
def pdfs():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        pdf = request.files.get("pdf")

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        if not pdf or pdf.filename == "":

            cur.close()
            conn.close()

            return "Please select a PDF file."

        if not pdf.filename.lower().endswith(".pdf"):

            cur.close()
            conn.close()

            return "Only PDF files are allowed."

        filename = secure_filename(
            pdf.filename
        )

        if not filename:

            cur.close()
            conn.close()

            return "Invalid PDF filename."

        # -------------------------------------------------
        # CREATE UNIQUE B2 OBJECT KEY
        # -------------------------------------------------

        timestamp = datetime.now().strftime(
            "%Y%m%d%H%M%S%f"
        )

        object_key = (
            f"{username}/"
            f"{timestamp}_"
            f"{filename}"
        )

        # -------------------------------------------------
        # SAVE TEMPORARILY
        # -------------------------------------------------

        temp_path = None

        try:

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".pdf"
            ) as temp:

                pdf.save(temp.name)
                temp_path = temp.name

            # -------------------------------------------------
            # UPLOAD TO BACKBLAZE B2
            # -------------------------------------------------

            b2 = get_b2_client()

            b2.upload_file(
                temp_path,
                B2_BUCKET_NAME,
                object_key,
                ExtraArgs={
                    "ContentType": "application/pdf"
                },
                Config=B2_TRANSFER_CONFIG
            )

            # -------------------------------------------------
            # SAVE DATABASE INFORMATION
            # -------------------------------------------------

            cur.execute("""
                INSERT INTO pdf_files
                (
                    username,
                    subject,
                    filename,
                    filepath,
                    public_id,
                    storage_key
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                username,
                subject,
                filename,
                object_key,
                None,
                object_key
            ))

            conn.commit()

        except Exception as e:

            conn.rollback()

            print(
                "B2 PDF upload error:",
                str(e)
            )

            if temp_path and os.path.exists(temp_path):

                os.remove(temp_path)

            cur.close()
            conn.close()

            return (
                "PDF upload failed. "
                "Please check Backblaze B2 settings."
            )

        finally:

            if temp_path and os.path.exists(temp_path):

                os.remove(temp_path)

    # -------------------------------------------------
    # GET ONLY CURRENT USER PDFs
    # -------------------------------------------------

    cur.execute("""
        SELECT *
        FROM pdf_files
        WHERE username = %s
        ORDER BY id DESC
    """, (
        username,
    ))

    rows = cur.fetchall()

    pdf_files = []

    # -------------------------------------------------
    # GENERATE PRIVATE PRESIGNED URL
    # -------------------------------------------------

    b2 = None

    for row in rows:

        item = dict(row)

        # New Backblaze files
        if item.get("storage_key"):

            try:

                if b2 is None:

                    b2 = get_b2_client()

                item["filepath"] = (
                    b2.generate_presigned_url(
                        "get_object",
                        Params={
                            "Bucket": B2_BUCKET_NAME,
                            "Key": item["storage_key"]
                        },
                        ExpiresIn=3600
                    )
                )

            except Exception as e:

                print(
                    "B2 presigned URL error:",
                    str(e)
                )

                item["filepath"] = "#"

        # Old Cloudinary files
        else:

            item["filepath"] = item["filepath"]

        pdf_files.append(item)

    cur.close()
    conn.close()

    return render_template(
        "pdfs.html",
        pdf_files=pdf_files
    )


# =========================================================
# OPEN / DOWNLOAD PDF THROUGH APP
# =========================================================

@app.route("/open_pdf/<int:id>")
def open_pdf(id):

    if "username" not in session:
        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM pdf_files
        WHERE id = %s
        AND username = %s
    """, (id, username))

    pdf = cur.fetchone()

    cur.close()
    conn.close()

    if not pdf:
        return "PDF not found.", 404

    if not pdf.get("storage_key"):
        return redirect(pdf["filepath"])

    try:
        b2 = get_b2_client()

        obj = b2.get_object(
            Bucket=B2_BUCKET_NAME,
            Key=pdf["storage_key"]
        )

        from flask import Response

        def generate():
            body = obj["Body"]
            try:
                while True:
                    chunk = body.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk
            finally:
                body.close()

        return Response(
            generate(),
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{pdf["filename"]}"'
            }
        )

    except Exception as e:
        print("B2 PDF open error:", str(e))
        return (
            "PDF could not be opened right now. "
            "Please try again."
        ), 500


# =========================================================
# DELETE PDF
# =========================================================

@app.route("/delete_pdf/<int:id>", methods=["POST"])
def delete_pdf(id):

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    # -------------------------------------------------
    # GET PDF ONLY FROM CURRENT USER
    # -------------------------------------------------

    cur.execute("""
        SELECT *
        FROM pdf_files
        WHERE id = %s
        AND username = %s
    """, (
        id,
        username
    ))

    pdf = cur.fetchone()

    if pdf:

        # -------------------------------------------------
        # BACKBLAZE DELETE
        # -------------------------------------------------

        if pdf.get("storage_key"):

            try:

                b2 = get_b2_client()

                b2.delete_object(
                    Bucket=B2_BUCKET_NAME,
                    Key=pdf["storage_key"]
                )

            except Exception as e:

                print(
                    "B2 PDF delete error:",
                    str(e)
                )

        # -------------------------------------------------
        # OLD CLOUDINARY DELETE
        # -------------------------------------------------

        # If an old PDF was uploaded to Cloudinary,
        # public_id will exist.
        #
        # We intentionally do not use Cloudinary
        # for new uploads.

        # -------------------------------------------------
        # DATABASE DELETE
        # -------------------------------------------------

        cur.execute("""
            DELETE FROM pdf_files
            WHERE id = %s
            AND username = %s
        """, (
            id,
            username
        ))

        conn.commit()

    cur.close()
    conn.close()

    return redirect("/pdfs")


# =========================================================
# ALERTS
# =========================================================

@app.route("/alerts")
def alerts():

    if "username" not in session:

        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    today = date.today()

    # -------------------------------------------------
    # ASSIGNMENTS
    # -------------------------------------------------

    cur.execute("""
        SELECT *
        FROM assignments
        WHERE username = %s
        AND completed = 0
        ORDER BY due_date
    """, (username,))

    assignments_data = cur.fetchall()

    # -------------------------------------------------
    # EXAMS
    # -------------------------------------------------

    cur.execute("""
        SELECT *
        FROM exams
        WHERE username = %s
        ORDER BY exam_date
    """, (username,))

    exams_data = cur.fetchall()

    # -------------------------------------------------
    # TIMETABLE
    # -------------------------------------------------

    cur.execute("""
        SELECT *
        FROM timetable
        WHERE username = %s
        ORDER BY study_date, start_time
    """, (username,))

    timetable_data = cur.fetchall()

    cur.close()
    conn.close()

    # =================================================
    # ASSIGNMENT ALERTS
    # =================================================

    alert_assignments = []

    for item in assignments_data:

        try:

            due = datetime.strptime(
                item["due_date"],
                "%Y-%m-%d"
            ).date()

        except (ValueError, TypeError):

            continue

        days_left = (
            due - today
        ).days

        if days_left <= 1:

            alert_assignments.append({
                "subject": item["subject"],
                "title": item["title"],
                "due_date": item["due_date"],
                "days_left": days_left
            })

    # =================================================
    # EXAM ALERTS
    # =================================================

    alert_exams = []

    for exam in exams_data:

        try:

            exam_day = datetime.strptime(
                exam["exam_date"],
                "%Y-%m-%d"
            ).date()

        except (ValueError, TypeError):

            continue

        days_left = (
            exam_day - today
        ).days

        if 0 <= days_left <= 3:

            alert_exams.append({
                "subject": exam["subject"],
                "exam_date": exam["exam_date"],
                "days_left": days_left
            })

    # =================================================
    # TODAY'S TIMETABLE
    # =================================================

    alert_timetable = []

    for item in timetable_data:

        if item["study_date"] == today.isoformat():

            alert_timetable.append({
                "subject": item["subject"],
                "topic": item["topic"],
                "start_time": item["start_time"],
                "end_time": item["end_time"]
            })

    return render_template(
        "alerts.html",
        assignments=alert_assignments,
        exams=alert_exams,
        timetable=alert_timetable
    )


# =========================================================
# TO-DO LIST
# =========================================================

TODO_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>To-Do List</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #0f1115;
    color: white;
}

.container {
    max-width: 900px;
    margin: auto;
    padding: 25px;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 15px;
    margin-bottom: 25px;
}

.header h1 {
    margin: 0;
}

.back {
    color: white;
    text-decoration: none;
    background: #252a34;
    padding: 10px 15px;
    border-radius: 8px;
}

.card {
    background: #181c24;
    padding: 20px;
    border-radius: 14px;
    margin-bottom: 20px;
}

input,
textarea {
    width: 100%;
    padding: 12px;
    margin-top: 8px;
    margin-bottom: 15px;
    background: #0f1115;
    border: 1px solid #333;
    color: white;
    border-radius: 8px;
}

textarea {
    min-height: 80px;
    resize: vertical;
}

button {
    border: none;
    padding: 10px 15px;
    border-radius: 8px;
    cursor: pointer;
    margin-right: 5px;
}

.add-btn {
    background: #22c55e;
    color: white;
}

.complete-btn {
    background: #3b82f6;
    color: white;
}

.edit-btn {
    background: #f59e0b;
    color: white;
}

.delete-btn {
    background: #ef4444;
    color: white;
}

.todo {
    background: #202631;
    padding: 15px;
    border-radius: 12px;
    margin-bottom: 12px;
}

.todo.completed {
    opacity: 0.55;
}

.todo.completed .title {
    text-decoration: line-through;
}

.title {
    font-size: 19px;
    font-weight: bold;
    margin-bottom: 7px;
}

.description {
    color: #bbb;
    margin-bottom: 10px;
    white-space: pre-wrap;
}

.due {
    color: #fbbf24;
    margin-bottom: 12px;
}

.status {
    margin-bottom: 12px;
    font-size: 14px;
}

.empty {
    text-align: center;
    color: #aaa;
    padding: 30px;
}

.setting {
    display: flex;
    align-items: center;
    gap: 10px;
}

.setting input {
    width: auto;
    margin: 0;
}

.actions form {
    display: inline;
}

a.action-link {
    text-decoration: none;
}

@media (max-width: 600px) {
    .container {
        padding: 15px;
    }

    .header {
        align-items: flex-start;
        flex-direction: column;
    }
}

</style>

</head>

<body>

<div class="container">

<div class="header">

<h1>📝 To-Do List</h1>

<a href="/dashboard" class="back">
Dashboard
</a>

</div>

<!-- ADD TODO -->
<div class="card">

<h2>Add To-Do</h2>

<form method="POST" action="/todo/add">

<label>Task</label>

<input
    type="text"
    name="title"
    placeholder="Example: Complete Python assignment"
    required
>

<label>Description</label>

<textarea
    name="description"
    placeholder="Optional"
></textarea>

<label>Due Date & Time</label>

<input
    type="datetime-local"
    name="due_datetime"
>

<button class="add-btn" type="submit">
➕ Add To-Do
</button>

</form>

</div>

<!-- SETTINGS -->
<div class="card">

<h3>🔔 Reminder Settings</h3>

<div class="setting">

<input
    type="checkbox"
    id="vibrationToggle"
    checked
>

<label for="vibrationToggle">
Enable vibration
</label>

</div>

<br>

<button
    type="button"
    class="complete-btn"
    onclick="enableNotifications()"
>
🔔 Enable Notifications
</button>

<p style="color:#aaa;font-size:13px;margin-bottom:0;">
Keep this To-Do page open for browser reminders. Android native reminders can be added later.
</p>

</div>

<!-- TODO LIST -->
<div class="card">

<h2>My Tasks</h2>

<div id="todoList">

{% if todos %}

{% for todo in todos %}

<div
    class="todo {% if todo.completed %}completed{% endif %}"
    id="todo-{{ todo.id }}"
>

<div class="title">
{{ todo.title }}
</div>

{% if todo.description %}

<div class="description">
{{ todo.description }}
</div>

{% endif %}

{% if todo.due_datetime %}

<div class="due">

⏰ Due:
{{ todo.due_datetime.strftime('%d-%m-%Y %I:%M %p') if todo.due_datetime.strftime else todo.due_datetime }}

</div>

{% endif %}

<div class="status">

{% if todo.completed %}

✅ Completed

{% else %}

⏳ Pending

{% endif %}

</div>

<div class="actions">

{% if not todo.completed %}

<form
    method="POST"
    action="/todo/complete/{{ todo.id }}"
>

<button class="complete-btn" type="submit">
✅ Complete
</button>

</form>

{% endif %}

<a
    class="action-link"
    href="/todo/edit/{{ todo.id }}"
>

<button
    type="button"
    class="edit-btn"
>
✏️ Edit
</button>

</a>

<form
    method="POST"
    action="/todo/delete/{{ todo.id }}"
    onsubmit="return confirm('Delete this task?')"
>

<button class="delete-btn" type="submit">
🗑️ Delete
</button>

</form>

</div>

</div>

{% endfor %}

{% else %}

<div class="empty">
No To-Do tasks yet.
</div>

{% endif %}

</div>

</div>

</div>

<script>

let vibrationEnabled =
    localStorage.getItem("todoVibration") !== "false";

const vibrationToggle =
    document.getElementById("vibrationToggle");

vibrationToggle.checked = vibrationEnabled;

vibrationToggle.addEventListener("change", function() {

    vibrationEnabled = this.checked;

    localStorage.setItem(
        "todoVibration",
        vibrationEnabled ? "true" : "false"
    );

});


async function enableNotifications() {

    if (!("Notification" in window)) {

        alert("This browser does not support notifications.");
        return;

    }

    try {

        const permission =
            await Notification.requestPermission();

        if (permission === "granted") {

            alert("Notifications enabled successfully!");

            new Notification(
                "Student Smart Study Planner",
                {
                    body: "Reminder notifications are enabled."
                }
            );

        } else {

            alert("Notification permission denied.");

        }

    } catch (error) {

        console.log("Notification permission error:", error);
        alert("Could not enable notifications in this browser.");

    }

}


function playAlarm() {

    try {

        const AudioContext =
            window.AudioContext ||
            window.webkitAudioContext;

        if (!AudioContext) {
            return;
        }

        const audioContext = new AudioContext();

        const oscillator =
            audioContext.createOscillator();

        const gain =
            audioContext.createGain();

        oscillator.type = "sine";
        oscillator.frequency.value = 900;
        gain.gain.value = 0.25;

        oscillator.connect(gain);
        gain.connect(audioContext.destination);
        oscillator.start();

        setTimeout(function() {

            oscillator.stop();
            audioContext.close();

        }, 1000);

    } catch (error) {

        console.log("Alarm sound error:", error);

    }

}


function vibratePhone() {

    if (
        vibrationEnabled &&
        navigator.vibrate
    ) {

        navigator.vibrate([
            500,
            300,
            500,
            300,
            800
        ]);

    }

}


async function checkTodoReminders() {

    try {

        const response =
            await fetch("/todo/reminders", {
                cache: "no-store"
            });

        if (!response.ok) {
            return;
        }

        const data =
            await response.json();

        if (!data.reminders) {
            return;
        }

        for (const reminder of data.reminders) {

            playAlarm();
            vibratePhone();

            if (
                "Notification" in window &&
                Notification.permission === "granted"
            ) {

                new Notification(
                    "⏰ To-Do Reminder",
                    {
                        body: reminder.title + " is due now!",
                        requireInteraction: true
                    }
                );

            } else {

                alert(
                    "⏰ Reminder: " +
                    reminder.title
                );

            }

        }

    } catch (error) {

        console.log(
            "Reminder check error:",
            error
        );

    }

}

setInterval(
    checkTodoReminders,
    10000
);

checkTodoReminders();

</script>

</body>
</html>
"""


# =========================================================
# TODO HOME
# =========================================================

@app.route("/todo")
def todo():

    if "username" not in session:
        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM todos
        WHERE username = %s
        ORDER BY
            completed ASC,
            due_datetime ASC NULLS LAST,
            id DESC
    """, (username,))

    todos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template_string(
        TODO_PAGE,
        todos=todos
    )


# =========================================================
# ADD TODO
# =========================================================

@app.route("/todo/add", methods=["POST"])
def add_todo():

    if "username" not in session:
        return redirect("/login")

    username = session["username"]

    title = request.form.get(
        "title",
        ""
    ).strip()

    description = request.form.get(
        "description",
        ""
    ).strip()

    due_datetime_text = request.form.get(
        "due_datetime",
        ""
    ).strip()

    if not title:
        return "Task title is required."

    due_datetime = None

    if due_datetime_text:

        try:
            due_datetime = datetime.strptime(
                due_datetime_text,
                "%Y-%m-%dT%H:%M"
            )
        except ValueError:
            return "Invalid date/time."

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO todos
        (
            username,
            title,
            description,
            due_datetime,
            completed,
            notified
        )
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            0,
            0
        )
    """, (
        username,
        title,
        description,
        due_datetime
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/todo")


# =========================================================
# COMPLETE TODO
# =========================================================

@app.route("/todo/complete/<int:todo_id>", methods=["POST"])
def complete_todo(todo_id):

    if "username" not in session:
        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE todos
        SET completed = 1
        WHERE id = %s
        AND username = %s
    """, (
        todo_id,
        username
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/todo")


# =========================================================
# DELETE TODO
# =========================================================

@app.route("/todo/delete/<int:todo_id>", methods=["POST"])
def delete_todo(todo_id):

    if "username" not in session:
        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM todos
        WHERE id = %s
        AND username = %s
    """, (
        todo_id,
        username
    ))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/todo")


# =========================================================
# EDIT TODO
# =========================================================

@app.route("/todo/edit/<int:todo_id>", methods=["GET", "POST"])
def edit_todo(todo_id):

    if "username" not in session:
        return redirect("/login")

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        due_datetime_text = request.form.get(
            "due_datetime",
            ""
        ).strip()

        if not title:

            cur.close()
            conn.close()
            return "Task title is required."

        due_datetime = None

        if due_datetime_text:

            try:
                due_datetime = datetime.strptime(
                    due_datetime_text,
                    "%Y-%m-%dT%H:%M"
                )
            except ValueError:
                cur.close()
                conn.close()
                return "Invalid date/time."

        cur.execute("""
            UPDATE todos
            SET
                title = %s,
                description = %s,
                due_datetime = %s,
                notified = 0
            WHERE id = %s
            AND username = %s
        """, (
            title,
            description,
            due_datetime,
            todo_id,
            username
        ))

        conn.commit()

        cur.close()
        conn.close()

        return redirect("/todo")

    cur.execute("""
        SELECT *
        FROM todos
        WHERE id = %s
        AND username = %s
    """, (
        todo_id,
        username
    ))

    todo_item = cur.fetchone()

    cur.close()
    conn.close()

    if not todo_item:
        return "To-Do not found."

    due_value = ""

    if todo_item["due_datetime"]:

        due_value = todo_item[
            "due_datetime"
        ].strftime(
            "%Y-%m-%dT%H:%M"
        )

    return render_template_string(
        """
<!DOCTYPE html>

<html>

<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>Edit To-Do</title>

<style>

body {
    background: #0f1115;
    color: white;
    font-family: Arial, sans-serif;
    padding: 25px;
    margin: 0;
}

.container {
    max-width: 600px;
    margin: auto;
}

input,
textarea {
    width: 100%;
    padding: 12px;
    margin: 10px 0 20px;
    background: #181c24;
    color: white;
    border: 1px solid #333;
    border-radius: 8px;
    box-sizing: border-box;
}

textarea {
    min-height: 100px;
    resize: vertical;
}

button {
    padding: 12px 18px;
    border: none;
    border-radius: 8px;
    background: #22c55e;
    color: white;
    cursor: pointer;
}

a {
    color: white;
}

</style>

</head>

<body>

<div class="container">

<h1>✏️ Edit To-Do</h1>

<form method="POST">

<label>Task</label>

<input
    type="text"
    name="title"
    value="{{ todo_item.title }}"
    required
>

<label>Description</label>

<textarea
    name="description"
>{{ todo_item.description or "" }}</textarea>

<label>Due Date & Time</label>

<input
    type="datetime-local"
    name="due_datetime"
    value="{{ due_value }}"
>

<button type="submit">
💾 Save Changes
</button>

</form>

<br>

<a href="/todo">
← Back to To-Do
</a>

</div>

</body>

</html>
        """,
        todo_item=todo_item,
        due_value=due_value
    )


# =========================================================
# TODO REMINDER API
# =========================================================

@app.route("/todo/reminders")
def todo_reminders():

    if "username" not in session:
        return jsonify({"reminders": []})

    username = session["username"]

    conn = get_db()
    cur = conn.cursor()

    # due_datetime is stored as a local India time entered by the user.
    # Render/Postgres may use UTC internally, so compare against
    # the current Asia/Kolkata local time.
    cur.execute("""
        SELECT
            id,
            title,
            due_datetime
        FROM todos
        WHERE username = %s
        AND completed = 0
        AND notified = 0
        AND due_datetime IS NOT NULL
        AND due_datetime <= (
            CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata'
        )
        ORDER BY due_datetime
    """, (username,))

    rows = cur.fetchall()

    reminders = []

    for row in rows:

        reminders.append({
            "id": row["id"],
            "title": row["title"]
        })

        cur.execute("""
            UPDATE todos
            SET notified = 1
            WHERE id = %s
            AND username = %s
        """, (
            row["id"],
            username
        ))

    conn.commit()

    cur.close()
    conn.close()

    return jsonify({
        "reminders": reminders
    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run()
