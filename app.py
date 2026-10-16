from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import date, datetime
import os, sqlite3, json

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

# 구글 시트 연동 라이브러리
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
app.secret_key = os.environ.get("SECRET_KEY", "local-development-secret-key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ddyy1016")

# 모든 평일 하루 최대 1팀으로 변경, 최대 인원은 4명 유지
MAX_TEAMS = 1
MAX_MEMBERS = 4

# Render 환경 변수에서 구글 시트 주소와 인증 정보를 불러옴
SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL", "https://docs.google.com/spreadsheets/d/1f00pdqXWqFAF14QfyKDu3V-3LlV8orSnBhAghaMGJNg/edit")
CREDENTIALS_JSON_STR = os.environ.get("GOOGLE_CREDENTIALS_JSON")

def get_sheet():
    try:
        if not CREDENTIALS_JSON_STR:
            print("구글 시트 인증 정보(GOOGLE_CREDENTIALS_JSON) 환경 변수가 없습니다.")
            return None
        
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Render 환경변수 텍스트 정제 (양끝 공백/따옴표 제거)
        raw_json = CREDENTIALS_JSON_STR.strip()
        if (raw_json.startswith("'") and raw_json.endswith("'")) or (raw_json.startswith('"') and raw_json.endswith('"')):
            raw_json = raw_json[1:-1].strip()
            
        # 개행 문자 처리 및 strict=False 적용
        raw_json = raw_json.replace('\r\n', '\n').replace('\r', '\n')
        creds_dict = json.loads(raw_json, strict=False)
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client.open_by_url(SPREADSHEET_URL).sheet1
    except Exception as e:
        print(f"구글 시트 연결 오류 상세: {e}")
        return None

# 주말(토, 일) 여부를 판별하는 백엔드 함수
def is_weekend(target_date):
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
        rows = c.execute("SELECT booking_date, COUNT(*) AS count FROM bookings GROUP BY booking_date").fetchall()
        return jsonify({r["booking_date"]: r["count"] for r in rows})
    finally:
        c.close()

@app.get("/api/bookings/<booking_date>")
def date_bookings(booking_date):
    if not allowed_date(booking_date):
        return jsonify({"error":"주말이거나 올바르지 않은 날짜입니다."}),400

    rows = rows_for_date(booking_date)

    return jsonify({
        "date":booking_date,
        "count":len(rows),
        "teams":[
            {
                "team_no":r["team_no"],
                "name":r["name"],
                "student_id":r["student_id"],
                "members":r["members"].split(",") if r["members"] else []
            } for r in rows
        ]
    })

@app.post("/api/book")
def book():
    data = request.get_json(silent=True) or {}

    d = (data.get("date") or "").strip()
    name = (data.get("name") or "").strip()
    sid = (data.get("student_id") or "").strip()
    extra = data.get("members") or []

    if not allowed_date(d):
        return jsonify({"error":"주말에는 예약할 수 없으며, 오늘부터 10년 이내의 날짜만 예약 가능합니다."}),400

    if not name:
        return jsonify({"error":"예약자 이름을 입력해주세요."}),400

    if not sid:
        return jsonify({"error":"예약자 학번을 입력해주세요."}),400

    members = [sid] + [str(x).strip() for x in extra if str(x).strip()]

    if len(members) > MAX_MEMBERS:
        return jsonify({"error":"한 팀은 예약자를 포함해 최대 4명까지 가능합니다."}),400

    if len(set(members)) != len(members):
        return jsonify({"error":"같은 학번을 중복해서 입력할 수 없습니다."}),400

    c = get_db()

    try:
        target_dt = datetime.strptime(d, "%Y-%m-%d").date()
        if is_weekend(target_dt):
            return jsonify({"error":"주말에는 예약할 수 없습니다."}),400

        max_teams = MAX_TEAMS
        created_at_str = datetime.now().isoformat(timespec="seconds")

        if pg():
            with c.transaction():
                c.execute(
                    "SELECT id FROM bookings WHERE booking_date=%s FOR UPDATE",
                    (d,)
                )

                count = c.execute(
                    "SELECT COUNT(*) AS count FROM bookings WHERE booking_date=%s",
                    (d,)
                ).fetchone()["count"]

                if count >= max_teams:
                    return jsonify({"error":"이 날짜는 이미 예약이 마감되었습니다."}),409

                used = {
                    r["team_no"]
                    for r in c.execute(
                        "SELECT team_no FROM bookings WHERE booking_date=%s",
                        (d,)
                    ).fetchall()
                }

                team = next(
                    n for n in range(1, max_teams + 1)
                    if n not in used
                )

                bid = c.execute(
                    """INSERT INTO bookings(
                        booking_date, team_no, name, student_id, members, created_at
                    ) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (
                        d, team, name, sid,
                        ",".join(members),
                        created_at_str
                    )
                ).fetchone()["id"]

        else:
            c.execute("BEGIN IMMEDIATE")

            count = c.execute(
                "SELECT COUNT(*) FROM bookings WHERE booking_date=?",
                (d,)
            ).fetchone()[0]

            if count >= max_teams:
                c.rollback()
                return jsonify({"error":"이 날짜는 이미 예약이 마감되었습니다."}),409

            used = {
                r["team_no"]
                for r in c.execute(
                    "SELECT team_no FROM bookings WHERE booking_date=?",
                    (d,)
                ).fetchall()
            }

            team = next(
                n for n in range(1, max_teams + 1)
                if n not in used
            )

            cur = c.execute(
                """INSERT INTO bookings(
                    booking_date, team_no, name, student_id, members, created_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    d, team, name, sid,
                    ",".join(members),
                    created_at_str
                )
            )

            c.commit()
            bid = cur.lastrowid

        # 구글 시트에 실시간 추가
        sheet = get_sheet()
        if sheet:
            try:
                sheet.append_row([str(d), int(team), str(name), str(sid), ", ".join(members), str(created_at_str)])
            except Exception as e:
                print(f"구글 시트 행 추가 실패: {e}")

        return jsonify({
            "success": True,
            "booking": {
                "id": bid,
                "date": d,
                "team_no": team,
                "name": name,
                "student_id": sid,
                "members": members
            }
        })

    except Exception as e:
        try:
            c.rollback()
        except:
            pass

        return jsonify({
            "error": "예약 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
        }), 500

    finally:
        c.close()

@app.post("/api/lookup")
def lookup():
    sid = ((request.get_json(silent=True) or {}).get("student_id") or "").strip()

    if not sid:
        return jsonify({"error":"학번을 입력해주세요."}), 400

    c = get_db()

    try:
        rows = c.execute(
            "SELECT * FROM bookings ORDER BY booking_date, team_no"
        ).fetchall()
    finally:
        c.close()

    result = []

    for r in rows:
        m = r["members"].split(",") if r["members"] else []

        if sid == r["student_id"] or sid in m:
            result.append({
                "date": r["booking_date"],
                "team_no": r["team_no"],
                "name": r["name"],
                "student_id": r["student_id"],
                "members": m
            })

    return jsonify({"bookings": result})

@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password","") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))

        return render_template(
            "admin_login.html",
            error="비밀번호가 올바르지 않습니다."
        )

    if not session.get("admin"):
        return render_template("admin_login.html")

    return render_template("admin.html")

@app.post("/admin/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.get("/api/admin/bookings")
def admin_bookings():
    if not session.get("admin"):
        return jsonify({"error":"관리자 인증이 필요합니다."}), 401

    c = get_db()

    try:
        rows = c.execute(
            "SELECT * FROM bookings ORDER BY booking_date, team_no"
        ).fetchall()
    finally:
        c.close()

    return jsonify({
        "bookings": [
            {
                "id": r["id"],
                "date": r["booking_date"],
                "team_no": r["team_no"],
                "name": r["name"],
                "student_id": r["student_id"],
                "members": r["members"].split(",") if r["members"] else []
            }
            for r in rows
        ]
    })

@app.delete("/api/admin/bookings/<int:booking_id>")
def delete_booking(booking_id):
    if not session.get("admin"):
        return jsonify({"error":"관리자 인증이 필요합니다."}), 401

    c = get_db()

    try:
        q_sel = "SELECT booking_date, team_no FROM bookings WHERE id=%s" if pg() else "SELECT booking_date, team_no FROM bookings WHERE id=?"
        target_row = c.execute(q_sel, (booking_id,)).fetchone()

        q = "DELETE FROM bookings WHERE id=%s" if pg() else "DELETE FROM bookings WHERE id=?"
        cur = c.execute(q, (booking_id,))
        c.commit()
        deleted = cur.rowcount

        if deleted and target_row:
            sheet = get_sheet()
            if sheet:
                try:
                    b_date = str(target_row["booking_date"])
                    b_team = str(target_row["team_no"])
                    
                    records = sheet.get_all_values()
                    for idx, row in enumerate(records[1:], start=2):
                        if len(row) >= 2 and row[0] == b_date and str(row[1]) == b_team:
                            sheet.delete_rows(idx)
                            break
                except Exception as e:
                    print(f"구글 시트 행 삭제 실패: {e}")

    finally:
        c.close()

    if not deleted:
        return jsonify({"error":"예약을 찾을 수 없습니다."}), 404

    return jsonify({"success": True})

@app.get("/api/admin/backup")
def admin_backup():
    if not session.get("admin"):
        return jsonify({"error": "관리자 인증이 필요합니다."}), 401

    c = get_db()
    try:
        rows = c.execute("SELECT * FROM bookings ORDER BY booking_date, team_no").fetchall()
        
        backup_data = []
        for r in rows:
            backup_data.append({
                "booking_date": r["booking_date"],
                "team_no": r["team_no"],
                "name": r["name"],
                "student_id": r["student_id"],
                "members": r["members"],
                "created_at": r["created_at"] if "created_at" in r else datetime.now().isoformat()
            })
            
        return jsonify({
            "success": True,
            "backup_date": datetime.now().isoformat(timespec="seconds"),
            "total_count": len(backup_data),
            "bookings": backup_data
        })
    except Exception as e:
        return jsonify({"error": f"백업 생성 중 오류가 발생했습니다: {str(e)}"}), 500
    finally:
        c.close()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT","5000")),
        debug=False
    )
