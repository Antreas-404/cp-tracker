import os
import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'super_secret_key_change_this_in_production')

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True

# الاتصال بـ Vercel Postgres
def get_db_connection():
    db_url = os.environ.get('POSTGRES_URL')
    if not db_url:
        raise Exception("POSTGRES_URL is missing! Make sure Postgres storage is attached to your Vercel project.")
    return psycopg2.connect(db_url)

# إنشاء جدول المستخدمين تلقائياً إذا لم يكن موجوداً
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                password VARCHAR(255) NOT NULL,
                display_name VARCHAR(100) NOT NULL,
                cf_handle VARCHAR(50) DEFAULT '',
                ac_handle VARCHAR(50) DEFAULT '',
                lc_handle VARCHAR(50) DEFAULT '',
                cses_id VARCHAR(50) DEFAULT ''
            );
        ''')
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database Initialization Error: {e}")

init_db()

def get_codeforces_stats(handle):
    if not handle: return []
    url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=10000"
    try:
        res = requests.get(url, timeout=15).json()
        if res.get('status') != 'OK': return []
        
        first_solved = {}
        for sub in reversed(res['result']):
            if sub.get('verdict') == 'OK':
                prob = sub['problem']
                c_id = prob.get('contestId') or prob.get('problemsetName', 'gym')
                p_idx = prob.get('index', '')
                p_name = prob.get('name', '')
                p_id = f"{c_id}_{p_idx}_{p_name}"
                
                if p_id not in first_solved:
                    first_solved[p_id] = datetime.fromtimestamp(sub['creationTimeSeconds'], tz=timezone.utc)
                    
        return list(first_solved.values())
    except:
        return []

def get_atcoder_stats(handle):
    if not handle: return []
    url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions?user={handle}&from_second=0"
    try:
        res = requests.get(url, timeout=10).json()
        first_solved = {}
        for sub in res:
            if sub.get('result') == 'AC':
                p_id = sub.get('problem_id')
                if p_id not in first_solved:
                    first_solved[p_id] = datetime.fromtimestamp(sub['epoch_second'], tz=timezone.utc)
        return list(first_solved.values())
    except:
        return []

def calculate_streak_and_stats(timestamps):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    day_cnt = sum(1 for ts in timestamps if ts >= today_start)
    month_cnt = sum(1 for ts in timestamps if ts >= month_start)
    year_cnt = sum(1 for ts in timestamps if ts >= year_start)

    solved_dates = {ts.date() for ts in timestamps}
    current_date = now.date()
    streak = 0

    if current_date not in solved_dates:
        current_date -= timedelta(days=1)

    while current_date in solved_dates:
        streak += 1
        current_date -= timedelta(days=1)

    return day_cnt, month_cnt, year_cnt, streak

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    display_name = data.get('display_name', '').strip()

    if not username or not password or not display_name:
        return jsonify({'error': 'All fields are required.'}), 400

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute('SELECT username FROM users WHERE username = %s', (username,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({'error': 'Username is already taken.'}), 400

    cur.execute(
        'INSERT INTO users (username, password, display_name) VALUES (%s, %s, %s)',
        (username, password, display_name)
    )
    conn.commit()
    cur.close()
    conn.close()

    session['user'] = username
    return jsonify({'message': 'Account created and logged in successfully!'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({'error': 'Invalid username or password.'}), 400

    session['user'] = username
    return jsonify({'message': 'Logged in successfully!'})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({'message': 'Logged out successfully.'})

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    username = session.get('user')
    if not username:
        return jsonify({'logged_in': False})
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users WHERE username = %s', (username,))
    u = cur.fetchone()
    cur.close()
    conn.close()

    if not u:
        return jsonify({'logged_in': False})

    return jsonify({
        'logged_in': True,
        'username': u['username'],
        'display_name': u['display_name'],
        'cf_handle': u['cf_handle'],
        'ac_handle': u['ac_handle'],
        'lc_handle': u['lc_handle'],
        'cses_id': u['cses_id']
    })

@app.route('/api/profile', methods=['PUT'])
def update_profile():
    username = session.get('user')
    if not username:
        return jsonify({'error': 'Unauthorized. Please login.'}), 401

    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET display_name = %s, cf_handle = %s, ac_handle = %s, lc_handle = %s, cses_id = %s
        WHERE username = %s
    ''', (
        data.get('display_name', '').strip(),
        data.get('cf_handle', '').strip(),
        data.get('ac_handle', '').strip(),
        data.get('lc_handle', '').strip(),
        data.get('cses_id', '').strip(),
        username
    ))
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({'message': 'Profile updated successfully!'})

@app.route('/api/scoreboard', methods=['GET'])
def get_scoreboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM users')
    users = cur.fetchall()
    cur.close()
    conn.close()

    scoreboard = []

    for user in users:
        cf_ts = get_codeforces_stats(user['cf_handle'])
        ac_ts = get_atcoder_stats(user['ac_handle'])
        all_ts = cf_ts + ac_ts

        day, month, year, streak = calculate_streak_and_stats(all_ts)

        scoreboard.append({
            'username': user['username'],
            'display_name': user['display_name'],
            'today': day,
            'month': month,
            'year': year,
            'streak': streak,
            'details': {
                'cf': len(cf_ts),
                'ac': len(ac_ts)
            }
        })

    scoreboard.sort(key=lambda x: (x['today'], x['streak'], x['year']), reverse=True)
    return jsonify(scoreboard)

if __name__ == '__main__':
    app.run(debug=True, port=5000)