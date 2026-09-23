from models.db import db

class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    cuisine = db.Column(db.String(80))
    city = db.Column(db.String(80))
    # add relationships as needed
