from flask import Flask, render_template

import database

app = Flask(__name__)

NAV_ITEMS = [
    {"endpoint": "index", "label": "首页", "path": "/"},
    {"endpoint": "goals", "label": "目标", "path": "/goals"},
    {"endpoint": "tasks", "label": "任务", "path": "/tasks"},
    {"endpoint": "reviews", "label": "复盘", "path": "/reviews"},
    {"endpoint": "assets", "label": "资产", "path": "/assets"},
    {"endpoint": "capabilities", "label": "能力", "path": "/capabilities"},
]


@app.route("/")
def index():
    return render_template("index.html", active_page="index", nav_items=NAV_ITEMS)


@app.route("/goals")
def goals():
    return render_template("goals.html", active_page="goals", nav_items=NAV_ITEMS)


@app.route("/tasks")
def tasks():
    return render_template("tasks.html", active_page="tasks", nav_items=NAV_ITEMS)


@app.route("/reviews")
def reviews():
    return render_template("reviews.html", active_page="reviews", nav_items=NAV_ITEMS)


@app.route("/assets")
def assets():
    return render_template("assets.html", active_page="assets", nav_items=NAV_ITEMS)


@app.route("/capabilities")
def capabilities():
    return render_template(
        "capabilities.html", active_page="capabilities", nav_items=NAV_ITEMS
    )


if __name__ == "__main__":
    database.init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)