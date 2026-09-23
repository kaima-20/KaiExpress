import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///kaiexpress.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
