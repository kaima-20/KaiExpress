from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from . import db


class User(db.Model, UserMixin):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(120), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)

    is_restaurant = db.Column(db.Boolean, default=False)

    cuisine = db.Column(db.String(80))

    city = db.Column(db.String(80))

    menu_items = db.relationship(
        "MenuItem",
        backref="restaurant",
        lazy=True
    )

    customer_orders = db.relationship(
        "Order",
        foreign_keys="Order.customer_id",
        backref="customer",
        lazy=True
    )

    restaurant_orders = db.relationship(
        "Order",
        foreign_keys="Order.restaurant_id",
        backref="restaurant",
        lazy=True
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password
        )


class MenuItem(db.Model):

    __tablename__ = "menu_items"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(120), nullable=False)

    description = db.Column(db.Text, nullable=False)

    price = db.Column(db.Float, nullable=False)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )


class Order(db.Model):

    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)

    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    customer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id")
    )

    menu_item_id = db.Column(
        db.Integer,
        db.ForeignKey("menu_items.id"),
        nullable=False
    )

    customer_name = db.Column(db.String(100))

    quantity = db.Column(db.Integer, default=1)

    price = db.Column(db.Float)

    payment_status = db.Column(db.String(20), nullable=False, default="pending")

    payment_method = db.Column(db.String(30))

    payment_reference = db.Column(db.String(120), unique=True)

    paid_at = db.Column(db.DateTime)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    menu_item = db.relationship(
        "MenuItem"
    )


class Payout(db.Model):
    __tablename__ = "payouts"

    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
    )
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    gross_amount = db.Column(db.Numeric(12, 2), nullable=False)
    platform_fee = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="requested")
    payment_reference = db.Column(db.String(120), unique=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)

    restaurant = db.relationship("User", backref="payouts")