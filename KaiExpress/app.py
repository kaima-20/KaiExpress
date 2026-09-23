import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()

from models.db import db
from config import Config

login_manager = LoginManager()
login_manager.login_view = "login"


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()

    # Simple public routes
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/admin/dashboard")
    def admin_dashboard():
        return render_template("admin/dashboard.html")

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
