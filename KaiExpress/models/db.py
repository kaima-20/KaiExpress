from flask_sqlalchemy import SQLAlchemy

# shared DB instance; call db.init_app(app) in application factory
db = SQLAlchemy()
