from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pandas as pd
from io import BytesIO
from collections import defaultdict
import os
import time
import base64
import json
import requests as req
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

app = Flask(__name__)

# 資料庫路徑設定（支援本地開發和 PythonAnywhere）
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'guild_war.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

DEFAULT_JOBS = [
    {"name": "鐵衣", "color": "#FFD8A8", "text_color": "#000000"},
    {"name": "血河", "color": "#FFB3B3", "text_color": "#000000"},
    {"name": "碎夢", "color": "#B3E5FC", "text_color": "#000000"},
    {"name": "神相", "color": "#A7C7E7", "text_color": "#000000"},
    {"name": "九靈", "color": "#E1BEE7", "text_color": "#000000"},
    {"name": "玄機", "color": "#FFF59D", "text_color": "#000000"},
    {"name": "素問", "color": "#F8BBD0", "text_color": "#000000"},
    {"name": "龍吟", "color": "#C8E6C9", "text_color": "#000000"},
]

DEFAULT_SKILLS = [
    "流風輕雲(奶絕)", "鈞天浩意(砲)", "法天象地", "蝶舞清夢", "劍魂沖銷",
    "大鬧天宮", "騰龍越淵", "九天雷引", "冰火絕滅", "劍破乾坤",
    "太極圖", "萬劍訣", "奪破寶典", "紅蓮焚夜", "狂發一怒",
    "殘心三絕劍", "繁花一夢", "長歌獻君", "蓋世訣", "天下無狗",
    "春華佑世", "昀光神劍",
]

# 職業資料表
class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    color = db.Column(db.String(10), default='#CCCCCC')
    text_color = db.Column(db.String(10), default='#000000')

# 技能資料表
class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

# 玩家資料表
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(50), nullable=False)
    main_job = db.Column(db.String(20), nullable=False)
    sub_job = db.Column(db.String(20))
    can_fight = db.Column(db.Boolean, default=True)
    group_name = db.Column(db.String(50))
    team_name = db.Column(db.String(50))
    role_note = db.Column(db.String(100))
    skill = db.Column(db.String(500))
    is_guild = db.Column(db.Boolean, default=False)
    is_challenge = db.Column(db.Boolean, default=False)
    challenge_group_name = db.Column(db.String(50))
    challenge_team_name = db.Column(db.String(50))
    challenge_skill = db.Column(db.String(500))
    team_active_job = db.Column(db.String(20))
    challenge_active_job = db.Column(db.String(20))
    challenge_can_fight = db.Column(db.Boolean, default=True)

# 團隊編成小隊名稱設定表
class TeamConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(50), nullable=False)
    slot_index = db.Column(db.Integer, nullable=False)
    display_name = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint('group_name', 'slot_index', name='uq_team_config_group_slot'),)

# 約戰小隊名稱設定表
class ChallengeTeamConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_name = db.Column(db.String(50), nullable=False)
    slot_index = db.Column(db.Integer, nullable=False)
    display_name = db.Column(db.String(50), nullable=False)
    __table_args__ = (db.UniqueConstraint('group_name', 'slot_index', name='uq_challenge_tc_group_slot'),)

with app.app_context():
    db.create_all()
    # 為既有資料庫補上新欄位（SQLite 不支援 ALTER TABLE ADD COLUMN IF NOT EXISTS）
    with db.engine.connect() as conn:
        inspector = db.inspect(db.engine)
        player_cols = [c['name'] for c in inspector.get_columns('player')]
        # 將舊欄位 job 改名為 main_job
        if 'job' in player_cols and 'main_job' not in player_cols:
            conn.execute(db.text('ALTER TABLE player RENAME COLUMN job TO main_job'))
            conn.commit()
            player_cols = [c['name'] for c in inspector.get_columns('player')]
        new_cols = [
            ('sub_job',             'ALTER TABLE player ADD COLUMN sub_job VARCHAR(20)'),
            ('is_guild',            'ALTER TABLE player ADD COLUMN is_guild BOOLEAN DEFAULT 0'),
            ('is_challenge',        'ALTER TABLE player ADD COLUMN is_challenge BOOLEAN DEFAULT 0'),
            ('challenge_group_name','ALTER TABLE player ADD COLUMN challenge_group_name VARCHAR(50)'),
            ('challenge_team_name', 'ALTER TABLE player ADD COLUMN challenge_team_name VARCHAR(50)'),
            ('challenge_skill',     'ALTER TABLE player ADD COLUMN challenge_skill VARCHAR(500)'),
            ('team_active_job',      'ALTER TABLE player ADD COLUMN team_active_job VARCHAR(20)'),
            ('challenge_active_job', 'ALTER TABLE player ADD COLUMN challenge_active_job VARCHAR(20)'),
            ('challenge_can_fight',  'ALTER TABLE player ADD COLUMN challenge_can_fight BOOLEAN DEFAULT 1'),
        ]
        for col, ddl in new_cols:
            if col not in player_cols:
                conn.execute(db.text(ddl))
        conn.commit()

    # 預設職業資料（若資料庫為空）
    if Job.query.count() == 0:
        for jd in DEFAULT_JOBS:
            db.session.add(Job(**jd))
        db.session.commit()

    # 預設技能資料（若資料庫為空）
    if Skill.query.count() == 0:
        for sname in DEFAULT_SKILLS:
            db.session.add(Skill(name=sname))
        db.session.commit()

@app.context_processor
def inject_global():
    jobs = Job.query.order_by(Job.id).all()
    return dict(
        all_jobs=jobs,
        job_styles={j.name: {"bg": j.color, "fg": j.text_color} for j in jobs}
    )

# 首頁：大表格顯示 + 職業統計
@app.route('/')
def index():
    jobs = Job.query.order_by(Job.id).all()

    stats = {}
    for j in jobs:
        total = Player.query.filter_by(main_job=j.name).count()
        leave = Player.query.filter_by(main_job=j.name, can_fight=False).count()
        stats[j.name] = {"total": total, "leave": leave, "can_fight": total - leave}

    grouped = defaultdict(list)
    for p in Player.query.all():
        grouped[p.main_job].append(p)

    max_len = max((len(v) for v in grouped.values()), default=0)

    return render_template('index.html', stats=stats, grouped=grouped, jobs=[j.name for j in jobs], max_len=max_len)

# 新增玩家
@app.route('/add_player', methods=['GET'])
def add_player_page():
    return render_template('add_player.html')

@app.route('/add_player', methods=['POST'])
def add_player():
    name = request.form.get('name')
    main_job = request.form.get('main_job')
    sub_job = request.form.get('sub_job') or None
    leave = request.form.get('leave')
    role_note = request.form.get('role_note')
    is_guild = bool(request.form.get('is_guild'))
    is_challenge = bool(request.form.get('is_challenge'))
    can_fight = False if leave else True

    new_player = Player(player_name=name, main_job=main_job, sub_job=sub_job,
                        can_fight=can_fight, role_note=role_note,
                        is_guild=is_guild, is_challenge=is_challenge)
    db.session.add(new_player)
    db.session.commit()
    return jsonify({"status": "success"})

# 批量新增
@app.route('/batch_add', methods=['GET', 'POST'])
def batch_add():
    if request.method == 'POST':
        players_text = request.form.get('players', '').strip()
        lines = players_text.splitlines()
        valid_jobs = [j.name for j in Job.query.all()]

        added_count = 0
        errors = []

        for idx, line in enumerate(lines, start=1):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                errors.append(f"第 {idx} 行格式錯誤：至少需要 名字,主職業")
                continue

            name = parts[0]
            main_job = parts[1]
            sub_job = parts[2] if len(parts) > 2 and parts[2] in valid_jobs else None
            note_idx = 3 if sub_job else 2
            note = parts[note_idx] if len(parts) > note_idx else None

            if main_job not in valid_jobs:
                errors.append(f"第 {idx} 行主職業錯誤：{main_job}")
                continue

            new_player = Player(player_name=name, main_job=main_job, sub_job=sub_job,
                                can_fight=True, role_note=note)
            db.session.add(new_player)
            added_count += 1

        if added_count > 0:
            db.session.commit()

        if errors:
            return render_template('batch_add_fail.html', errors=errors, count=added_count)
        else:
            return render_template('batch_add_success.html', count=added_count)

    return render_template('batch_add.html')

# 職業分頁（總覽 + 批次更新）
@app.route('/job/<job>', methods=['GET', 'POST'])
def job_page(job):
    players = Player.query.filter_by(main_job=job).all()

    if request.method == 'POST':
        for player in players:
            player.group_name = request.form.get(f"group_name_{player.id}") or None
            player.team_name = request.form.get(f"team_name_{player.id}") or None
            player.role_note = request.form.get(f"role_note_{player.id}") or None
            player.sub_job = request.form.get(f"sub_job_{player.id}") or None
            player.is_guild = bool(request.form.get(f"is_guild_{player.id}"))
            player.is_challenge = bool(request.form.get(f"is_challenge_{player.id}"))
        db.session.commit()
        return redirect(url_for('job_page', job=job))

    return render_template('job.html', job=job, players=players)

# 單一玩家編輯頁面
@app.route('/job_detail/<int:id>', methods=['GET', 'POST'])
def job_detail(id):
    player = Player.query.get_or_404(id)

    if request.method == 'POST':
        player.group_name = request.form.get('group_name')
        player.team_name = request.form.get('team_name')
        player.role_note = request.form.get('role_note')
        player.sub_job = request.form.get('sub_job') or None
        player.is_guild = bool(request.form.get('is_guild'))
        player.is_challenge = bool(request.form.get('is_challenge'))

        db.session.commit()
        return redirect(url_for('job_page', job=player.main_job))

    return render_template('job_detail.html', player=player)

def _build_team_name_configs(config_model):
    configs = config_model.query.all()
    result = {}
    for c in configs:
        if c.group_name not in result:
            result[c.group_name] = {}
        result[c.group_name][c.slot_index] = c.display_name
    return result

# 團隊編成頁面（只顯示幫眾）
@app.route('/team_assign')
def team_assign():
    skills = [s.name for s in Skill.query.order_by(Skill.id).all()]
    players_data = [
        {"id": p.id, "name": p.player_name, "job": p.main_job, "sub_job": p.sub_job or "",
         "can_fight": p.can_fight,
         "group_name": p.group_name or "", "team_name": p.team_name or "", "skill": p.skill or "",
         "active_job": p.team_active_job or p.main_job}
        for p in Player.query.filter_by(is_guild=True).all()
    ]
    return render_template('team_assign.html',
                           players=players_data,
                           skills=skills,
                           team_name_configs=_build_team_name_configs(TeamConfig),
                           save_url='/team_assign_update',
                           page_title='團隊編成',
                           publish_context='team',
                           mention_role_name=os.getenv('GUILD_WAR_TEAM_ROLE_NAME', '小泡泡'))

# 約戰頁面（只顯示約戰成員）
@app.route('/challenge_assign')
def challenge_assign():
    skills = [s.name for s in Skill.query.order_by(Skill.id).all()]
    players_data = [
        {"id": p.id, "name": p.player_name, "job": p.main_job, "sub_job": p.sub_job or "",
         "can_fight": p.challenge_can_fight if p.challenge_can_fight is not None else True,
         "group_name": p.challenge_group_name or "", "team_name": p.challenge_team_name or "", "skill": p.challenge_skill or "",
         "active_job": p.challenge_active_job or p.main_job}
        for p in Player.query.filter_by(is_challenge=True).all()
    ]
    return render_template('team_assign.html',
                           players=players_data,
                           skills=skills,
                           team_name_configs=_build_team_name_configs(ChallengeTeamConfig),
                           save_url='/challenge_assign_update',
                           page_title='約戰',
                           publish_context='challenge',
                           mention_role_name=os.getenv('GUILD_WAR_CHALLENGE_ROLE_NAME', '俱樂部'))

def _save_assign_update(data, player_fields, config_model):
    for item in data.get('assignments', []):
        player = Player.query.get(item['id'])
        if player:
            setattr(player, player_fields['group'],      item.get('group_name')  or None)
            setattr(player, player_fields['team'],       item.get('team_name')   or None)
            setattr(player, player_fields['skill'],      item.get('skill')       or None)
            setattr(player, player_fields['active_job'], item.get('active_job')  or None)
    for cfg in data.get('team_configs', []):
        existing = config_model.query.filter_by(
            group_name=cfg['group_name'], slot_index=cfg['slot_index']
        ).first()
        if existing:
            existing.display_name = cfg['display_name']
        else:
            db.session.add(config_model(
                group_name=cfg['group_name'],
                slot_index=cfg['slot_index'],
                display_name=cfg['display_name']
            ))
    db.session.commit()

# 團隊編成儲存 API
@app.route('/team_assign_update', methods=['POST'])
def team_assign_update():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "無效的資料格式"}), 400
    _save_assign_update(data,
                        {'group': 'group_name', 'team': 'team_name', 'skill': 'skill', 'active_job': 'team_active_job'},
                        TeamConfig)
    return jsonify({"status": "success"})

# 約戰儲存 API
@app.route('/challenge_assign_update', methods=['POST'])
def challenge_assign_update():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "無效的資料格式"}), 400
    _save_assign_update(data,
                        {'group': 'challenge_group_name', 'team': 'challenge_team_name', 'skill': 'challenge_skill', 'active_job': 'challenge_active_job'},
                        ChallengeTeamConfig)
    return jsonify({"status": "success"})

# 匯出 Excel
from urllib.parse import quote

@app.route('/export_all')
def export_all():
    players = Player.query.all()
    data = [{
        "分組": p.group_name,
        "隊伍": p.team_name,
        "名字": p.player_name,
        "主職業": p.main_job,
        "副職業": p.sub_job or "",
        "絕技": (p.skill or "").replace("|", ", "),
        "備註": p.role_note,
        "狀態": "能打" if p.can_fight else "請假"
    } for p in players]

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="大表", index=False)
        for group in df["分組"].dropna().unique():
            if group.strip():
                df[df["分組"] == group].to_excel(writer, sheet_name=group, index=False)
        candidate_df = df[df["隊伍"].isna() | (df["隊伍"] == "")]
        if not candidate_df.empty:
            candidate_df.to_excel(writer, sheet_name="候補", index=False)

    output.seek(0)
    response = make_response(output.read())

    # 中文檔名處理：用 RFC 5987 編碼
    filename = "醉臥泡影間.xlsx"
    response.headers["Content-Disposition"] = f"attachment; filename=guild.xlsx; filename*=UTF-8''{quote(filename)}"
    response.mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return response

# 切換能打 / 請假
@app.route('/toggle/<int:id>', methods=['POST'])
def toggle_status(id):
    player = Player.query.get_or_404(id)
    player.can_fight = not player.can_fight
    db.session.commit()
    return jsonify({"status": "success", "can_fight": player.can_fight})

# 刪除玩家
@app.route('/delete_page')
def delete_page():
    jobs = [j.name for j in Job.query.order_by(Job.id).all()]
    grouped = defaultdict(list)
    for p in Player.query.all():
        grouped[p.main_job].append(p)
    max_len = max((len(v) for v in grouped.values()), default=0)
    return render_template('delete.html', grouped=grouped, jobs=jobs, max_len=max_len)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_player(id):
    player = Player.query.get_or_404(id)
    db.session.delete(player)
    db.session.commit()
    return jsonify({"status": "success"})

# ─── 職業管理 ─────────────────────────────────────────────────
@app.route('/manage_jobs')
def manage_jobs():
    return render_template('manage_jobs.html')

@app.route('/api/jobs', methods=['POST'])
def api_add_job():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = data.get('color', '#CCCCCC')
    text_color = data.get('text_color', '#000000')
    if not name:
        return jsonify({"status": "error", "message": "職業名稱不能為空"}), 400
    if Job.query.filter_by(name=name).first():
        return jsonify({"status": "error", "message": "職業名稱已存在"}), 400
    job = Job(name=name, color=color, text_color=text_color)
    db.session.add(job)
    db.session.commit()
    return jsonify({"status": "success", "id": job.id, "name": job.name,
                    "color": job.color, "text_color": job.text_color})

@app.route('/api/jobs/<int:id>', methods=['POST'])
def api_edit_job(id):
    job = Job.query.get_or_404(id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = data.get('color', job.color)
    text_color = data.get('text_color', job.text_color)
    if not name:
        return jsonify({"status": "error", "message": "職業名稱不能為空"}), 400
    existing = Job.query.filter_by(name=name).first()
    if existing and existing.id != id:
        return jsonify({"status": "error", "message": "職業名稱已存在"}), 400
    job.name = name
    job.color = color
    job.text_color = text_color
    db.session.commit()
    return jsonify({"status": "success", "id": job.id, "name": job.name,
                    "color": job.color, "text_color": job.text_color})

@app.route('/api/jobs/<int:id>/delete', methods=['POST'])
def api_delete_job(id):
    job = Job.query.get_or_404(id)
    count = Player.query.filter_by(main_job=job.name).count()
    if count > 0:
        return jsonify({"status": "error", "message": f"有 {count} 名玩家使用此職業，無法刪除"}), 400
    db.session.delete(job)
    db.session.commit()
    return jsonify({"status": "success"})

# ─── 技能管理 ─────────────────────────────────────────────────
@app.route('/manage_skills')
def manage_skills():
    skills = Skill.query.order_by(Skill.id).all()
    return render_template('manage_skills.html', all_skills=skills)

@app.route('/api/skills', methods=['POST'])
def api_add_skill():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"status": "error", "message": "技能名稱不能為空"}), 400
    if Skill.query.filter_by(name=name).first():
        return jsonify({"status": "error", "message": "技能名稱已存在"}), 400
    skill = Skill(name=name)
    db.session.add(skill)
    db.session.commit()
    return jsonify({"status": "success", "id": skill.id, "name": skill.name})

@app.route('/api/skills/<int:id>', methods=['POST'])
def api_edit_skill(id):
    skill = Skill.query.get_or_404(id)
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"status": "error", "message": "技能名稱不能為空"}), 400
    existing = Skill.query.filter_by(name=name).first()
    if existing and existing.id != id:
        return jsonify({"status": "error", "message": "技能名稱已存在"}), 400
    skill.name = name
    db.session.commit()
    return jsonify({"status": "success", "id": skill.id, "name": skill.name})

@app.route('/api/skills/<int:id>/delete', methods=['POST'])
def api_delete_skill(id):
    skill = Skill.query.get_or_404(id)
    db.session.delete(skill)
    db.session.commit()
    return jsonify({"status": "success"})

# ─── 發佈編成圖到 Discord ─────────────────────────────────────

@app.route('/api/publish', methods=['POST'])
def publish_to_discord():
    data = request.get_json()
    context     = (data.get('context') or '').strip()
    content     = (data.get('content') or '').strip()
    mention_all = bool(data.get('mention_all', False))
    image_b64   = data.get('image', '')

    if context == 'team':
        webhook_url = os.getenv('GUILD_WAR_TEAM_WEBHOOK', '')
        role_id     = os.getenv('GUILD_WAR_TEAM_ROLE_ID', '')
    elif context == 'challenge':
        webhook_url = os.getenv('GUILD_WAR_CHALLENGE_WEBHOOK', '')
        role_id     = os.getenv('GUILD_WAR_CHALLENGE_ROLE_ID', '')
    else:
        return jsonify({"status": "error", "message": "無效的 context"}), 400

    if not webhook_url or webhook_url.startswith('https://discord.com/api/webhooks/你的'):
        return jsonify({"status": "error", "message": "Webhook URL 尚未設定，請編輯 .env 檔案"}), 500

    # 解碼 base64 圖片（去掉 data:image/png;base64, 前綴）
    if ',' in image_b64:
        image_b64 = image_b64.split(',', 1)[1]
    img_bytes = base64.b64decode(image_b64)

    role_mention = f"<@&{role_id}>\n" if (mention_all and role_id) else ""
    message = role_mention + content

    try:
        resp = req.post(
            webhook_url,
            data={"payload_json": json.dumps({"content": message})},
            files={"files[0]": ("編成圖.png", BytesIO(img_bytes), "image/png")},
            timeout=15,
        )
    except req.exceptions.Timeout:
        return jsonify({"status": "error", "message": "連線 Discord 逾時（15s），請稍後再試"}), 500
    except req.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"連線失敗：{e}"}), 500

    if resp.status_code in (200, 204):
        return jsonify({"status": "success"})
    if resp.status_code == 429:
        try:
            retry_after = resp.json().get("retry_after", 1)
        except Exception:
            retry_after = resp.headers.get("Retry-After", "幾秒")
        return jsonify({"status": "error", "message": f"Discord 限流，請等待 {retry_after} 秒後再試"}), 429
    return jsonify({"status": "error", "message": f"Discord 回應 {resp.status_code}"}), 500


# ─── Discord Bot API ──────────────────────────────────────────

# 1. 取得職業列表
@app.route('/api/bot/jobs', methods=['GET'])
def bot_get_jobs():
    jobs = Job.query.order_by(Job.id).all()
    return jsonify({"status": "success", "jobs": [j.name for j in jobs]})

# 2. 查詢某職業的所有玩家名字
@app.route('/api/bot/players', methods=['GET'])
def bot_get_players_by_job():
    job_name = request.args.get('job', '').strip()
    if not job_name:
        return jsonify({"status": "error", "message": "請提供 job 參數"}), 400
    if not Job.query.filter_by(name=job_name).first():
        return jsonify({"status": "error", "message": f"職業 '{job_name}' 不存在"}), 404
    players = Player.query.filter_by(main_job=job_name).order_by(Player.player_name).all()
    return jsonify({
        "status": "success",
        "job": job_name,
        "players": [
            {"name": p.player_name, "can_fight": p.can_fight}
            for p in players
        ]
    })

# 3. 更改玩家狀態（能打 / 請假）
# context 參數：'team'（預設）或 'challenge'，分別對應不同欄位
@app.route('/api/bot/set_status', methods=['POST'])
def bot_set_status():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "需要 JSON body"}), 400
    name = (data.get('name') or '').strip()
    status = (data.get('status') or '').strip()
    context = (data.get('context') or 'team').strip()
    if not name:
        return jsonify({"status": "error", "message": "請提供 name"}), 400
    if status not in ('能打', '請假'):
        return jsonify({"status": "error", "message": "status 只接受 '能打' 或 '請假'"}), 400
    if context not in ('team', 'challenge'):
        return jsonify({"status": "error", "message": "context 只接受 'team' 或 'challenge'"}), 400
    player = Player.query.filter_by(player_name=name).first()
    if not player:
        return jsonify({"status": "error", "message": f"找不到玩家 '{name}'"}), 404
    can_fight = (status == '能打')
    if context == 'challenge':
        player.challenge_can_fight = can_fight
    else:
        player.can_fight = can_fight
    db.session.commit()
    return jsonify({
        "status": "success",
        "name": player.player_name,
        "context": context,
        "can_fight": can_fight
    })


# 4. 全員狀態重置為能打
@app.route('/api/bot/reset_all_status', methods=['POST'])
def bot_reset_all_status():
    data = request.get_json() or {}
    context = (data.get('context') or 'both').strip()
    if context not in ('team', 'challenge', 'both'):
        return jsonify({"status": "error", "message": "context 只接受 'team'、'challenge' 或 'both'"}), 400

    if context in ('team', 'both'):
        Player.query.update({Player.can_fight: True})
    if context in ('challenge', 'both'):
        Player.query.update({Player.challenge_can_fight: True})
    db.session.commit()

    return jsonify({"status": "success", "context": context})


if __name__ == '__main__':
    app.run(debug=True)