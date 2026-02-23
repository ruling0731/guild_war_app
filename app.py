from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pandas as pd
from io import BytesIO
from collections import defaultdict
import os

app = Flask(__name__)

# 資料庫路徑設定（支援本地開發和 PythonAnywhere）
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'guild_war.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# 玩家資料表
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_name = db.Column(db.String(50), nullable=False)
    job = db.Column(db.String(20), nullable=False)
    can_fight = db.Column(db.Boolean, default=True)
    group_name = db.Column(db.String(50))
    team_name = db.Column(db.String(50))
    role_note = db.Column(db.String(100))
    skill = db.Column(db.String(50))
    is_guild = db.Column(db.Boolean, default=False)
    is_challenge = db.Column(db.Boolean, default=False)
    challenge_group_name = db.Column(db.String(50))
    challenge_team_name = db.Column(db.String(50))
    challenge_skill = db.Column(db.String(50))

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
        new_cols = [
            ('is_guild',            'ALTER TABLE player ADD COLUMN is_guild BOOLEAN DEFAULT 0'),
            ('is_challenge',        'ALTER TABLE player ADD COLUMN is_challenge BOOLEAN DEFAULT 0'),
            ('challenge_group_name','ALTER TABLE player ADD COLUMN challenge_group_name VARCHAR(50)'),
            ('challenge_team_name', 'ALTER TABLE player ADD COLUMN challenge_team_name VARCHAR(50)'),
            ('challenge_skill',     'ALTER TABLE player ADD COLUMN challenge_skill VARCHAR(50)'),
        ]
        for col, ddl in new_cols:
            if col not in player_cols:
                conn.execute(db.text(ddl))
        conn.commit()

# 首頁：大表格顯示 + 職業統計
@app.route('/')
def index():
    jobs = ["鐵衣", "血河", "碎夢", "神相", "九靈", "玄機", "素問", "龍吟"]

    stats = {}
    for job in jobs:
        total = Player.query.filter_by(job=job).count()
        leave = Player.query.filter_by(job=job, can_fight=False).count()
        stats[job] = {"total": total, "leave": leave, "can_fight": total - leave}

    grouped = defaultdict(list)
    for p in Player.query.all():
        grouped[p.job].append(p)

    max_len = max((len(v) for v in grouped.values()), default=0)

    return render_template('index.html', stats=stats, grouped=grouped, jobs=jobs, max_len=max_len)

# 新增玩家
@app.route('/add_player', methods=['GET'])
def add_player_page():
    return render_template('add_player.html')

@app.route('/add_player', methods=['POST'])
def add_player():
    name = request.form.get('name')
    job = request.form.get('job')
    leave = request.form.get('leave')
    role_note = request.form.get('role_note')
    is_guild = bool(request.form.get('is_guild'))
    is_challenge = bool(request.form.get('is_challenge'))
    can_fight = False if leave else True

    new_player = Player(player_name=name, job=job, can_fight=can_fight,
                        role_note=role_note, is_guild=is_guild, is_challenge=is_challenge)
    db.session.add(new_player)
    db.session.commit()
    return jsonify({"status": "success"})

# 批量新增
@app.route('/batch_add', methods=['GET', 'POST'])
def batch_add():
    if request.method == 'POST':
        players_text = request.form.get('players', '').strip()
        lines = players_text.splitlines()
        valid_jobs = ["鐵衣","血河","碎夢","神相","九靈","玄機","素問","龍吟"]

        added_count = 0
        errors = []

        for idx, line in enumerate(lines, start=1):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                errors.append(f"第 {idx} 行格式錯誤：至少需要 名字,職業")
                continue

            name = parts[0]
            job = parts[1]
            note = parts[2] if len(parts) > 2 else None

            if job not in valid_jobs:
                errors.append(f"第 {idx} 行職業錯誤：{job}")
                continue

            new_player = Player(player_name=name, job=job, can_fight=True, role_note=note)
            db.session.add(new_player)
            added_count += 1

        if added_count > 0:
            db.session.commit()

        if errors:
            return render_template('batch_error.html', errors=errors, count=added_count)
        else:
            return render_template('batch_result.html', count=added_count)

    return render_template('batch_add.html')

# 職業分頁（總覽 + 批次更新）
@app.route('/job/<job>', methods=['GET', 'POST'])
def job_page(job):
    players = Player.query.filter_by(job=job).all()

    if request.method == 'POST':
        for player in players:
            player.group_name = request.form.get(f"group_name_{player.id}") or None
            player.team_name = request.form.get(f"team_name_{player.id}") or None
            player.role_note = request.form.get(f"role_note_{player.id}") or None
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
        player.is_guild = bool(request.form.get('is_guild'))
        player.is_challenge = bool(request.form.get('is_challenge'))

        db.session.commit()
        return redirect(url_for('job_page', job=player.job))

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
    players_data = [
        {"id": p.id, "name": p.player_name, "job": p.job, "can_fight": p.can_fight,
         "group_name": p.group_name or "", "team_name": p.team_name or "", "skill": p.skill or ""}
        for p in Player.query.filter_by(is_guild=True).all()
    ]
    return render_template('team_assign.html',
                           players=players_data,
                           team_name_configs=_build_team_name_configs(TeamConfig),
                           save_url='/team_assign_update',
                           page_title='團隊編成')

# 約戰頁面（只顯示約戰成員）
@app.route('/challenge_assign')
def challenge_assign():
    players_data = [
        {"id": p.id, "name": p.player_name, "job": p.job, "can_fight": p.can_fight,
         "group_name": p.challenge_group_name or "", "team_name": p.challenge_team_name or "", "skill": p.challenge_skill or ""}
        for p in Player.query.filter_by(is_challenge=True).all()
    ]
    return render_template('team_assign.html',
                           players=players_data,
                           team_name_configs=_build_team_name_configs(ChallengeTeamConfig),
                           save_url='/challenge_assign_update',
                           page_title='約戰')

def _save_assign_update(data, player_fields, config_model):
    for item in data.get('assignments', []):
        player = Player.query.get(item['id'])
        if player:
            setattr(player, player_fields['group'], item.get('group_name') or None)
            setattr(player, player_fields['team'],  item.get('team_name')  or None)
            setattr(player, player_fields['skill'], item.get('skill')      or None)
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
                        {'group': 'group_name', 'team': 'team_name', 'skill': 'skill'},
                        TeamConfig)
    return jsonify({"status": "success"})

# 約戰儲存 API
@app.route('/challenge_assign_update', methods=['POST'])
def challenge_assign_update():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "無效的資料格式"}), 400
    _save_assign_update(data,
                        {'group': 'challenge_group_name', 'team': 'challenge_team_name', 'skill': 'challenge_skill'},
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
        "職業": p.job,
        "絕技": p.skill,
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
    jobs = ["鐵衣", "血河", "碎夢", "神相", "九靈", "玄機", "素問", "龍吟"]
    grouped = defaultdict(list)
    for p in Player.query.all():
        grouped[p.job].append(p)
    max_len = max((len(v) for v in grouped.values()), default=0)
    return render_template('delete.html', grouped=grouped, jobs=jobs, max_len=max_len)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_player(id):
    player = Player.query.get_or_404(id)
    db.session.delete(player)
    db.session.commit()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)