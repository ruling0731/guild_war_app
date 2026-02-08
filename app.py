from flask import Flask, render_template, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///guild_war.db'
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

# 首頁：職業統計 + 分組顯示
@app.route('/')
def index():
    jobs = ["鐵衣", "血河", "碎夢", "神相", "九靈", "玄機", "素問", "龍吟"]
    stats = {}
    for job in jobs:
        total = Player.query.filter_by(job=job).count()
        leave = Player.query.filter_by(job=job, can_fight=False).count()
        stats[job] = {"total": total, "leave": leave, "can_fight": total - leave}

    grouped = {job: Player.query.filter_by(job=job).all() for job in jobs}
    return render_template('index.html', stats=stats, grouped=grouped, jobs=jobs)

# 新增玩家
@app.route('/add_player', methods=['GET'])
def add_player_page():
    return render_template('add_player.html')

@app.route('/add_player', methods=['POST'])
def add_player():
    name = request.form.get('name')
    job = request.form.get('job')
    leave = request.form.get('leave')
    group_name = request.form.get('group_name')
    team_name = request.form.get('team_name')
    role_note = request.form.get('role_note')
    can_fight = False if leave else True

    new_player = Player(player_name=name, job=job, can_fight=can_fight,
                        group_name=group_name, team_name=team_name, role_note=role_note)
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

# 分組管理
@app.route('/group')
def group_page():
    players = Player.query.all()
    return render_template('group.html', players=players)

@app.route('/update_group/<int:id>', methods=['POST'])
def update_group(id):
    player = Player.query.get_or_404(id)
    player.group_name = request.form.get('group_name')
    player.team_name = request.form.get('team_name')
    player.role_note = request.form.get('role_note')
    db.session.commit()
    return jsonify({"status": "success"})

# 職業分頁（純顯示）
@app.route('/job/<job>')
def job_page(job):
    players = Player.query.filter_by(job=job).all()
    return render_template('job.html', job=job, players=players)

# 匯出 Excel
@app.route('/export_all')
def export_all():
    players = Player.query.all()
    data = [{
        "分組": p.group_name,
        "隊伍": p.team_name,
        "名字": p.player_name,
        "職業": p.job,
        "備註": p.role_note,
        "狀態": "能打" if p.can_fight else "請假"
    } for p in players]

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # 主表
        df.to_excel(writer, sheet_name="大表", index=False)

        # 分組表（排除 None 和空字串）
        for group in df["分組"].dropna().unique():
            if group.strip():  # 確保不是空字串
                df[df["分組"] == group].to_excel(writer, sheet_name=group, index=False)

        # 候補表（沒有分隊的）
        candidate_df = df[df["隊伍"].isna() | (df["隊伍"] == "")]
        if not candidate_df.empty:
            candidate_df.to_excel(writer, sheet_name="候補", index=False)

    output.seek(0)
    response = make_response(output.read())
    response.headers["Content-Disposition"] = "attachment; filename=醉臥泡影間.xlsx"
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
    players = Player.query.all()
    return render_template('delete.html', players=players)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_player(id):
    player = Player.query.get_or_404(id)
    db.session.delete(player)
    db.session.commit()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)