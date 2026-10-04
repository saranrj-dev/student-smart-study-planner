from flask import Flask, render_template, request, redirect, session
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
# RUN
# =========================================================

if __name__ == "__main__":

    app.run()
