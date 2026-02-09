#!/usr/bin/env python3
"""
資料庫初始化腳本
在 PythonAnywhere 的 Bash console 執行：
    cd ~/guild_war_app
    source venv/bin/activate
    python init_db.py
"""
import os
from app import app, db

# 確保 instance 資料夾存在
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)
    print(f"已建立資料夾: {instance_path}")

# 建立資料庫表格
with app.app_context():
    db.create_all()
    print("資料庫初始化完成！")
    print(f"資料庫位置: {app.config['SQLALCHEMY_DATABASE_URI']}")
