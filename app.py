from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import date, datetime
import os, sqlite3

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
app.secret_key = os.environ.get("SECRET_KEY", "local-development-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ddyy1016")

# 모든 평일 하루 최대 1팀으로 변경, 최대 인원은 4명 유지
MAX_TEAMS = 1
MAX_MEMBERS = 4

# 주말(토, 일) 여부를 판별하는 백엔드 함수
def is_weekend(target_date):
    # weekday() 기준 5: 토요일, 6: 일요일
    return target_date.weekday() >= 5

DB_PATH = "billiards.db"

def pg():
    return bool(os.environ.get("DATABASE_URL"))

def get_db():
    if pg():
        if psycopg is None:
            raise RuntimeError("psycopg가 설치되지 않았습니다.")
        return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = get_db()
    try:
        if pg():
            c.execute("""CREATE TABLE IF NOT EXISTS bookings(
                id SERIAL PRIMARY KEY, booking_date TEXT NOT NULL, team_no INTEGER NOT NULL,
                name TEXT NOT NULL, student_id TEXT NOT NULL, members TEXT NOT NULL,
                created_at TEXT NOT NULL)""")
            c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_booking_team
                         ON bookings(booking_date, team_no)""")
        else:
            c.execute("""CREATE TABLE IF NOT EXISTS bookings(
                id INTEGER PRIMARY KEY AUTOINCREMENT, booking_date TEXT NOT NULL,
                team_no INTEGER NOT NULL, name TEXT NOT NULL, student_id TEXT NOT NULL,
                members TEXT NOT NULL, created_at TEXT NOT NULL)""")
            c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_booking_team
                         ON bookings(booking_date, team_no)""")
        c.commit()
    finally:
        c.close()

def allowed_date(s):
    try:
        today = date.today()
        target = datetime.strptime(s, "%Y-%m-%d").date()
        
        # 주말인 경우 예약 가능 날짜에서 원천 제외
        if is_weekend(target):
            return False
            
        try:
            end = today.replace(year=today.year + 10)
        except ValueError:
            end = today.replace(year=today.year + 10, day=28)
        return today <= target <= end
    except ValueError:
        return False

def rows_for_date(d):
    c = get_db()
    try:
        q = "SELECT * FROM bookings WHERE booking_date=%s ORDER BY team_no" if pg() else "SELECT * FROM bookings WHERE booking_date=? ORDER BY team_no"
        return c.execute(q, (d,)).fetchall()
    finally:
        c.close()

@app.before_request
def db_ready():
    init_db()

@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/calendar")
def calendar():
    c = get_db()
    try:
        rows = c.execute("SELECT booking_date,
