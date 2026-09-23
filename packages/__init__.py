import os

from dotenv import load_dotenv
from flask import request
from sqlalchemy import inspect, text
from uuid import uuid4

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()


def request_data():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


def json_response(success, message=None, status=200, **kwargs):
    payload = {"success": success}
    if message is not None:
        payload["message"] = message
    payload.update(kwargs)
    return payload, status


def create_app():
    load_dotenv()
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-secret")
    app.config["PAYSTACK_SECRET_KEY"] = os.getenv("PAYSTACK_SECRET_KEY", "")
    app.config["PAYSTACK_PUBLIC_KEY"] = os.getenv("PAYSTACK_PUBLIC_KEY", "")
    app.config["PAYSTACK_TEST_MODE"] = True

    basedir = os.path.abspath(os.path.dirname(__file__))
    database_url = os.getenv("DATABASE_URL")
    if not database_url and os.getenv("MYSQL_HOST"):
        database_url = "mysql+pymysql://{user}:{password}@{host}:{port}/{database}".format(
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            host=os.getenv("MYSQL_HOST"),
            port=os.getenv("MYSQL_PORT", "3306"),
            database=os.getenv("MYSQL_DATABASE", "kaiexpress"),
        )
    if not database_url:
        database_url = "sqlite:///" + os.path.join(basedir, "..", "app.db")
    if database_url.startswith("mysql://"):
        database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message_category = "warning"

    from .models import User, MenuItem, Order, Payout

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .user_routes import init_user_routes
    from .admin_routes import init_admin_routes

    init_user_routes(app, db, User, MenuItem, Order)
    init_admin_routes(app, db, User, MenuItem, Order, Payout)

    with app.app_context():
        db.create_all()
        upgrade_schema(db)
        seed_catalog(db, User, MenuItem)

    return app


def upgrade_schema(db):
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    if "orders" in tables:
        order_columns = {column["name"] for column in inspector.get_columns("orders")}
        with db.engine.begin() as connection:
            if "payment_status" not in order_columns:
                connection.execute(text(
                    "ALTER TABLE orders ADD COLUMN payment_status VARCHAR(20) NOT NULL DEFAULT 'pending'"
                ))
            if "payment_method" not in order_columns:
                connection.execute(text(
                    "ALTER TABLE orders ADD COLUMN payment_method VARCHAR(30)"
                ))
            if "payment_reference" not in order_columns:
                connection.execute(text(
                    "ALTER TABLE orders ADD COLUMN payment_reference VARCHAR(40)"
                ))
            if "paid_at" not in order_columns:
                connection.execute(text(
                    "ALTER TABLE orders ADD COLUMN paid_at DATETIME"
                ))

    if "payouts" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("payouts")}
    with db.engine.begin() as connection:
        if "payment_reference" not in columns:
            connection.execute(text(
                "ALTER TABLE payouts ADD COLUMN payment_reference VARCHAR(120)"
            ))
        payout_ids = connection.execute(text(
            "SELECT id FROM payouts WHERE payment_reference IS NULL"
        )).scalars().all()
        for payout_id in payout_ids:
            connection.execute(
                text("UPDATE payouts SET payment_reference = :reference WHERE id = :id"),
                {"reference": f"KAI-MIGRATED-{uuid4().hex[:12].upper()}", "id": payout_id},
            )


def seed_catalog(db, User, MenuItem):
    catalog = [
        {
            "name": "Lagos Grill House",
            "email": "lagos@kaiexpress.demo",
            "cuisine": "Lagos favourites",
            "city": "Lagos",
            "items": [
                ("Jollof Rice & Chicken", "Rich tomato rice with grilled chicken, peppers, and aromatic spices.", 12.50),
                ("Ewa Agoyin", "Creamy beans served with pepper sauce and plantain.", 8.50),
                ("Ofada Rice & Ayamase", "Local rice served with green pepper stew and grilled protein.", 11.75),
                ("Seafood Pepper Soup", "Spicy seafood broth with prawns, fish, and fresh peppers.", 13.50),
            ],
        },
        {
            "name": "Anambra Pot Kitchen",
            "email": "anambra@kaiexpress.demo",
            "cuisine": "Anambra specialities",
            "city": "Awka",
            "items": [
                ("Nkwobi", "Cow foot in a spicy palm-oil sauce with herbs.", 9.75),
                ("Abacha", "African salad with ukpaka, palm oil, and traditional toppings.", 7.50),
                ("Ofe Nsala", "White soup with catfish, spices, and fresh herbs.", 10.50),
                ("Isi Ewu", "Goat meat in a rich peppery sauce.", 11.25),
            ],
        },
        {
            "name": "Enugu Heritage Kitchen",
            "email": "enugu@kaiexpress.demo",
            "cuisine": "Enugu soups & staples",
            "city": "Enugu",
            "items": [
                ("Okpa", "Cornmeal wrapped dish with rich traditional seasoning.", 8.00),
                ("Abacha", "African salad prepared with fresh vegetables and pepper mix.", 7.50),
                ("Oha Soup & Fufu", "Green leafy soup with yam flour and assorted meat.", 12.00),
                ("Nsala Soup", "Peppery catfish soup with fresh spices.", 10.75),
            ],
        },
        {
            "name": "Imo Family Feast",
            "email": "imo@kaiexpress.demo",
            "cuisine": "Imo classics",
            "city": "Owerri",
            "items": [
                ("Ofe Owerri", "Traditional soup with banga flavour and assorted meat.", 11.50),
                ("Ukpaka", "Local delicacy with savoury seasoning and starch.", 9.25),
                ("Egusi & Fufu", "Ground melon soup with rich seasoning and pounded yam.", 12.50),
                ("Pepper Soup", "Spicy soup with chicken, goat meat, and herbs.", 10.25),
            ],
        },
        {
            "name": "Rivers Seafood Hub",
            "email": "rivers@kaiexpress.demo",
            "cuisine": "Rivers seafood",
            "city": "Port Harcourt",
            "items": [
                ("Banga Soup", "Palm kernel soup with fresh fish and herbs.", 11.00),
                ("Native Jollof", "Traditional rice with rich flavour and local seasoning.", 12.50),
                ("Fisherman's Soup", "Seafood medley with okra and pepper base.", 13.25),
                ("Seafood Okro", "Fresh okra soup with prawns, fish, and spices.", 12.75),
            ],
        },
        {
            "name": "Kano Saffron Kitchen",
            "email": "kano@kaiexpress.demo",
            "cuisine": "Northern staples",
            "city": "Kano",
            "items": [
                ("Tuwo Shinkafa", "Soft rice pudding served with soup and grilled meat.", 10.50),
                ("Miyan Kuka", "Soup made with dried okra leaves and protein.", 9.75),
                ("Suya", "Spiced grilled meat served with onion and peppers.", 8.50),
                ("Masa", "Fermented rice cake with a soft, airy centre.", 7.25),
            ],
        },
        {
            "name": "Ibadan Heritage Table",
            "email": "oyo@kaiexpress.demo",
            "cuisine": "Southwest classics",
            "city": "Ibadan",
            "items": [
                ("Amala & Ewedu", "Smooth yam flour swallow with green vegetable sauce.", 9.00),
                ("Gbegiri", "Bean soup with rich local seasoning.", 8.75),
                ("Ofada Rice", "Local rice and stew with a rich pepper base.", 10.25),
                ("Peppered Meat", "Well-seasoned grilled meat with peppers and onions.", 11.50),
            ],
        },
        {
            "name": "Global Bites Studio",
            "email": "global@kaiexpress.demo",
            "cuisine": "A Taste of the World",
            "city": "Lagos",
            "items": [
                ("Chicken Ramen", "Comforting noodles with roasted chicken and savoury broth.", 14.25),
                ("Bibimbap", "Korean mixed rice bowl with vegetables and protein.", 13.50),
                ("Margherita Pizza", "Classic pizza with tomato base and mozzarella.", 12.75),
                ("Crêpes", "Thin pancakes filled with sweet or savoury toppings.", 8.50),
            ],
        },
    ]

    changed = False
    for restaurant_data in catalog:
        restaurant = User.query.filter_by(email=restaurant_data["email"]).first()
        if not restaurant:
            restaurant = User(
                name=restaurant_data["name"],
                email=restaurant_data["email"],
                is_restaurant=True,
                cuisine=restaurant_data["cuisine"],
                city=restaurant_data["city"],
            )
            restaurant.set_password("kaiexpress-demo")
            db.session.add(restaurant)
            db.session.flush()
            changed = True

        existing_titles = {
            item.title for item in MenuItem.query.filter_by(restaurant_id=restaurant.id).all()
        }
        for title, description, price in restaurant_data["items"]:
            if title not in existing_titles:
                db.session.add(MenuItem(
                    title=title,
                    description=description,
                    price=price,
                    restaurant_id=restaurant.id,
                ))
                changed = True

    if changed:
        db.session.commit()