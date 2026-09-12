from flask import Flask, render_template, request, redirect, session
from datetime import date, datetime
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = "student-study-planner-secret"


# ================= DATABASE =================

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    if not DATABASE_URL:
        raise Exception("DATABASE_URL is not configured in Render Environment.")

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )


def init_db():

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            exam_date TEXT NOT NULL,
            exam_time TEXT NOT NULL
        )
    """)

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS study_topics (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            topic TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()


# ================= HOME =================

@app.route("/")
def home():
    return render_template("index.html")


# ================= SIGNUP =================

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            return "Please enter username and password."

        conn = get_db()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users (username, password) VALUES (%s, %s)",
                (username, password)
            )

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


# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM users
            WHERE username = %s AND password = %s
        """, (username, password))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:

            session["username"] = username

            return redirect("/dashboard")

        return "Invalid username or password!"

    return render_template("login.html")


# ================= FORGOT PASSWORD =================

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password", "").strip()

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
            """, (new_password, username))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/login")

        cur.close()
        conn.close()

        return "Username not found!"

    return render_template("forgot_password.html")


# ================= LOGOUT =================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ================= DASHBOARD =================

@app.route("/dashboard")
def dashboard():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS count FROM subjects")
    subjects_count = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM assignments
        WHERE completed = 0
    """)
    assignments_count = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) AS count FROM exams")
    exams_count = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM study_topics
        WHERE completed = 1
    """)
    completed_topics = cur.fetchone()["count"]

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM study_topics
    """)
    total_topics = cur.fetchone()["count"]

    cur.execute("""
        SELECT *
        FROM assignments
        WHERE completed = 0
        ORDER BY due_date
        LIMIT 5
    """)
    pending_assignments = cur.fetchall()

    today = date.today().isoformat()

    cur.execute("""
        SELECT *
        FROM exams
        WHERE exam_date >= %s
        ORDER BY exam_date
        LIMIT 5
    """, (today,))
    upcoming_exams = cur.fetchall()

    cur.execute("""
        SELECT
            subject,
            COUNT(*) AS total,
            SUM(completed) AS completed
        FROM study_topics
        GROUP BY subject
    """)
    progress_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "dashboard.html",
        username=session["username"],
        subjects_count=subjects_count,
        assignments_count=assignments_count,
        exams_count=exams_count,
        completed_topics=completed_topics,
        total_topics=total_topics,
        pending_assignments=pending_assignments,
        upcoming_exams=upcoming_exams,
        progress=progress_data,
        today=today
    )


# ================= SUBJECTS =================

@app.route("/subjects", methods=["GET", "POST"])
def subjects():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        if name:

            cur.execute(
                "INSERT INTO subjects (name) VALUES (%s)",
                (name,)
            )

            conn.commit()

    cur.execute("""
        SELECT *
        FROM subjects
        ORDER BY id DESC
    """)

    subjects_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "subjects.html",
        subjects=subjects_data
    )


# ================= DELETE SUBJECT =================

@app.route("/delete_subject/<int:id>", methods=["POST"])
def delete_subject(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM subjects WHERE id = %s",
        (id,)
    )

    conn.commit()
    cur.close()
    conn.close()

    return redirect("/subjects")


# ================= ASSIGNMENTS =================

@app.route("/assignments", methods=["GET", "POST"])
def assignments():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "")

        if subject and title and due_date:

            cur.execute("""
                INSERT INTO assignments
                (subject, title, due_date, completed)
                VALUES (%s, %s, %s, 0)
            """, (subject, title, due_date))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM assignments
        ORDER BY due_date
    """)

    assignments_data = cur.fetchall()

    today = date.today().isoformat()

    cur.close()
    conn.close()

    return render_template(
        "assignments.html",
        assignments=assignments_data,
        today=today
    )


# ================= COMPLETE ASSIGNMENT =================

@app.route("/complete_assignment/<int:id>", methods=["POST"])
def complete_assignment(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM assignments WHERE id = %s",
        (id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/assignments")


# ================= EDIT ASSIGNMENT =================

@app.route("/edit_assignment/<int:id>", methods=["GET", "POST"])
def edit_assignment(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "")

        if subject and title and due_date:

            cur.execute("""
                UPDATE assignments
                SET subject = %s,
                    title = %s,
                    due_date = %s
                WHERE id = %s
            """, (subject, title, due_date, id))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/assignments")

    cur.execute("""
        SELECT *
        FROM assignments
        WHERE id = %s
    """, (id,))

    assignment = cur.fetchone()

    cur.close()
    conn.close()

    if assignment is None:
        return "Assignment not found!"

    return render_template(
        "edit_assignment.html",
        assignment=assignment
    )


# ================= EXAMS =================
@app.route("/exams", methods=["GET", "POST"])
def exams():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        exam_date = request.form.get("exam_date", "")

        if subject and exam_date:

            cur.execute("""
                INSERT INTO exams
                (subject, exam_date, exam_time)
                VALUES (%s, %s, %s)
            """, (subject, exam_date, ""))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM exams
        ORDER BY exam_date
    """)

    exams_data = cur.fetchall()

    today = date.today()

    for exam in exams_data:
        exam_day = exam["exam_date"]

        if hasattr(exam_day, "date"):
            exam_day = exam_day.date()

        exam["days_left"] = (exam_day - today).days

    cur.close()
    conn.close()

    return render_template(
        "exams.html",
        exams=exams_data,
        today=today.isoformat()
    )



# ================= EDIT EXAM =================

@app.route("/edit_exam/<int:id>", methods=["GET", "POST"])
def edit_exam(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        exam_date = request.form.get("exam_date", "")

        if subject and exam_date:

            cur.execute("""
                UPDATE exams
                SET subject = %s,
                    exam_date = %s
                WHERE id = %s
            """, (subject, exam_date, id))

            conn.commit()

            cur.close()
            conn.close()

            return redirect("/exams")

    cur.execute("""
        SELECT *
        FROM exams
        WHERE id = %s
    """, (id,))

    exam = cur.fetchone()

    cur.close()
    conn.close()

    if exam is None:
        return "Exam not found!"

    return render_template(
        "edit_exam.html",
        exam=exam
    )


# ================= DELETE EXAM =================

@app.route("/delete_exam/<int:id>", methods=["POST"])
def delete_exam(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM exams WHERE id = %s",
        (id,)
    )

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/exams")


# ================= TIMETABLE =================

@app.route("/timetable", methods=["GET", "POST"])
def timetable():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        study_date = request.form.get("study_date", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        topic = request.form.get("topic", "").strip()

        if subject and study_date and start_time and end_time and topic:

            cur.execute("""
                INSERT INTO timetable
                (subject, study_date, start_time, end_time, topic)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                subject,
                study_date,
                start_time,
                end_time,
                topic
            ))

            conn.commit()

    cur.execute("""
        SELECT *
        FROM timetable
        ORDER BY study_date, start_time
    """)

    timetable_data = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "timetable.html",
        timetable=timetable_data
    )


# ================= PROGRESS =================

@app.route("/progress", methods=["GET", "POST"])
def progress():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()

        try:
            total_topics = int(
                request.form.get("total_topics", 0)
            )
        except ValueError:
            total_topics = 0

        for i in range(1, total_topics + 1):

            topic = request.form.get(
                f"topic{i}", ""
            ).strip()

            completed = 1 if request.form.get(
                f"complete{i}"
            ) else 0

            if subject and topic:

                cur.execute("""
                    INSERT INTO study_topics
                    (subject, topic, completed)
                    VALUES (%s, %s, %s)
                """, (
                    subject,
                    topic,
                    completed
                ))

        conn.commit()

    # Subject-wise Progress
    cur.execute("""
        SELECT
            subject,
            COUNT(*) AS total,
            SUM(completed) AS completed
        FROM study_topics
        GROUP BY subject
    """)

    progress_data = cur.fetchall()

    # Overall Progress
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
            (overall_completed / overall_total) * 100
        )
    else:
        overall_percentage = 0

    # All Topics
    cur.execute("""
        SELECT *
        FROM study_topics
        ORDER BY id DESC
    """)

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


# ================= UPDATE PROGRESS =================

@app.route("/update_progress/<int:id>", methods=["POST"])
def update_progress(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE study_topics
        SET completed = 1
        WHERE id = %s
    """, (id,))

    conn.commit()

    cur.close()
    conn.close()

    return redirect("/progress")


# ================= ALERTS =================

@app.route("/alerts")
def alerts():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    today = date.today()

    cur.execute("""
        SELECT *
        FROM assignments
        WHERE completed = 0
        ORDER BY due_date
    """)

    assignments_data = cur.fetchall()

    cur.execute("""
        SELECT *
        FROM exams
        ORDER BY exam_date
    """)

    exams_data = cur.fetchall()

    cur.execute("""
        SELECT *
        FROM timetable
        ORDER BY study_date, start_time
    """)

    timetable_data = cur.fetchall()

    cur.close()
    conn.close()


    # Assignment Alerts

    alert_assignments = []

    for item in assignments_data:

        due = datetime.strptime(
            item["due_date"],
            "%Y-%m-%d"
        ).date()

        days_left = (due - today).days

        if days_left <= 1:

            alert_assignments.append({
                "subject": item["subject"],
                "title": item["title"],
                "due_date": item["due_date"],
                "days_left": days_left
            })


    # Exam Alerts

    alert_exams = []

    for exam in exams_data:

        exam_day = datetime.strptime(
            exam["exam_date"],
            "%Y-%m-%d"
        ).date()

        days_left = (exam_day - today).days

        if 0 <= days_left <= 3:

            alert_exams.append({
                "subject": exam["subject"],
                "exam_date": exam["exam_date"],
                "days_left": days_left
            })


    # Today's Timetable

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


# ================= RUN =================

if __name__ == "__main__":
    app.run()
