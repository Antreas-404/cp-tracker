import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_this_in_production'

# إعدادات الـ Session لضمان ثبات التشفير على Vercel
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True
users_db = {}

def get_codeforces_stats(handle):
    if not handle: return []
    url = f"https://codeforces.com/api/user.status?handle={handle}"
    try:
        res = requests.get(url, timeout=10).json()
        if res.get('status') != 'OK': return []
        solved = set()
        timestamps = []
        for sub in res['result']:
            if sub.get('verdict') == 'OK':
                prob = sub['problem']
                p_id = f"{prob.get('contestId', '')}{prob.get('index', '')}"
                if p_id not in solved:
                    solved.add(p_id)
                    timestamps.append(datetime.fromtimestamp(sub['creationTimeSeconds']))
        return timestamps
    except:
        return []

def get_atcoder_stats(handle):
    if not handle: return []
    url = f"https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions?user={handle}&from_second=0"
    try:
        res = requests.get(url, timeout=10).json()
        solved = set()
        timestamps = []
        for sub in res:
            if sub.get('result') == 'AC':
                p_id = sub.get('problem_id')
                if p_id not in solved:
                    solved.add(p_id)
                    timestamps.append(datetime.fromtimestamp(sub['epoch_second']))
        return timestamps
    except:
        return []

def get_cses_count(cses_id):
    if not cses_id: return 0
    url = f"https://cses.fi/user/{cses_id}"
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        for p in soup.find_all('p'):
            if 'Tasks solved' in p.text:
                return int(p.text.split(':')[1].strip().split('/')[0])
        return 0
    except:
        return 0

def get_leetcode_count(username):
    if not username: return 0
    url = "https://leetcode.com/graphql"
    query = """
    query userProfileUserQuestionProgressV2($userSlug: String!) {
      userProfileUserQuestionProgressV2(userSlug: $userSlug) {
        numAcceptedQuestions { count }
      }
    }
    """
    try:
        res = requests.post(url, json={'query': query, 'variables': {'userSlug': username}}, timeout=10).json()
        counts = res['data']['userProfileUserQuestionProgressV2']['numAcceptedQuestions']
        return sum(item['count'] for item in counts)
    except:
        return 0

def process_timestamps(timestamps):
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    day_cnt = sum(1 for ts in timestamps if ts >= today_start)
    month_cnt = sum(1 for ts in timestamps if ts >= month_start)
    year_cnt = sum(1 for ts in timestamps if ts >= year_start)
    return day_cnt, month_cnt, year_cnt, len(timestamps)

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
        cf_ts = get_codeforces_stats(user['cf_handle'])
        ac_ts = get_atcoder_stats(user['ac_handle'])

        cf_day, cf_month, cf_year, cf_total = process_timestamps(cf_ts)
        ac_day, ac_month, ac_year, ac_total = process_timestamps(ac_ts)

        lc_total = get_leetcode_count(user['lc_handle'])
        cses_total = get_cses_count(user['cses_id'])

        scoreboard.append({
            'username': user['username'],
            'display_name': user['display_name'],
            'day': cf_day + ac_day,
            'month': cf_month + ac_month,
            'year': cf_year + ac_year,
            'total': cf_total + ac_total + lc_total + cses_total,
            'details': {
                'cf': cf_total, 'ac': ac_total, 'lc': lc_total, 'cses': cses_total
            }
        })

    scoreboard.sort(key=lambda x: x['total'], reverse=True)
    return jsonify(scoreboard)

if __name__ == '__main__':
    app.run(debug=True, port=5000)