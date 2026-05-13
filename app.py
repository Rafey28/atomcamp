from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from db_manager import JSONDatabase
from lms_engine import LMSEngine
from seed import seed_data
from werkzeug.utils import secure_filename
from datetime import datetime
import os

UPLOAD_FOLDER = os.path.join("static", "videos")
ALLOWED_EXTENSIONS = {"mp4", "webm", "mov", "mkv"}
MAX_VIDEO_MB = 500


def allowed_video(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)
app.secret_key = "atomcamp-lms-secret"
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_MB * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = JSONDatabase()
engine = LMSEngine(db)

# In-memory quiz store keyed by (user_id, module_id) — avoids cookie size limits
_quiz_store: dict = {}

if not os.path.exists("data/courses.json"):
    seed_data()


GOAL_TO_COURSE = {
    "Data Science": "c_ds", "AI": "c_genai", "Web Development": "c_web",
    "Marketing": "c_dm", "Product": "c_pm", "Analytics": "c_da",
}


def current_user():
    uid = session.get("user_id")
    return db.get("users", uid) if uid else None


@app.context_processor
def inject_user():
    return {"user": current_user()}


@app.route("/")
def index():
    user = current_user()
    if user:
        return redirect(url_for("instructor" if user["role"] == "instructor" else "dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        form = request.form
        if db.find("users", email=form["email"]):
            flash("That email is already registered.", "error")
            return redirect(url_for("register"))
        user = engine.register_student(
            form["name"], form["email"], form["goal"], form["skill_level"],
            form.get("background", ""), int(form.get("time_commitment", 5)),
        )
        session["user_id"] = user["id"]
        goal_course = GOAL_TO_COURSE.get(user["goal"])
        if goal_course:
            engine.enroll(user["id"], goal_course)
        flash(f"Welcome, {user['name'].split(' ')[0]} — your path is ready.", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = engine.login(request.form["email"])
        if not user:
            flash("No account found with that email.", "error")
            return redirect(url_for("login"))
        session["user_id"] = user["id"]
        return redirect(url_for("instructor" if user["role"] == "instructor" else "dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/catalogue")
def catalogue():
    user = current_user()
    courses = db.all("courses")
    module_counts = {c["id"]: len(db.find("modules", course_id=c["id"])) for c in courses}
    enrolled_ids = set()
    if user and user["role"] == "student":
        enrolled_ids = {e["course_id"] for e in db.find("enrollments", user_id=user["id"])}
    return render_template("catalogue.html", courses=courses,
                           module_counts=module_counts, enrolled_ids=enrolled_ids)


@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    path = engine.personalized_path(user["id"])
    xp = engine.get_xp(user["id"])
    all_courses = db.all("courses")
    enrolled_ids = {p["course"]["id"] for p in path}
    goal_track = {"Data Science": "Data Science", "AI": "AI", "Web Development": "Web Development",
                  "Marketing": "Marketing", "Product": "Product", "Analytics": "Analytics"}.get(user["goal"])
    recommended = [c for c in all_courses if c["id"] not in enrolled_ids]
    if goal_track:
        recommended = sorted(recommended, key=lambda c: 0 if c["track"] == goal_track else 1)
    return render_template("dashboard.html", path=path, recommended=recommended[:3], xp=xp)


@app.route("/enroll/<course_id>", methods=["POST"])
def enroll(course_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    engine.enroll(user["id"], course_id)
    # Track enrollment against recommendation if exists
    recs = db.find("recommendations", user_id=user["id"], to_course_id=course_id)
    if recs and not recs[0].get("enrolled_at"):
        db.update("recommendations", recs[0]["id"], {"enrolled_at": datetime.now().isoformat()})
    flash("Enrolled. Your path has been updated.", "success")
    return redirect(url_for("course", course_id=course_id))


@app.route("/unenroll/<enrollment_id>", methods=["POST"])
def unenroll(enrollment_id):
    engine.unenroll(enrollment_id)
    flash("Enrollment removed.", "success")
    return redirect(url_for("dashboard"))


@app.route("/course/<course_id>")
def course(course_id):
    user = current_user()
    course = db.get("courses", course_id)
    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("catalogue"))
    modules = engine.get_course_modules(course_id)
    progress, avg, rec, unlocked, next_course, completion = None, None, None, {}, None, 0
    if user and user["role"] == "student":
        progress = engine.get_user_progress(user["id"])
        avg = engine.course_average(user["id"], course_id)
        rec = engine.recommend_next_module(user["id"], course_id)
        completion = engine.course_completion(user["id"], course_id)
        unlocked = {m["id"]: engine.is_module_unlocked(user["id"], m["id"]) for m in modules}
        if completion == 100:
            next_course = engine.get_next_course_recommendation(user["id"], course_id)
    is_enrolled = bool(db.find("enrollments", user_id=user["id"], course_id=course_id)) if user else False
    return render_template("course.html", course=course, modules=modules, progress=progress,
                           avg=avg, rec=rec, is_enrolled=is_enrolled, unlocked=unlocked,
                           next_course=next_course, completion=completion)

@app.route("/module/<module_id>")
def module(module_id):
    user = current_user()
    mod = db.get("modules", module_id)
    if not mod:
        flash("Module not found.", "error")
        return redirect(url_for("catalogue"))
    course = db.get("courses", mod["course_id"])
    if not course:
        flash("Course data missing.", "error")
        return redirect(url_for("catalogue"))
    progress = None
    avg = None
    if user and user["role"] == "student":
        if not engine.is_module_unlocked(user["id"], module_id):
            flash("Complete the previous module's quiz first to unlock this one.", "error")
            return redirect(url_for("course", course_id=mod["course_id"]))
        progress = engine.get_user_progress(user["id"]).get(module_id)
        avg = engine.course_average(user["id"], mod["course_id"])
    return render_template("module.html", mod=mod, course=course, progress=progress, avg=avg)

@app.route("/module/<module_id>/ai_quiz")
def module_ai_quiz(module_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 403
    if user["role"] == "student" and not engine.is_module_unlocked(user["id"], module_id):
        return jsonify({"error": "Module locked. Complete the previous module first."}), 403
    module = db.get("modules", module_id)
    if not module:
        return jsonify({"error": "Module not found"}), 404
    from gemini import generate_quiz
    skill_level = user.get("skill_level", "intermediate")
    quiz = generate_quiz(module, skill_level)
    if not quiz:
        return jsonify({"error": "AI service unavailable. Please try again."}), 500
    _quiz_store[(user["id"], module_id)] = quiz
    return jsonify({"quiz": quiz})


@app.route("/module/<module_id>/submit_ai_quiz", methods=["POST"])
def submit_ai_quiz(module_id):
    user = current_user()
    if not user:
        return jsonify({"error": "Authentication required"}), 403
    quiz = _quiz_store.get((user["id"], module_id))
    if not quiz:
        return jsonify({"error": "Quiz expired. Please generate a new quiz."}), 400
    data = request.get_json(silent=True) or {}
    answers = data.get("answers", [])
    questions = quiz["questions"]
    if len(answers) != len(questions):
        return jsonify({"error": "Answer count mismatch."}), 400
    correct = sum(1 for i, q in enumerate(questions) if answers[i] == q["answer"])
    score = round(correct / len(questions) * 100)
    engine.record_progress(user["id"], module_id, score)
    _quiz_store.pop((user["id"], module_id), None)
    if score >= 80:
        remark = "Excellent work — you clearly understand this module."
    elif score >= 60:
        remark = "Good job! A little more review will make this even stronger."
    else:
        remark = "Keep practicing — focus on the concepts behind the questions."
    return jsonify({"score": score, "correct": correct, "total": len(questions), "remark": remark})


@app.route("/instructor")
def instructor():
    user = current_user()
    if not user or user["role"] != "instructor":
        flash("Instructor access required.", "error")
        return redirect(url_for("login"))
    overview = engine.instructor_overview()
    students = db.find("users", role="student")
    courses = db.all("courses")
    course_modules = {c["id"]: engine.get_course_modules(c["id"]) for c in courses}
    rec_report = engine.recommendation_report()
    return render_template("instructor.html", overview=overview, students=students,
                           courses=courses, course_modules=course_modules, rec_report=rec_report)


@app.route("/instructor/upload-video/<module_id>", methods=["POST"])
def upload_video(module_id):
    user = current_user()
    if not user or user["role"] != "instructor":
        return jsonify({"error": "Unauthorized"}), 403
    mod = db.get("modules", module_id)
    if not mod:
        return jsonify({"error": "Module not found"}), 404
    if "video" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["video"]
    if not f.filename or not allowed_video(f.filename):
        return jsonify({"error": "Invalid file type. Allowed: mp4, webm, mov, mkv"}), 400
    ext = f.filename.rsplit(".", 1)[1].lower()
    # Remove old video if exists
    old_url = mod.get("video_url", "")
    if old_url:
        old_path = os.path.join("static", old_url.lstrip("/static/").lstrip("static/"))
        if os.path.exists(old_path):
            os.remove(old_path)
    filename = f"{module_id}.{ext}"
    save_path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(save_path)
    video_url = f"/static/videos/{filename}"
    db.update("modules", module_id, {"video_url": video_url})
    return jsonify({"video_url": video_url})


@app.route("/instructor/delete-video/<module_id>", methods=["POST"])
def delete_video(module_id):
    user = current_user()
    if not user or user["role"] != "instructor":
        return jsonify({"error": "Unauthorized"}), 403
    mod = db.get("modules", module_id)
    if not mod:
        return jsonify({"error": "Module not found"}), 404
    video_url = mod.get("video_url", "")
    if video_url:
        path = os.path.join("static", "videos", os.path.basename(video_url))
        if os.path.exists(path):
            os.remove(path)
        db.update("modules", module_id, {"video_url": ""})
    return jsonify({"ok": True})


@app.route("/instructor/nudge/<user_id>", methods=["POST"])
def nudge_student(user_id):
    user = current_user()
    if not user or user["role"] != "instructor":
        return jsonify({"error": "Unauthorized"}), 403
    db.update("users", user_id, {"last_nudge": datetime.now().isoformat()})
    return jsonify({"ok": True})


@app.route("/instructor/assign-review/<user_id>/<module_id>", methods=["POST"])
def assign_review(user_id, module_id):
    user = current_user()
    if not user or user["role"] != "instructor":
        return jsonify({"error": "Unauthorized"}), 403
    existing = db.find("progress", user_id=user_id, module_id=module_id)
    if existing:
        db.update("progress", existing[0]["id"], {"status": "needs_review", "instructor_flagged": True})
    else:
        db.insert("progress", {"user_id": user_id, "module_id": module_id,
                               "status": "needs_review", "instructor_flagged": True,
                               "last_score": 0, "attempts": 0,
                               "updated_at": datetime.now().isoformat()})
    return jsonify({"ok": True})


@app.route("/suggested/<course_id>")
def suggested_course(course_id):
    user = current_user()
    if not user or user["role"] != "student":
        return redirect(url_for("login"))
    course = db.get("courses", course_id)
    if not course:
        flash("Course not found.", "error")
        return redirect(url_for("dashboard"))
    modules = engine.get_course_modules(course_id)
    notes = engine.get_notes(user["id"], course_id)
    # Mark recommendation as viewed
    recs = db.find("recommendations", user_id=user["id"], to_course_id=course_id)
    if recs and not recs[0].get("viewed_at"):
        db.update("recommendations", recs[0]["id"], {"viewed_at": datetime.now().isoformat()})
    rationale = recs[0].get("rationale") if recs else None
    is_enrolled = bool(db.find("enrollments", user_id=user["id"], course_id=course_id))
    return render_template("suggested_course.html", course=course, modules=modules,
                           notes=notes, rationale=rationale, is_enrolled=is_enrolled)


@app.route("/notes/save", methods=["POST"])
def save_notes():
    user = current_user()
    if not user:
        return jsonify({"error": "Not authenticated"}), 403
    data = request.get_json(silent=True) or {}
    course_id = data.get("course_id")
    content = data.get("content", "")
    if not course_id:
        return jsonify({"error": "Missing course_id"}), 400
    engine.save_notes(user["id"], course_id, content)
    return jsonify({"ok": True})


@app.route("/api/data/<table>")
def api_data(table):
    if table not in ["users", "courses", "modules", "enrollments", "progress", "quizzes", "recommendations", "notes"]:
        return jsonify({"error": "invalid table"}), 404
    return jsonify(db.all(table))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
