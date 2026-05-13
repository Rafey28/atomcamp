from datetime import datetime, timedelta
from typing import Optional
from db_manager import JSONDatabase
from gemini import generate_quiz, suggest_next_course


class LMSEngine:
    def __init__(self, db: JSONDatabase):
        self.db = db

    def register_student(self, name: str, email: str, goal: str, skill_level: str,
                         background: str = "", time_commitment: int = 5) -> dict:
        now = datetime.now().isoformat()
        return self.db.insert("users", {
            "name": name, "email": email, "role": "student",
            "goal": goal, "skill_level": skill_level,
            "background": background, "time_commitment": time_commitment,
            "created_at": now, "last_login": now,
        })

    def login(self, email: str) -> Optional[dict]:
        users = self.db.find("users", email=email)
        if not users:
            return None
        self.db.update("users", users[0]["id"], {"last_login": datetime.now().isoformat()})
        return users[0]

    def enroll(self, user_id: str, course_id: str) -> Optional[dict]:
        if self.db.find("enrollments", user_id=user_id, course_id=course_id):
            return None
        return self.db.insert("enrollments", {
            "user_id": user_id, "course_id": course_id,
            "enrolled_at": datetime.now().isoformat(),
        })

    def unenroll(self, enrollment_id: str) -> bool:
        return self.db.delete("enrollments", enrollment_id)

    def record_progress(self, user_id: str, module_id: str, score: int) -> dict:
        existing = self.db.find("progress", user_id=user_id, module_id=module_id)
        status = "completed" if score >= 60 else "needs_review"
        module = self.db.get("modules", module_id)
        course = self.db.get("courses", module["course_id"]) if module else None
        instructor_id = course.get("instructor_id") if course else None
        payload = {
            "user_id": user_id, "module_id": module_id,
            "last_score": score, "status": status,
            "attempts": (existing[0].get("attempts", 0) + 1) if existing else 1,
            "updated_at": datetime.now().isoformat(),
            "instructor_id": instructor_id,
        }
        if existing:
            return self.db.update("progress", existing[0]["id"], payload)
        return self.db.insert("progress", payload)

    def get_quiz_for_module(self, user_id: str, module_id: str) -> Optional[dict]:
        module = self.db.get("modules", module_id)
        if not module:
            return None
        user = self.db.get("users", user_id)
        skill_level = user.get("skill_level", "intermediate") if user else "intermediate"
        return generate_quiz(module, skill_level)

    def generate_ai_quiz_for_module(self, user_id: str, module_id: str, fresh: bool = False) -> Optional[dict]:
        return self.get_quiz_for_module(user_id, module_id)

    def submit_quiz_via_ai(self, user_id: str, module_id: str, answers: list[int]) -> dict:
        quiz = self.get_quiz_for_module(user_id, module_id)
        if not quiz:
            return {"error": "Quiz not available"}
        questions = quiz["questions"]
        if len(answers) != len(questions):
            return {"error": "Invalid answers length"}
        correct = sum(1 for i, q in enumerate(questions) if answers[i] == q["answer"])
        score = round(correct / len(questions) * 100)
        progress = self.record_progress(user_id, module_id, score)
        if score >= 80:
            remark = "Excellent work — you clearly understand this module."
        elif score >= 60:
            remark = "Good job! A little more review will make this even stronger."
        else:
            remark = "Keep practicing this topic — focus on the concepts behind the questions."
        return {
            "score": score,
            "correct": correct,
            "total": len(questions),
            "progress": progress,
            "remark": remark,
        }

    def submit_quiz(self, user_id: str, module_id: str, answers: list[int]) -> dict:
        quiz = self.get_quiz_for_module(user_id, module_id)
        if not quiz:
            return {"error": "Quiz not available"}
        questions = quiz["questions"]
        if len(answers) != len(questions):
            return {"error": "Invalid answers length"}
        correct = sum(1 for i, q in enumerate(questions) if answers[i] == q["answer"])
        score = round(correct / len(questions) * 100)
        progress = self.record_progress(user_id, module_id, score)
        return {"score": score, "correct": correct, "total": len(questions), "progress": progress}

    def get_next_course_recommendation(self, user_id: str, course_id: str) -> Optional[dict]:
        if self.course_completion(user_id, course_id) < 100:
            return None
        # Return cached recommendation if exists
        cached = self.db.find("recommendations", user_id=user_id, from_course_id=course_id)
        if cached:
            return {"next_course_id": cached[0]["to_course_id"],
                    "title": cached[0]["title"], "rationale": cached[0]["rationale"]}
        user = self.db.get("users", user_id)
        course = self.db.get("courses", course_id)
        if not user or not course:
            return None
        avg_score = self.course_average(user_id, course_id) or 0
        modules = self.get_course_modules(course_id)
        progress = self.get_user_progress(user_id)
        weakest, min_score = None, 101
        for m in modules:
            p = progress.get(m["id"])
            if p and p["last_score"] < min_score:
                min_score = p["last_score"]
                weakest = m
        enrolled = {e["course_id"] for e in self.db.find("enrollments", user_id=user_id)}
        remaining = [c for c in self.db.all("courses") if c["id"] not in enrolled]
        rec = suggest_next_course(user, course, avg_score, weakest, remaining)
        if rec:
            next_course = self.db.get("courses", rec["next_course_id"])
            if next_course:
                self.db.insert("recommendations", {
                    "user_id": user_id, "from_course_id": course_id,
                    "to_course_id": rec["next_course_id"], "title": next_course["title"],
                    "rationale": rec["rationale"],
                    "recommended_at": datetime.now().isoformat(),
                    "viewed_at": None, "enrolled_at": None,
                })
                return {"next_course_id": rec["next_course_id"],
                        "title": next_course["title"], "rationale": rec["rationale"]}
        return None

    def is_module_unlocked(self, user_id: str, module_id: str) -> bool:
        return bool(self.db.get("modules", module_id))

    def get_xp(self, user_id: str) -> dict:
        progress = self.db.find("progress", user_id=user_id)
        total_xp = sum(p.get("last_score", 0) * 10 for p in progress)
        levels = [(0, "Beginner"), (500, "Explorer"), (1500, "Practitioner"), (3000, "Expert"), (6000, "Master")]
        idx = max(i for i, (t, _) in enumerate(levels) if total_xp >= t)
        level_name = levels[idx][1]
        cur_thresh = levels[idx][0]
        next_thresh = levels[idx + 1][0] if idx + 1 < len(levels) else cur_thresh + 3000
        xp_in = total_xp - cur_thresh
        xp_to = next_thresh - cur_thresh
        return {"total": total_xp, "level": idx + 1, "level_name": level_name,
                "pct": min(100, round(xp_in / xp_to * 100)), "xp_in_level": xp_in, "xp_to_next": xp_to}

    def get_notes(self, user_id: str, course_id: str) -> str:
        rows = self.db.find("notes", user_id=user_id, course_id=course_id)
        return rows[0]["content"] if rows else ""

    def save_notes(self, user_id: str, course_id: str, content: str) -> None:
        self.db.upsert("notes", {"user_id": user_id, "course_id": course_id},
                       {"content": content, "updated_at": datetime.now().isoformat()})

    def recommendation_report(self) -> list[dict]:
        rows = []
        for r in self.db.all("recommendations"):
            user = self.db.get("users", r["user_id"])
            from_course = self.db.get("courses", r["from_course_id"])
            to_course = self.db.get("courses", r["to_course_id"])
            if not user or not from_course or not to_course:
                continue
            enrolled = bool(self.db.find("enrollments", user_id=r["user_id"], course_id=r["to_course_id"]))
            progress_pct = self.course_completion(r["user_id"], r["to_course_id"]) if enrolled else None
            rows.append({
                "student": user, "from_course": from_course, "to_course": to_course,
                "recommended_at": r["recommended_at"][:10],
                "viewed": bool(r.get("viewed_at")),
                "enrolled": enrolled,
                "progress": progress_pct,
            })
        return sorted(rows, key=lambda x: x["recommended_at"], reverse=True)

    def get_course_modules(self, course_id: str) -> list[dict]:
        return sorted(self.db.find("modules", course_id=course_id), key=lambda m: m.get("order", 0))

    def get_user_progress(self, user_id: str) -> dict:
        return {r["module_id"]: r for r in self.db.find("progress", user_id=user_id)}

    def recommend_next_module(self, user_id: str, course_id: str) -> dict:
        modules = self.get_course_modules(course_id)
        progress = self.get_user_progress(user_id)
        for mod in modules:
            p = progress.get(mod["id"])
            if not p:
                return {"action": "start", "module": mod, "reason": "Next module on your learning path."}
            score = p.get("last_score", 0)
            if score < 60:
                return {"action": "review", "module": mod,
                        "reason": f"Your last score of {score}% indicates this concept needs review before moving on."}
            if score >= 90 and mod.get("advanced_id"):
                adv = self.db.get("modules", mod["advanced_id"])
                if adv:
                    return {"action": "advance", "module": adv,
                            "reason": f"Strong score of {score}% — advancing to {adv['title']}."}
        return {"action": "complete", "module": None, "reason": "Course complete. All modules passed."}

    def personalized_path(self, user_id: str) -> list[dict]:
        path = []
        for e in self.db.find("enrollments", user_id=user_id):
            course = self.db.get("courses", e["course_id"])
            if not course:
                continue
            rec = self.recommend_next_module(user_id, course["id"])
            avg = self.course_average(user_id, course["id"])
            completion = self.course_completion(user_id, course["id"])
            next_course = self.get_next_course_recommendation(user_id, course["id"]) if completion == 100 else None
            # Build module nodes for journey map
            modules = self.get_course_modules(course["id"])
            progress = self.get_user_progress(user_id)
            found_current = False
            module_nodes = []
            for m in modules:
                p = progress.get(m["id"])
                if p:
                    state = "completed" if p["last_score"] >= 60 else "failed"
                elif not found_current:
                    state = "current"
                    found_current = True
                else:
                    state = "upcoming"
                module_nodes.append({"module": m, "progress": p, "state": state})
            path.append({"course": course, "enrollment_id": e["id"], "recommendation": rec,
                         "avg": avg, "completion": completion, "next_course": next_course,
                         "module_nodes": module_nodes})
        return path

    def course_average(self, user_id: str, course_id: str) -> Optional[float]:
        modules = self.get_course_modules(course_id)
        progress = self.get_user_progress(user_id)
        scores = [progress[m["id"]]["last_score"] for m in modules if m["id"] in progress]
        return round(sum(scores) / len(scores), 1) if scores else None

    def course_completion(self, user_id: str, course_id: str) -> int:
        modules = self.get_course_modules(course_id)
        if not modules:
            return 0
        progress = self.get_user_progress(user_id)
        completed = sum(1 for m in modules if progress.get(m["id"], {}).get("status") == "completed")
        return round(completed / len(modules) * 100)

    def at_risk_students(self, inactive_days: int = 7, failing_threshold: float = 60) -> list[dict]:
        students = self.db.find("users", role="student")
        cutoff = datetime.now() - timedelta(days=inactive_days)
        flagged = []
        for s in students:
            reasons = []
            try:
                last = datetime.fromisoformat(s.get("last_login", s["created_at"]))
                if last < cutoff:
                    reasons.append(f"Inactive {(datetime.now() - last).days} days")
            except (ValueError, KeyError):
                pass
            prog = self.db.find("progress", user_id=s["id"])
            if prog:
                avg = sum(p["last_score"] for p in prog) / len(prog)
                if avg < failing_threshold:
                    reasons.append(f"Average score {avg:.0f}%")
                retries = [p for p in prog if p.get("attempts", 1) >= 3 and p["last_score"] < 60]
                if retries:
                    reasons.append(f"{len(retries)} module(s) failed after 3+ attempts")
            elif self.db.find("enrollments", user_id=s["id"]):
                reasons.append("Enrolled but no quiz attempts yet")
            if reasons:
                flagged.append({"student": s, "reasons": reasons})
        return flagged

    def module_difficulty_report(self) -> list[dict]:
        report = []
        for mod in self.db.all("modules"):
            attempts = self.db.find("progress", module_id=mod["id"])
            if not attempts:
                continue
            avg = sum(a["last_score"] for a in attempts) / len(attempts)
            pass_rate = sum(1 for a in attempts if a["last_score"] >= 60) / len(attempts) * 100
            course = self.db.get("courses", mod["course_id"])
            report.append({
                "module": mod, "course": course,
                "attempts": len(attempts),
                "avg_score": round(avg, 1),
                "pass_rate": round(pass_rate),
            })
        return sorted(report, key=lambda r: r["pass_rate"])

    def engagement_metrics(self) -> dict:
        students = self.db.find("users", role="student")
        now = datetime.now()
        active_7d = active_30d = 0
        for s in students:
            try:
                last = datetime.fromisoformat(s.get("last_login", s["created_at"]))
                if last > now - timedelta(days=7): active_7d += 1
                if last > now - timedelta(days=30): active_30d += 1
            except (ValueError, KeyError):
                pass
        return {
            "active_7d": active_7d, "active_30d": active_30d,
            "total_students": len(students),
            "engagement_rate": round(active_7d / len(students) * 100) if students else 0,
        }

    def top_performers(self, limit: int = 5) -> list[dict]:
        students = self.db.find("users", role="student")
        scored = []
        for s in students:
            prog = self.db.find("progress", user_id=s["id"])
            if not prog:
                continue
            avg = sum(p["last_score"] for p in prog) / len(prog)
            scored.append({"student": s, "avg": round(avg, 1), "modules": len(prog)})
        return sorted(scored, key=lambda x: x["avg"], reverse=True)[:limit]

    def _course_heatmap(self) -> list[dict]:
        result = []
        for course in self.db.all("courses"):
            modules = self.get_course_modules(course["id"])
            rows = []
            for m in modules:
                attempts = self.db.find("progress", module_id=m["id"])
                if not attempts:
                    rows.append({"title": m["title"], "order": m["order"],
                                 "avg_score": None, "pass_rate": None, "attempts": 0})
                    continue
                avg = sum(a["last_score"] for a in attempts) / len(attempts)
                pass_rate = sum(1 for a in attempts if a["last_score"] >= 60) / len(attempts) * 100
                rows.append({"title": m["title"], "order": m["order"],
                             "avg_score": round(avg, 1), "pass_rate": round(pass_rate), "attempts": len(attempts)})
            if any(r["attempts"] > 0 for r in rows):
                result.append({"course": course, "modules": rows})
        return result

    def instructor_overview(self) -> dict:
        progress = self.db.all("progress")
        avg = round(sum(p["last_score"] for p in progress) / len(progress), 1) if progress else 0
        engagement = self.engagement_metrics()
        return {
            "total_students": engagement["total_students"],
            "total_courses": len(self.db.all("courses")),
            "total_modules": len(self.db.all("modules")),
            "total_attempts": len(progress),
            "overall_average": avg,
            "engagement": engagement,
            "at_risk": self.at_risk_students(),
            "difficulty": self.module_difficulty_report(),
            "top_performers": self.top_performers(),
            "heatmap": self._course_heatmap(),
        }
