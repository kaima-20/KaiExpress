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
    if "payouts" not in inspector.get_table_names():
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
            "name": "Ember & Crust",
            "email": "ember@kaiexpress.demo",
            "cuisine": "Wood-fired pizza",
            "city": "Nairobi",
            "items": [
                ("Ember Margherita", "San Marzano tomato, basil, and mozzarella.", 11.50),
                ("Smoky Pepperoni", "Crisp pepperoni, roasted peppers, and hot honey.", 14.00),
                ("Truffle Mushroom", "Garlic mushrooms, parmesan, and truffle oil.", 15.50),
            ],
        },
        {
            "name": "Miso Moon",
            "email": "miso@kaiexpress.demo",
            "cuisine": "Japanese comfort food",
            "city": "Mombasa",
            "items": [
                ("Tonkotsu Ramen", "Rich pork broth, noodles, egg, and spring onion.", 13.75),
                ("Crispy Katsu Bowl", "Panko chicken, steamed rice, cabbage, and katsu sauce.", 12.25),
                ("Yuzu Salmon", "Seared salmon, citrus glaze, edamame, and rice.", 16.00),
            ],
        },
        {
            "name": "The Green Table",
            "email": "green@kaiexpress.demo",
            "cuisine": "Fresh bowls",
            "city": "Kisumu",
            "items": [
                ("Charred Chicken Bowl", "Herb chicken, avocado, grains, and tahini dressing.", 12.50),
                ("Roasted Veggie Bowl", "Seasonal vegetables, hummus, grains, and herbs.", 10.75),
                ("Mango Lime Cooler", "Fresh mango, lime, mint, and sparkling water.", 4.50),
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