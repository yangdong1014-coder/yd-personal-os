# 个人能力操作系统 v2

本地优先的个人操作系统，基于 Flask + SQLite + 原生 HTML/CSS/JS。

## 启动

```bash
pip install -r requirements.txt
python app.py
```

浏览器访问 http://localhost:5000

## 版本

- v0.1 — 系统骨架（基础路由 + 页面可打开）

## 目录

```
app.py          主入口
database.py     数据库初始化
data/yd_os.db   SQLite 数据文件
static/         静态资源
templates/      页面模板
```