# PythonAnywhere WSGI 配置檔案
# 在 PythonAnywhere 的 WSGI configuration file 中貼上以下內容：
#
# import sys
# import os
# project_home = '/home/你的用戶名/guild_war_app'
# if project_home not in sys.path:
#     sys.path.insert(0, project_home)
# os.environ['FLASK_APP'] = 'app.py'
# from app import app as application

from app import app as application

if __name__ == "__main__":
    application.run()
