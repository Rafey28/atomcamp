import json
import urllib.request
import urllib.error
from typing import Optional
from config import GEMINI_API_KEY, GEMINI_MODEL

ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


import time

def _call(prompt: str, temperature: float = 0.7, timeout: int = 45) -> Optional[dict]:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": temperature,
        },
    }
    retries = 5
    backoff = 2
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            f"{ENDPOINT}?key={GEMINI_API_KEY}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = json.loads(r.read().decode("utf-8"))
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries:
                print(f"[gemini] {e.code}, retrying in {backoff}s... ({attempt}/{retries})")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            print(f"[gemini] http error {e.code}: {e.read().decode()[:200]}")
            return None
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
            if attempt < retries:
                print(f"[gemini] transient error, retrying in {backoff}s... ({attempt}/{retries}) {e}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            print(f"[gemini] failed after {retries} attempts: {e}")
            return None


def generate_quiz(module: dict, skill_level: str = "intermediate") -> Optional[dict]:
    objectives = "\n".join(f"- {o}" for o in module.get("objectives", []))
    prompt = f"""You are an expert curriculum designer for atomcamp, a leading tech-education platform.

Generate EXACTLY 5 challenging multiple-choice questions to test deep understanding of the module below. Questions must be conceptual, scenario-based, or test edge cases — NOT trivia or recall. Each question has EXACTLY 4 options; exactly one is correct.

Module: {module['title']}
Module content: {module['content']}
Learning objectives:
{objectives}

Target learner skill level: {skill_level}

Requirements:
- Vary the position of the correct option across questions (do not always make option 0 correct).
- Make every distractor plausible to a learner who has not mastered the concept.
- Cover different aspects of the module, not the same concept five times.
- Questions and options must be self-contained (no "all of the above" / "none of the above" / no references to "the previous question").

Return ONLY valid JSON in this exact shape, no surrounding text:
{{
  "questions": [
    {{"q": "<question text>", "options": ["<a>", "<b>", "<c>", "<d>"], "answer": <0|1|2|3>}}
  ]
}}"""
    result = _call(prompt, temperature=0.9)
    if not result or "questions" not in result:
        return None
    questions = result["questions"]
    if not isinstance(questions, list) or len(questions) < 3:
        return None
    valid = [q for q in questions
             if isinstance(q.get("options"), list) and len(q["options"]) == 4
             and isinstance(q.get("answer"), int) and 0 <= q["answer"] <= 3
             and isinstance(q.get("q"), str)]
    if len(valid) < 3:
        return None
    return {"questions": valid[:5]}


def suggest_next_course(user: dict, completed_course: dict, avg_score: float,
                        weakest_module: Optional[dict], remaining_courses: list[dict]) -> Optional[dict]:
    catalogue = "\n".join(
        f"- id={c['id']} | {c['title']} ({c['track']}, {c['level']}, {c['duration_weeks']} weeks): {c['description']}"
        for c in remaining_courses
    )
    weak = weakest_module["title"] if weakest_module else "none — strong throughout"
    prompt = f"""You are a senior academic advisor for atomcamp, a tech-education platform serving learners across Pakistan and beyond.

A student has just completed a bootcamp. Recommend the single best next program from the catalogue.

STUDENT PROFILE
- Name: {user['name']}
- Stated career goal: {user.get('goal', 'unspecified')}
- Skill level: {user.get('skill_level', 'unspecified')}
- Background: {user.get('background', 'unspecified')}
- Time commitment: {user.get('time_commitment', 'unspecified')} hours per week

JUST COMPLETED
- Program: {completed_course['title']} ({completed_course['track']})
- Average score across modules: {avg_score:.0f}%
- Weakest module: {weak}

REMAINING CATALOGUE
{catalogue}

Pick the ONE program that best advances this specific learner's stated goal, accounting for their performance and time budget. Avoid generic answers — reference their goal and what they just completed.

Return ONLY valid JSON, no surrounding text:
{{
  "next_course_id": "<one of the ids above>",
  "rationale": "<2-3 concise sentences explaining why this is the right next step for this specific learner>"
}}"""
    result = _call(prompt, temperature=0.5)
    if not result or "next_course_id" not in result:
        return None
    if result["next_course_id"] not in [c["id"] for c in remaining_courses]:
        return None
    return result
