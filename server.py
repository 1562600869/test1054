#!/usr/bin/env python3
import http.server
import socketserver
import sqlite3
import json
import os
import urllib.parse
from datetime import datetime

DB_PATH = 'fitness.db'

VALID_SPORT_TYPES = {'有氧', '力量', '瑜伽', 'HIIT', '拉伸'}
VALID_DIFFICULTIES = {'入门', '进阶', '高强度'}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sport_type TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            course_datetime TEXT NOT NULL,
            max_students INTEGER NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            contact TEXT NOT NULL,
            UNIQUE(nickname, contact)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            registered_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (student_id) REFERENCES students(id),
            UNIQUE(course_id, student_id)
        )
    ''')
    
    cursor.execute('DROP TABLE IF EXISTS checkins')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            student_nickname TEXT NOT NULL,
            checked_in_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            UNIQUE(course_id, student_nickname)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (student_id) REFERENCES students(id),
            UNIQUE(course_id, student_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def dict_factory(row):
    return dict(zip(row.keys(), row))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory='.', **kwargs)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _send_html(self, content, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))

    def _get_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))

    def do_OPTIONS(self):
        self._send_json({})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == '/' or parsed.path == '/index.html':
            self._send_html(INDEX_HTML)
            return
        
        if parsed.path == '/api/courses':
            conn = get_db()
            courses = conn.execute('SELECT * FROM courses ORDER BY course_datetime DESC').fetchall()
            result = []
            for c in courses:
                cd = dict_factory(c)
                reg_count = conn.execute('SELECT COUNT(*) as cnt FROM registrations WHERE course_id = ?', (c['id'],)).fetchone()['cnt']
                cd['registered_count'] = reg_count
                checkin_count = conn.execute('SELECT COUNT(*) as cnt FROM checkins WHERE course_id = ?', (c['id'],)).fetchone()['cnt']
                cd['checkin_count'] = checkin_count
                avg_rating = conn.execute('SELECT AVG(rating) as avg FROM ratings WHERE course_id = ?', (c['id'],)).fetchone()['avg']
                cd['avg_rating'] = round(avg_rating, 1) if avg_rating else None
                result.append(cd)
            conn.close()
            self._send_json(result)
            return
        
        if parsed.path.startswith('/api/courses/'):
            course_id = int(parsed.path.split('/')[-1])
            conn = get_db()
            course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
            if not course:
                conn.close()
                self._send_json({'error': '课程不存在'}, 404)
                return
            cd = dict_factory(course)
            reg_count = conn.execute('SELECT COUNT(*) as cnt FROM registrations WHERE course_id = ?', (course_id,)).fetchone()['cnt']
            cd['registered_count'] = reg_count
            conn.close()
            self._send_json(cd)
            return
        
        if parsed.path == '/api/students':
            conn = get_db()
            students = conn.execute('SELECT * FROM students ORDER BY id DESC').fetchall()
            conn.close()
            self._send_json([dict_factory(s) for s in students])
            return
        
        if parsed.path == '/api/registrations':
            conn = get_db()
            rows = conn.execute('''
                SELECT r.id, r.course_id, r.student_id, r.registered_at,
                       c.name as course_name, s.nickname, s.contact
                FROM registrations r
                JOIN courses c ON r.course_id = c.id
                JOIN students s ON r.student_id = s.id
                ORDER BY r.registered_at DESC
            ''').fetchall()
            conn.close()
            self._send_json([dict_factory(r) for r in rows])
            return
        
        if parsed.path.startswith('/api/courses/') and '/registrations' in parsed.path:
            parts = parsed.path.split('/')
            course_id = int(parts[3])
            conn = get_db()
            rows = conn.execute('''
                SELECT r.id, r.student_id, r.registered_at,
                       s.nickname, s.contact,
                       CASE WHEN ch.id IS NOT NULL THEN 1 ELSE 0 END as checked_in,
                       ra.rating, ra.comment
                FROM registrations r
                JOIN students s ON r.student_id = s.id
                LEFT JOIN checkins ch ON r.course_id = ch.course_id AND s.nickname = ch.student_nickname
                LEFT JOIN ratings ra ON r.course_id = ra.course_id AND r.student_id = ra.student_id
                WHERE r.course_id = ?
                ORDER BY r.registered_at
            ''', (course_id,)).fetchall()
            conn.close()
            self._send_json([dict_factory(r) for r in rows])
            return
        
        if parsed.path == '/api/stats/monthly-courses':
            now = datetime.now()
            year = now.year
            month = now.month
            conn = get_db()
            rows = conn.execute('''
                SELECT sport_type, COUNT(*) as count
                FROM courses
                WHERE strftime('%Y', course_datetime) = ? AND strftime('%m', course_datetime) = ?
                GROUP BY sport_type
            ''', (str(year), f'{month:02d}')).fetchall()
            conn.close()
            self._send_json([dict_factory(r) for r in rows])
            return
        
        if parsed.path == '/api/stats/good-rate':
            conn = get_db()
            total = conn.execute('SELECT COUNT(*) as cnt FROM ratings').fetchone()['cnt']
            good = conn.execute('SELECT COUNT(*) as cnt FROM ratings WHERE rating >= 4').fetchone()['cnt']
            rate = round(good / total * 100, 1) if total > 0 else 0
            conn.close()
            self._send_json({'total_ratings': total, 'good_ratings': good, 'good_rate': rate})
            return
        
        if parsed.path.startswith('/api/ratings/course/'):
            course_id = int(parsed.path.split('/')[-1])
            conn = get_db()
            rows = conn.execute('''
                SELECT r.*, s.nickname
                FROM ratings r
                JOIN students s ON r.student_id = s.id
                WHERE r.course_id = ?
                ORDER BY r.created_at DESC
            ''', (course_id,)).fetchall()
            conn.close()
            self._send_json([dict_factory(r) for r in rows])
            return
        
        self._send_json({'error': 'Not Found'}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        body = self._get_body()
        
        if parsed.path == '/api/courses':
            required = ['name', 'sport_type', 'difficulty', 'course_datetime', 'max_students']
            for k in required:
                if k not in body:
                    self._send_json({'error': f'缺少参数: {k}'}, 400)
                    return
            if body['sport_type'] not in VALID_SPORT_TYPES:
                self._send_json({'error': f'运动类型必须是: {", ".join(sorted(VALID_SPORT_TYPES))}'}, 400)
                return
            if body['difficulty'] not in VALID_DIFFICULTIES:
                self._send_json({'error': f'难度必须是: {", ".join(sorted(VALID_DIFFICULTIES))}'}, 400)
                return
            conn = get_db()
            cursor = conn.execute('''
                INSERT INTO courses (name, sport_type, difficulty, course_datetime, max_students)
                VALUES (?, ?, ?, ?, ?)
            ''', (body['name'], body['sport_type'], body['difficulty'], body['course_datetime'], body['max_students']))
            conn.commit()
            course_id = cursor.lastrowid
            course = conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,)).fetchone()
            conn.close()
            self._send_json(dict_factory(course), 201)
            return
        
        if parsed.path == '/api/students':
            required = ['nickname', 'contact']
            for k in required:
                if k not in body:
                    self._send_json({'error': f'缺少参数: {k}'}, 400)
                    return
            conn = get_db()
            try:
                cursor = conn.execute('''
                    INSERT INTO students (nickname, contact)
                    VALUES (?, ?)
                ''', (body['nickname'], body['contact']))
                conn.commit()
                student_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                existing = conn.execute('SELECT * FROM students WHERE nickname = ? AND contact = ?',
                                       (body['nickname'], body['contact'])).fetchone()
                student_id = existing['id']
            student = conn.execute('SELECT * FROM students WHERE id = ?', (student_id,)).fetchone()
            conn.close()
            self._send_json(dict_factory(student), 201)
            return
        
        if parsed.path == '/api/registrations':
            required = ['course_id', 'student_id']
            for k in required:
                if k not in body:
                    self._send_json({'error': f'缺少参数: {k}'}, 400)
                    return
            conn = get_db()
            course = conn.execute('SELECT * FROM courses WHERE id = ?', (body['course_id'],)).fetchone()
            if not course:
                conn.close()
                self._send_json({'error': '课程不存在'}, 404)
                return
            reg_count = conn.execute('SELECT COUNT(*) as cnt FROM registrations WHERE course_id = ?',
                                    (body['course_id'],)).fetchone()['cnt']
            if reg_count >= course['max_students']:
                conn.close()
                self._send_json({'error': '报名人数已达上限'}, 400)
                return
            try:
                now = datetime.now().isoformat()
                cursor = conn.execute('''
                    INSERT INTO registrations (course_id, student_id, registered_at)
                    VALUES (?, ?, ?)
                ''', (body['course_id'], body['student_id'], now))
                conn.commit()
                reg_id = cursor.lastrowid
                reg = conn.execute('''
                    SELECT r.*, c.name as course_name, s.nickname, s.contact
                    FROM registrations r
                    JOIN courses c ON r.course_id = c.id
                    JOIN students s ON r.student_id = s.id
                    WHERE r.id = ?
                ''', (reg_id,)).fetchone()
                conn.close()
                self._send_json(dict_factory(reg), 201)
            except sqlite3.IntegrityError:
                conn.close()
                self._send_json({'error': '该学员已报名此课程'}, 400)
            return
        
        if parsed.path == '/api/checkins':
            required = ['course_id', 'student_nickname']
            for k in required:
                if k not in body:
                    self._send_json({'error': f'缺少参数: {k}'}, 400)
                    return
            conn = get_db()
            registered = conn.execute('''
                SELECT r.* FROM registrations r
                JOIN students s ON r.student_id = s.id
                WHERE r.course_id = ? AND s.nickname = ?
            ''', (body['course_id'], body['student_nickname'])).fetchone()
            if not registered:
                conn.close()
                self._send_json({'error': '该学员未报名此课程'}, 400)
                return
            try:
                now = datetime.now().isoformat()
                conn.execute('''
                    INSERT INTO checkins (course_id, student_nickname, checked_in_at)
                    VALUES (?, ?, ?)
                ''', (body['course_id'], body['student_nickname'], now))
                conn.commit()
                conn.close()
                self._send_json({'success': True, 'checked_in_at': now}, 201)
            except sqlite3.IntegrityError:
                conn.close()
                self._send_json({'error': '该学员已签到'}, 400)
            return
        
        if parsed.path == '/api/ratings':
            required = ['course_id', 'student_id', 'rating']
            for k in required:
                if k not in body:
                    self._send_json({'error': f'缺少参数: {k}'}, 400)
                    return
            rating = body['rating']
            if not isinstance(rating, int) or rating < 1 or rating > 5:
                self._send_json({'error': '评分必须是1到5之间的整数'}, 400)
                return
            conn = get_db()
            student = conn.execute('SELECT nickname FROM students WHERE id = ?', (body['student_id'],)).fetchone()
            if not student:
                conn.close()
                self._send_json({'error': '学员不存在'}, 404)
                return
            checked_in = conn.execute('SELECT * FROM checkins WHERE course_id = ? AND student_nickname = ?',
                                     (body['course_id'], student['nickname'])).fetchone()
            if not checked_in:
                conn.close()
                self._send_json({'error': '该学员未签到，无法评价'}, 400)
                return
            try:
                now = datetime.now().isoformat()
                conn.execute('''
                    INSERT INTO ratings (course_id, student_id, rating, comment, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (body['course_id'], body['student_id'], rating, body.get('comment', ''), now))
                conn.commit()
                conn.close()
                self._send_json({'success': True, 'created_at': now}, 201)
            except sqlite3.IntegrityError:
                conn.close()
                self._send_json({'error': '该学员已评价此课程'}, 400)
            return
        
        self._send_json({'error': 'Not Found'}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path.startswith('/api/courses/'):
            course_id = int(parsed.path.split('/')[-1])
            conn = get_db()
            conn.execute('DELETE FROM ratings WHERE course_id = ?', (course_id,))
            conn.execute('DELETE FROM checkins WHERE course_id = ?', (course_id,))
            conn.execute('DELETE FROM registrations WHERE course_id = ?', (course_id,))
            conn.execute('DELETE FROM courses WHERE id = ?', (course_id,))
            conn.commit()
            conn.close()
            self._send_json({'success': True})
            return
        
        self._send_json({'error': 'Not Found'}, 404)

INDEX_HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>在家健身管理系统</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f7fa; color: #333; padding: 20px; }
.container { max-width: 1200px; margin: 0 auto; }
h1 { text-align: center; color: #2c3e50; margin-bottom: 30px; }
.tabs { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
.tab { padding: 12px 24px; background: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; transition: all 0.3s; }
.tab.active { background: #3498db; color: white; }
.tab:hover:not(.active) { background: #e8f4fc; }
.panel { display: none; background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
.panel.active { display: block; }
.card { background: #fafbfc; border-radius: 8px; padding: 20px; margin-bottom: 20px; border: 1px solid #e1e8ed; }
h2 { color: #2c3e50; margin-bottom: 16px; font-size: 18px; }
h3 { color: #34495e; margin: 16px 0 12px; font-size: 16px; }
.form-row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.form-group { flex: 1; min-width: 180px; }
label { display: block; margin-bottom: 6px; font-size: 13px; color: #555; font-weight: 500; }
input, select, textarea { width: 100%; padding: 10px 12px; border: 1px solid #dcdfe6; border-radius: 6px; font-size: 14px; font-family: inherit; }
input:focus, select:focus, textarea:focus { outline: none; border-color: #3498db; }
button { padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; transition: background 0.3s; }
button:hover { background: #2980b9; }
button.danger { background: #e74c3c; }
button.danger:hover { background: #c0392b; }
button.success { background: #27ae60; }
button.success:hover { background: #219a52; }
button.warning { background: #f39c12; }
button.warning:hover { background: #d68910; }
button:disabled { background: #bdc3c7; cursor: not-allowed; }
table { width: 100%; border-collapse: collapse; margin-top: 16px; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e1e8ed; font-size: 14px; }
th { background: #f8f9fa; font-weight: 600; color: #555; }
tr:hover { background: #f8f9fa; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 500; }
.badge-aerobic { background: #e3f2fd; color: #1565c0; }
.badge-strength { background: #ffebee; color: #c62828; }
.badge-yoga { background: #f3e5f5; color: #6a1b9a; }
.badge-hiit { background: #fff3e0; color: #e65100; }
.badge-stretch { background: #e8f5e9; color: #2e7d32; }
.badge-easy { background: #e8f5e9; color: #2e7d32; }
.badge-medium { background: #fff8e1; color: #f57f17; }
.badge-hard { background: #ffebee; color: #c62828; }
.badge-checked { background: #e8f5e9; color: #2e7d32; }
.badge-unchecked { background: #ffebee; color: #c62828; }
.stars { color: #ffc107; font-size: 16px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 20px; }
.stat-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 24px; border-radius: 12px; text-align: center; }
.stat-card h3 { color: white; font-size: 32px; margin: 0 0 8px; }
.stat-card p { opacity: 0.9; font-size: 14px; }
.stat-card.aerobic { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
.stat-card.strength { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
.stat-card.yoga { background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: #333; }
.stat-card.yoga h3 { color: #333; }
.stat-card.hiit { background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%); }
.stat-card.stretch { background: linear-gradient(135deg, #d299c2 0%, #fef9d7 100%); color: #333; }
.stat-card.stretch h3 { color: #333; }
.stat-card.rate { background: linear-gradient(135deg, #96fbc4 0%, #f9f586 100%); color: #333; }
.stat-card.rate h3 { color: #333; }
.empty { text-align: center; padding: 40px; color: #999; }
.action-btns { display: flex; gap: 8px; }
.action-btns button { padding: 6px 12px; font-size: 12px; }
.course-info { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
.course-info h3 { margin: 0; }
.progress-bar { height: 8px; background: #e1e8ed; border-radius: 4px; overflow: hidden; margin-top: 8px; }
.progress-fill { height: 100%; background: #3498db; transition: width 0.3s; }
.progress-fill.full { background: #e74c3c; }
.comment { color: #666; font-size: 13px; font-style: italic; }
.modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; z-index: 1000; }
.modal.active { display: flex; }
.modal-content { background: white; padding: 24px; border-radius: 12px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.close-btn { background: none; color: #999; font-size: 24px; padding: 0; }
.close-btn:hover { background: none; color: #333; }
.sport-badge { margin-right: 8px; }
</style>
</head>
<body>
<div class="container">
    <h1>🏋️ 在家健身管理系统</h1>
    
    <div class="tabs">
        <button class="tab active" data-tab="courses">课程管理</button>
        <button class="tab" data-tab="students">学员管理</button>
        <button class="tab" data-tab="register">报名签到</button>
        <button class="tab" data-tab="rate">课后评分</button>
        <button class="tab" data-tab="stats">数据统计</button>
    </div>

    <div class="panel active" id="panel-courses">
        <div class="card">
            <h2>➕ 添加课程</h2>
            <div class="form-row">
                <div class="form-group">
                    <label>课程名称</label>
                    <input type="text" id="course-name" placeholder="如：燃脂有氧操">
                </div>
                <div class="form-group">
                    <label>运动类型</label>
                    <select id="course-type">
                        <option value="有氧">有氧</option>
                        <option value="力量">力量</option>
                        <option value="瑜伽">瑜伽</option>
                        <option value="HIIT">HIIT</option>
                        <option value="拉伸">拉伸</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>难度</label>
                    <select id="course-difficulty">
                        <option value="入门">入门</option>
                        <option value="进阶">进阶</option>
                        <option value="高强度">高强度</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>日期时间</label>
                    <input type="datetime-local" id="course-datetime">
                </div>
                <div class="form-group">
                    <label>最大人数</label>
                    <input type="number" id="course-max" min="1" value="20">
                </div>
                <div class="form-group" style="display: flex; align-items: flex-end;">
                    <button onclick="addCourse()">添加课程</button>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📋 课程列表</h2>
            <div id="courses-list"></div>
        </div>
    </div>

    <div class="panel" id="panel-students">
        <div class="card">
            <h2>➕ 添加学员</h2>
            <div class="form-row">
                <div class="form-group">
                    <label>昵称</label>
                    <input type="text" id="student-nickname" placeholder="学员昵称">
                </div>
                <div class="form-group">
                    <label>联系方式</label>
                    <input type="text" id="student-contact" placeholder="手机号或微信号">
                </div>
                <div class="form-group" style="display: flex; align-items: flex-end;">
                    <button onclick="addStudent()">添加学员</button>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>👥 学员列表</h2>
            <div id="students-list"></div>
        </div>
    </div>

    <div class="panel" id="panel-register">
        <div class="card">
            <h2>📝 选择课程</h2>
            <select id="register-course-select" onchange="loadCourseRegistrations()">
                <option value="">-- 请选择课程 --</option>
            </select>
        </div>

        <div class="card" id="registration-card" style="display: none;">
            <div class="course-info">
                <h3 id="reg-course-name"></h3>
                <div>
                    <span id="reg-badge" class="badge"></span>
                </div>
            </div>
            <p id="reg-course-info" style="color: #666; margin: 8px 0 16px;"></p>
            <div class="progress-bar"><div class="progress-fill" id="reg-progress"></div></div>
            <p id="reg-count" style="text-align: right; font-size: 13px; color: #666; margin-top: 4px;"></p>

            <h3>学员报名</h3>
            <div class="form-row">
                <div class="form-group">
                    <label>选择学员</label>
                    <select id="register-student-select">
                        <option value="">-- 请选择学员 --</option>
                    </select>
                </div>
                <div class="form-group" style="display: flex; align-items: flex-end;">
                    <button onclick="registerStudent()" id="register-btn">报名</button>
                </div>
            </div>

            <h3>签到管理</h3>
            <div id="registrations-table"></div>
        </div>
    </div>

    <div class="panel" id="panel-rate">
        <div class="card">
            <h2>⭐ 选择课程进行评价</h2>
            <select id="rate-course-select" onchange="loadRatings()">
                <option value="">-- 请选择课程 --</option>
            </select>
        </div>

        <div class="card" id="rating-card" style="display: none;">
            <h3 id="rate-course-name"></h3>
            <p id="rate-course-info" style="color: #666; margin: 8px 0 16px;"></p>

            <h3>提交评价</h3>
            <div class="form-row">
                <div class="form-group">
                    <label>选择学员</label>
                    <select id="rate-student-select">
                        <option value="">-- 请选择已签到学员 --</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>评分</label>
                    <select id="rate-rating">
                        <option value="5">⭐⭐⭐⭐⭐ 5星</option>
                        <option value="4">⭐⭐⭐⭐ 4星</option>
                        <option value="3">⭐⭐⭐ 3星</option>
                        <option value="2">⭐⭐ 2星</option>
                        <option value="1">⭐ 1星</option>
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>评语</label>
                    <textarea id="rate-comment" rows="3" placeholder="可选：写下你的上课感受..."></textarea>
                </div>
            </div>
            <button onclick="submitRating()">提交评价</button>

            <h3>评价列表</h3>
            <div id="ratings-list"></div>
        </div>
    </div>

    <div class="panel" id="panel-stats">
        <div class="card">
            <h2>📊 本月各运动类型开课次数</h2>
            <div class="stats-grid" id="monthly-stats"></div>
        </div>

        <div class="card">
            <h2>📈 好评率统计</h2>
            <div class="stats-grid" id="good-rate-stats"></div>
        </div>
    </div>
</div>

<div class="modal" id="detail-modal">
    <div class="modal-content">
        <div class="modal-header">
            <h2 id="modal-title">课程详情</h2>
            <button class="close-btn" onclick="closeModal()">&times;</button>
        </div>
        <div id="modal-body"></div>
    </div>
</div>

<script>
const API_BASE = '/api';

function getSportBadge(type) {
    const map = {
        '有氧': 'badge-aerobic',
        '力量': 'badge-strength',
        '瑜伽': 'badge-yoga',
        'HIIT': 'badge-hiit',
        '拉伸': 'badge-stretch'
    };
    return `<span class="badge sport-badge ${map[type] || ''}">${type}</span>`;
}

function getDifficultyBadge(level) {
    const map = {
        '入门': 'badge-easy',
        '进阶': 'badge-medium',
        '高强度': 'badge-hard'
    };
    return `<span class="badge ${map[level] || ''}">${level}</span>`;
}

function getStars(rating) {
    return '⭐'.repeat(rating) + '☆'.repeat(5 - rating);
}

function formatDateTime(dt) {
    const d = new Date(dt);
    return d.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit'
    });
}

async function apiCall(url, method = 'GET', body = null) {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) options.body = JSON.stringify(body);
    const res = await fetch(API_BASE + url, options);
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || '操作失败');
        throw new Error(data.error);
    }
    return data;
}

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
        if (tab.dataset.tab === 'courses') loadCourses();
        if (tab.dataset.tab === 'students') loadStudents();
        if (tab.dataset.tab === 'register') loadRegisterCourses();
        if (tab.dataset.tab === 'rate') loadRateCourses();
        if (tab.dataset.tab === 'stats') loadStats();
    });
});

async function loadCourses() {
    const courses = await apiCall('/courses');
    const container = document.getElementById('courses-list');
    if (courses.length === 0) {
        container.innerHTML = '<div class="empty">暂无课程</div>';
        return;
    }
    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>课程名称</th>
                    <th>类型</th>
                    <th>难度</th>
                    <th>时间</th>
                    <th>报名/最大</th>
                    <th>签到</th>
                    <th>平均分</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                ${courses.map(c => {
                    const ratio = c.registered_count / c.max_students;
                    const full = ratio >= 1;
                    return `
                    <tr>
                        <td>${c.name}</td>
                        <td>${getSportBadge(c.sport_type)}</td>
                        <td>${getDifficultyBadge(c.difficulty)}</td>
                        <td>${formatDateTime(c.course_datetime)}</td>
                        <td>
                            ${c.registered_count}/${c.max_students}
                            ${full ? ' <span class="badge badge-unchecked">已满</span>' : ''}
                        </td>
                        <td>${c.checkin_count}人</td>
                        <td>${c.avg_rating ? getStars(Math.round(c.avg_rating)) + ' ' + c.avg_rating : '-'}</td>
                        <td class="action-btns">
                            <button onclick="viewCourseDetail(${c.id})">详情</button>
                            <button class="danger" onclick="deleteCourse(${c.id})">删除</button>
                        </td>
                    </tr>
                `}).join('')}
            </tbody>
        </table>
    `;
}

async function addCourse() {
    const name = document.getElementById('course-name').value.trim();
    const sport_type = document.getElementById('course-type').value;
    const difficulty = document.getElementById('course-difficulty').value;
    const course_datetime = document.getElementById('course-datetime').value;
    const max_students = parseInt(document.getElementById('course-max').value);

    if (!name || !course_datetime || !max_students) {
        alert('请填写完整信息');
        return;
    }

    await apiCall('/courses', 'POST', { name, sport_type, difficulty, course_datetime, max_students });
    alert('课程添加成功');
    document.getElementById('course-name').value = '';
    document.getElementById('course-datetime').value = '';
    loadCourses();
}

async function deleteCourse(id) {
    if (!confirm('确定要删除这个课程吗？相关的报名、签到、评价数据也会被删除。')) return;
    await apiCall('/courses/' + id, 'DELETE');
    loadCourses();
}

async function viewCourseDetail(courseId) {
    const course = await apiCall('/courses/' + courseId);
    const registrations = await apiCall('/courses/' + courseId + '/registrations');
    
    document.getElementById('modal-title').textContent = course.name + ' - 详情';
    document.getElementById('modal-body').innerHTML = `
        <p><strong>类型：</strong>${getSportBadge(course.sport_type)} ${getDifficultyBadge(course.difficulty)}</p>
        <p><strong>时间：</strong>${formatDateTime(course.course_datetime)}</p>
        <p><strong>人数：</strong>${course.registered_count}/${course.max_students} 人</p>
        <h3 style="margin-top: 20px;">报名学员</h3>
        ${registrations.length === 0 ? '<div class="empty">暂无学员报名</div>' : `
            <table>
                <thead>
                    <tr>
                        <th>学员</th>
                        <th>联系方式</th>
                        <th>签到状态</th>
                        <th>评分</th>
                        <th>评语</th>
                    </tr>
                </thead>
                <tbody>
                    ${registrations.map(r => `
                        <tr>
                            <td>${r.nickname}</td>
                            <td>${r.contact}</td>
                            <td>${r.checked_in ? '<span class="badge badge-checked">已签到</span>' : '<span class="badge badge-unchecked">未签到</span>'}</td>
                            <td>${r.rating ? getStars(r.rating) : '-'}</td>
                            <td class="comment">${r.comment || '-'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `}
    `;
    document.getElementById('detail-modal').classList.add('active');
}

function closeModal() {
    document.getElementById('detail-modal').classList.remove('active');
}

async function loadStudents() {
    const students = await apiCall('/students');
    const container = document.getElementById('students-list');
    if (students.length === 0) {
        container.innerHTML = '<div class="empty">暂无学员</div>';
        return;
    }
    container.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>昵称</th>
                    <th>联系方式</th>
                </tr>
            </thead>
            <tbody>
                ${students.map(s => `
                    <tr>
                        <td>${s.id}</td>
                        <td>${s.nickname}</td>
                        <td>${s.contact}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function addStudent() {
    const nickname = document.getElementById('student-nickname').value.trim();
    const contact = document.getElementById('student-contact').value.trim();

    if (!nickname || !contact) {
        alert('请填写完整信息');
        return;
    }

    await apiCall('/students', 'POST', { nickname, contact });
    alert('学员添加成功');
    document.getElementById('student-nickname').value = '';
    document.getElementById('student-contact').value = '';
    loadStudents();
}

async function loadRegisterCourses() {
    const courses = await apiCall('/courses');
    const select = document.getElementById('register-course-select');
    select.innerHTML = '<option value="">-- 请选择课程 --</option>' + 
        courses.map(c => `<option value="${c.id}">${c.name} - ${formatDateTime(c.course_datetime)}</option>`).join('');
}

async function loadCourseRegistrations() {
    const courseId = document.getElementById('register-course-select').value;
    if (!courseId) {
        document.getElementById('registration-card').style.display = 'none';
        return;
    }

    const [course, registrations, students] = await Promise.all([
        apiCall('/courses/' + courseId),
        apiCall('/courses/' + courseId + '/registrations'),
        apiCall('/students')
    ]);

    document.getElementById('registration-card').style.display = 'block';
    document.getElementById('reg-course-name').textContent = course.name;
    document.getElementById('reg-badge').outerHTML = getSportBadge(course.sport_type) + getDifficultyBadge(course.difficulty);
    document.getElementById('reg-course-info').textContent = '时间：' + formatDateTime(course.course_datetime);
    
    const ratio = course.registered_count / course.max_students;
    const progress = document.getElementById('reg-progress');
    progress.style.width = (ratio * 100) + '%';
    progress.classList.toggle('full', ratio >= 1);
    document.getElementById('reg-count').textContent = `已报名 ${course.registered_count} / ${course.max_students} 人`;

    const registeredIds = registrations.map(r => r.student_id);
    const availableStudents = students.filter(s => !registeredIds.includes(s.id));
    const studentSelect = document.getElementById('register-student-select');
    studentSelect.innerHTML = '<option value="">-- 请选择学员 --</option>' +
        availableStudents.map(s => `<option value="${s.id}">${s.nickname} (${s.contact})</option>`).join('');
    
    document.getElementById('register-btn').disabled = availableStudents.length === 0 || ratio >= 1;

    const table = document.getElementById('registrations-table');
    if (registrations.length === 0) {
        table.innerHTML = '<div class="empty">暂无学员报名</div>';
        return;
    }

    table.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>学员</th>
                    <th>联系方式</th>
                    <th>报名时间</th>
                    <th>签到状态</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                ${registrations.map(r => `
                    <tr>
                        <td>${r.nickname}</td>
                        <td>${r.contact}</td>
                        <td>${formatDateTime(r.registered_at)}</td>
                        <td>${r.checked_in ? '<span class="badge badge-checked">已签到</span>' : '<span class="badge badge-unchecked">未签到</span>'}</td>
                        <td class="action-btns">
                            ${!r.checked_in ? `<button class="success" onclick="checkIn(${courseId}, '${r.nickname}')">签到</button>` : ''}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function registerStudent() {
    const courseId = document.getElementById('register-course-select').value;
    const studentId = document.getElementById('register-student-select').value;
    if (!studentId) {
        alert('请选择学员');
        return;
    }
    await apiCall('/registrations', 'POST', { course_id: parseInt(courseId), student_id: parseInt(studentId) });
    alert('报名成功');
    loadCourseRegistrations();
    loadRegisterCourses();
}

async function checkIn(courseId, studentNickname) {
    await apiCall('/checkins', 'POST', { course_id: courseId, student_nickname: studentNickname });
    alert('签到成功');
    loadCourseRegistrations();
}

async function loadRateCourses() {
    const courses = await apiCall('/courses');
    const select = document.getElementById('rate-course-select');
    select.innerHTML = '<option value="">-- 请选择课程 --</option>' + 
        courses.map(c => `<option value="${c.id}">${c.name} - ${formatDateTime(c.course_datetime)}</option>`).join('');
}

async function loadRatings() {
    const courseId = document.getElementById('rate-course-select').value;
    if (!courseId) {
        document.getElementById('rating-card').style.display = 'none';
        return;
    }

    const [course, registrations, ratings] = await Promise.all([
        apiCall('/courses/' + courseId),
        apiCall('/courses/' + courseId + '/registrations'),
        apiCall('/ratings/course/' + courseId)
    ]);

    document.getElementById('rating-card').style.display = 'block';
    document.getElementById('rate-course-name').textContent = course.name;
    document.getElementById('rate-course-info').textContent = '时间：' + formatDateTime(course.course_datetime);

    const ratedIds = ratings.map(r => r.student_id);
    const eligibleStudents = registrations.filter(r => r.checked_in && !ratedIds.includes(r.student_id));
    const studentSelect = document.getElementById('rate-student-select');
    studentSelect.innerHTML = '<option value="">-- 请选择已签到学员 --</option>' +
        eligibleStudents.map(s => `<option value="${s.student_id}">${s.nickname} (${s.contact})</option>`).join('');

    const list = document.getElementById('ratings-list');
    if (ratings.length === 0) {
        list.innerHTML = '<div class="empty">暂无评价</div>';
        return;
    }

    list.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>学员</th>
                    <th>评分</th>
                    <th>评语</th>
                    <th>评价时间</th>
                </tr>
            </thead>
            <tbody>
                ${ratings.map(r => `
                    <tr>
                        <td>${r.nickname}</td>
                        <td><span class="stars">${getStars(r.rating)}</span> ${r.rating}星</td>
                        <td class="comment">${r.comment || '-'}</td>
                        <td>${formatDateTime(r.created_at)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function submitRating() {
    const courseId = parseInt(document.getElementById('rate-course-select').value);
    const studentId = parseInt(document.getElementById('rate-student-select').value);
    const rating = parseInt(document.getElementById('rate-rating').value);
    const comment = document.getElementById('rate-comment').value.trim();

    if (!studentId) {
        alert('请选择学员');
        return;
    }

    await apiCall('/ratings', 'POST', { course_id: courseId, student_id: studentId, rating, comment });
    alert('评价提交成功');
    document.getElementById('rate-comment').value = '';
    loadRatings();
}

async function loadStats() {
    const [monthly, goodRate] = await Promise.all([
        apiCall('/stats/monthly-courses'),
        apiCall('/stats/good-rate')
    ]);

    const typeMap = {
        '有氧': 'aerobic',
        '力量': 'strength',
        '瑜伽': 'yoga',
        'HIIT': 'hiit',
        '拉伸': 'stretch'
    };
    const allTypes = ['有氧', '力量', '瑜伽', 'HIIT', '拉伸'];
    const monthlyContainer = document.getElementById('monthly-stats');
    monthlyContainer.innerHTML = allTypes.map(type => {
        const found = monthly.find(m => m.sport_type === type);
        const count = found ? found.count : 0;
        return `
            <div class="stat-card ${typeMap[type]}">
                <h3>${count}</h3>
                <p>${type}课程</p>
            </div>
        `;
    }).join('');

    const rateContainer = document.getElementById('good-rate-stats');
    rateContainer.innerHTML = `
        <div class="stat-card">
            <h3>${goodRate.total_ratings}</h3>
            <p>总评价数</p>
        </div>
        <div class="stat-card rate">
            <h3>${goodRate.good_ratings}</h3>
            <p>好评数(≥4星)</p>
        </div>
        <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <h3>${goodRate.good_rate}%</h3>
            <p>好评率</p>
        </div>
    `;
}

document.addEventListener('DOMContentLoaded', () => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('course-datetime').value = now.toISOString().slice(0, 16);
    loadCourses();
});
</script>
</body>
</html>
'''

if __name__ == '__main__':
    init_db()
    PORT = 2500
    with socketserver.TCPServer(('', PORT), Handler) as httpd:
        print(f'Server running at http://localhost:{PORT}')
        httpd.serve_forever()
