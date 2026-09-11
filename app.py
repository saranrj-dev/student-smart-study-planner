from flask import Flask, render_template, request, redirect, session
from datetime import date, datetime
import sqlite3

app = Flask(__name__)
app.secret_key = "student-study-planner-secret"

DATABASE = "studyplanner.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            exam_date TEXT NOT NULL,
            exam_time TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            study_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            topic TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS study_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            topic TEXT NOT NULL,
            completed INTEGER DEFAULT 0
        )
    """)

    conn.commit()
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

        try:

            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password)
            )

            conn.commit()
            conn.close()

            return redirect("/login")

        except sqlite3.IntegrityError:

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

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE username = ? AND password = ?
        """, (username, password)).fetchone()

        conn.close()

        if user:

            session["username"] = username

            return redirect("/dashboard")

        return "Invalid username or password!"

    return render_template("login.html")
#========forget===============
# ================= FORGOT PASSWORD =================

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password", "").strip()

        if not username or not new_password:
            return "Please enter username and new password."

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE username = ?
        """, (username,)).fetchone()

        if user:

            conn.execute("""
                UPDATE users
                SET password = ?
                WHERE username = ?
            """, (new_password, username))

            conn.commit()
            conn.close()

            return redirect("/login")

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

    subjects_count = conn.execute(
        "SELECT COUNT(*) FROM subjects"
    ).fetchone()[0]

    assignments_count = conn.execute("""
        SELECT COUNT(*)
        FROM assignments
        WHERE completed = 0
    """).fetchone()[0]

    exams_count = conn.execute(
        "SELECT COUNT(*) FROM exams"
    ).fetchone()[0]

    completed_topics = conn.execute("""
        SELECT COUNT(*)
        FROM study_topics
        WHERE completed = 1
    """).fetchone()[0]

    total_topics = conn.execute("""
        SELECT COUNT(*)
        FROM study_topics
    """).fetchone()[0]

    pending_assignments = conn.execute("""
        SELECT *
        FROM assignments
        WHERE completed = 0
        ORDER BY due_date
        LIMIT 5
    """).fetchall()

    today = date.today().isoformat()

    upcoming_exams = conn.execute("""
        SELECT *
        FROM exams
        WHERE exam_date >= ?
        ORDER BY exam_date
        LIMIT 5
    """, (today,)).fetchall()

    progress_data = conn.execute("""
        SELECT
            subject,
            COUNT(*) AS total,
            SUM(completed) AS completed
        FROM study_topics
        GROUP BY subject
    """).fetchall()

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

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        if name:

            conn.execute(
                "INSERT INTO subjects (name) VALUES (?)",
                (name,)
            )

            conn.commit()

    subjects_data = conn.execute("""
        SELECT *
        FROM subjects
        ORDER BY id DESC
    """).fetchall()

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

    conn.execute(
        "DELETE FROM subjects WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/subjects")


# ================= ASSIGNMENTS =================

@app.route("/assignments", methods=["GET", "POST"])
def assignments():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "")

        if subject and title and due_date:

            conn.execute("""
                INSERT INTO assignments
                (subject, title, due_date, completed)
                VALUES (?, ?, ?, 0)
            """, (subject, title, due_date))

            conn.commit()

    assignments_data = conn.execute("""
        SELECT *
        FROM assignments
        ORDER BY due_date
    """).fetchall()

    today = date.today().isoformat()

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

    conn.execute(
        "DELETE FROM assignments WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/assignments")


# ================= EDIT ASSIGNMENT =================

@app.route("/edit_assignment/<int:id>", methods=["GET", "POST"])
def edit_assignment(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "")

        if subject and title and due_date:

            conn.execute("""
                UPDATE assignments
                SET subject = ?, title = ?, due_date = ?
                WHERE id = ?
            """, (subject, title, due_date, id))

            conn.commit()
            conn.close()

            return redirect("/assignments")

    assignment = conn.execute("""
        SELECT *
        FROM assignments
        WHERE id = ?
    """, (id,)).fetchone()

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

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        exam_date = request.form.get("exam_date", "")

        if subject and exam_date:

            conn.execute("""
                INSERT INTO exams
                (subject, exam_date, exam_time)
                VALUES (?, ?, ?)
            """, (subject, exam_date, ""))

            conn.commit()

    exams_data = conn.execute("""
        SELECT *
        FROM exams
        ORDER BY exam_date
    """).fetchall()

    today = date.today().isoformat()

    conn.close()

    return render_template(
        "exams.html",
        exams=exams_data,
        today=today
    )


# ================= EDIT EXAM =================

@app.route("/edit_exam/<int:id>", methods=["GET", "POST"])
def edit_exam(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        exam_date = request.form.get("exam_date", "")

        if subject and exam_date:

            conn.execute("""
                UPDATE exams
                SET subject = ?, exam_date = ?
                WHERE id = ?
            """, (subject, exam_date, id))

            conn.commit()
            conn.close()

            return redirect("/exams")

    exam = conn.execute("""
        SELECT *
        FROM exams
        WHERE id = ?
    """, (id,)).fetchone()

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

    conn.execute(
        "DELETE FROM exams WHERE id = ?",
        (id,)
    )

    conn.commit()
    conn.close()

    return redirect("/exams")


# ================= TIMETABLE =================

@app.route("/timetable", methods=["GET", "POST"])
def timetable():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()

    if request.method == "POST":

        subject = request.form.get("subject", "").strip()
        study_date = request.form.get("study_date", "")
        start_time = request.form.get("start_time", "")
        end_time = request.form.get("end_time", "")
        topic = request.form.get("topic", "").strip()

        if subject and study_date and start_time and end_time and topic:

            conn.execute("""
                INSERT INTO timetable
                (subject, study_date, start_time, end_time, topic)
                VALUES (?, ?, ?, ?, ?)
            """, (
                subject,
                study_date,
                start_time,
                end_time,
                topic
            ))

            conn.commit()

    timetable_data = conn.execute("""
        SELECT *
        FROM timetable
        ORDER BY study_date, start_time
    """).fetchall()

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

    if request.method == "POST":

        subject = request.form.get(
            "subject", ""
        ).strip()

        try:

            total_topics = int(
                request.form.get(
                    "total_topics", 0
                )
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

                conn.execute("""
                    INSERT INTO study_topics
                    (subject, topic, completed)
                    VALUES (?, ?, ?)
                """, (
                    subject,
                    topic,
                    completed
                ))

        conn.commit()

    progress_data = conn.execute("""
        SELECT
            subject,
            COUNT(*) AS total,
            SUM(completed) AS completed
        FROM study_topics
        GROUP BY subject
    """).fetchall()

    topics = conn.execute("""
        SELECT *
        FROM study_topics
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "progress.html",
        progress=progress_data,
        topics=topics
    )


# ================= UPDATE PROGRESS =================

@app.route("/update_progress/<int:id>", methods=["POST"])
def update_progress(id):

    if "username" not in session:
        return redirect("/login")

    conn = get_db()

    conn.execute("""
        UPDATE study_topics
        SET completed = 1
        WHERE id = ?
    """, (id,))

    conn.commit()
    conn.close()

    return redirect("/progress")


# ================= ALERTS =================

@app.route("/alerts")
def alerts():

    if "username" not in session:
        return redirect("/login")

    conn = get_db()

    today = date.today()

    assignments_data = conn.execute("""
        SELECT *
        FROM assignments
        WHERE completed = 0
        ORDER BY due_date
    """).fetchall()

    exams_data = conn.execute("""
        SELECT *
        FROM exams
        ORDER BY exam_date
    """).fetchall()

    timetable_data = conn.execute("""
        SELECT *
        FROM timetable
        ORDER BY study_date, start_time
    """).fetchall()

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
    app.run(debug=True)
