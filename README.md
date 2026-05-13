# AtomCamp Adaptive LMS

## Problem Statement

Traditional Learning Management Systems offer a one-size-fits-all approach that fails to address the diverse backgrounds, goals, and learning paces of students in tech bootcamps. Students with different skill levels are forced through the same content at the same speed, leading to disengagement, high dropout rates, and poor learning outcomes. Instructors also lack real-time visibility into student struggles, making it difficult to intervene before students fall behind.

**AtomCamp** solves this by delivering a fully adaptive, AI-powered learning experience that personalizes content progression, generates dynamic quizzes, and gives instructors actionable analytics — all in one platform.

---

## Features

### Student Features
- **Personalized Dashboard** — View enrolled courses, learning path, XP, and level progression
- **Adaptive Course Enrollment** — Auto-enroll in courses matched to your stated learning goals
- **AI-Generated Quizzes** — Module quizzes dynamically created by Google Gemini, tailored to skill level
- **Module Progression** — Sequential module unlocking; score 60%+ to advance
- **AI Course Recommendations** — Get next-course suggestions based on performance and identified weaknesses
- **Notes & Annotations** — Save personal notes per course
- **Progress Tracking** — Track module completion, quiz scores, attempts, and total XP

### Instructor Features
- **Analytics Dashboard** — Real-time overview of students, courses, modules, and engagement
- **At-Risk Student Detection** — Flags students inactive for 7+ days or scoring below 60%
- **Module Difficulty Report** — Pass rates and average scores per module across all students
- **Engagement Metrics** — Active users over 7-day and 30-day windows with engagement rate
- **Top Performers Leaderboard** — Ranking of highest-achieving students
- **Course Heatmap** — Visual matrix of module difficulty and performance across all tracks
- **Video Management** — Upload, replace, and delete instructional videos per module
- **Student Nudges** — Send re-engagement nudges to inactive students
- **Recommendation Report** — Track which AI recommendations were viewed or enrolled in

### General
- **Multi-Role System** — Separate student and instructor account types
- **Course Catalogue** — Browse all 6 bootcamp tracks with module counts and enrollment status
- **Gamified XP System** — Earn XP from quiz scores and progress through 6 levels: Beginner → Explorer → Practitioner → Expert → Master

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend Framework | Flask 3.0.0 (Python) |
| AI Integration | Google Gemini 2.5 Flash API |
| Database | JSON file-based persistence (custom `db_manager.py`) |
| Frontend | Jinja2 templating, HTML, CSS, JavaScript |
| File Storage | Local filesystem (`/static/videos/`) |

---

## Steps to Run the Project

### Prerequisites
- Python 3.8+
- A Google Gemini API key ([get one here](https://aistudio.google.com/))

### 1. Clone the Repository
```bash
git clone https://github.com/Rafey28/atomcamp.git
cd atomcamp
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure the Gemini API Key
Open `config.py` and replace the placeholder with your API key:
```python
GEMINI_API_KEY = "your-gemini-api-key-here"
GEMINI_MODEL = "gemini-2.5-flash"
```

### 4. Run the Application
```bash
python app.py
```

The app will start at `http://localhost:5000`. The database is seeded automatically on the first run.

### 5. Demo Login Credentials
No passwords required — just enter the email to log in.

| Role | Email |
|---|---|
| Student | hassan@demo.com |
| Student | fatima@demo.com |
| Student | omar@demo.com |
| Instructor | ayesha@atomcamp.com |
| Instructor | bilal@atomcamp.com |

---

## Team Members

- **Muhammad Okasha**
- **Abdul Rafey**
