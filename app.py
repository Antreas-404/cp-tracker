import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_this_in_production'

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
users_db = {}

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

    # حساب أعداد اليوم، الشهر، والسنة
    day_cnt = sum(1 for ts in timestamps if ts >= today_start)
    month_cnt = sum(1 for ts in timestamps if ts >= month_start)
    year_cnt = sum(1 for ts in timestamps if ts >= year_start)

    # حساب الـ Streak بالأيام المتتالية
    solved_dates = {ts.date() for ts in timestamps}
    current_date = now.date()
    streak = 0

    # لو محليش النهاردة، بنبدأ نراجع من امبارح لو الـ streak شغال
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

    if username in users_db:
        return jsonify({'error': 'Username is already taken.'}), 400

    users_db[username] = {
        'username': username,
        'password': password,
        'display_name': display_name,
        'cf_handle': '',
        'ac_handle': '',
        'lc_handle': '',
        'cses_id': ''
    }
    session['user'] = username
    return jsonify({'message': 'Account created and logged in successfully!'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()

    user = users_db.get(username)
    if not user or user['password'] != password:
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
    if not username or username not in users_db:
        return jsonify({'logged_in': False})
    
    u = users_db[username]
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
    if not username or username not in users_db:
        return jsonify({'error': 'Unauthorized. Please login.'}), 401

    data = request.json
    users_db[username]['display_name'] = data.get('display_name', users_db[username]['display_name']).strip()
    users_db[username]['cf_handle'] = data.get('cf_handle', '').strip()
    users_db[username]['ac_handle'] = data.get('ac_handle', '').strip()
    users_db[username]['lc_handle'] = data.get('lc_handle', '').strip()
    users_db[username]['cses_id'] = data.get('cses_id', '').strip()

    return jsonify({'message': 'Profile updated successfully!'})

@app.route('/api/scoreboard', methods=['GET'])
def get_scoreboard():
    scoreboard = []

    for username, user in users_db.items():
        # دمج كل الـ Timestamps المتاحة من المنصات الزمانية
        all_ts = get_codeforces_stats(user['cf_handle']) + get_atcoder_stats(user['ac_handle'])

        day, month, year, streak = calculate_streak_and_stats(all_ts)

        scoreboard.append({
            'username': user['username'],
            'display_name': user['display_name'],
            'today': day,
            'month': month,
            'year': year,
            'streak': streak,
            'details': {
                'cf': len(get_codeforces_stats(user['cf_handle'])),
                'ac': len(get_atcoder_stats(user['ac_handle']))
            }
        })

    # الترتيب تنازلياً: الأولوية للأكثر حلاً اليوم، ثم أطول Streak، ثم إجمالي السنة
    scoreboard.sort(key=lambda x: (x['today'], x['streak'], x['year']), reverse=True)
    return jsonify(scoreboard)

if __name__ == '__main__':
    app.run(debug=True, port=5000)