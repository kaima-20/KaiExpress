from models.db import db

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    food_id = db.Column(db.Integer, db.ForeignKey('food.id'))
    quantity = db.Column(db.Integer, default=1)
    session_id = db.Column(db.String(128))
