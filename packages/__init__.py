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
            "name": "Ember & Crust",
            "email": "ember@kaiexpress.demo",
            "cuisine": "Wood-fired pizza",
            "city": "Chicago",
            "items": [
                ("Ember Margherita", "San Marzano tomato, basil, and fresh mozzarella.", 11.50),
                ("Smoky Pepperoni", "Crisp pepperoni, roasted peppers, and hot honey drizzle.", 14.00),
                ("Truffle Mushroom", "Garlic mushrooms, parmesan, and truffle cream.", 15.50),
            ],
        },
        {
            "name": "Harbor & Hearth",
            "email": "miso@kaiexpress.demo",
            "cuisine": "American steakhouse",
            "city": "New York",
            "items": [
                ("Herb Butter Ribeye", "Prime ribeye with roasted potatoes and charred greens.", 27.00),
                ("Crispy Chicken Club", "Grilled chicken, bacon, lettuce, tomato, and aioli.", 16.25),
                ("Maple Glazed Salmon", "Seared salmon with lemon rice and seasonal veg.", 21.75),
            ],
        },
        {
            "name": "The Green Table",
            "email": "green@kaiexpress.demo",
            "cuisine": "Fresh salads & bowls",
            "city": "Los Angeles",
            "items": [
                ("Citrus Chicken Bowl", "Herb chicken, avocado, grains, and lemon vinaigrette.", 12.50),
                ("Roasted Veggie Bowl", "Seasonal vegetables, hummus, grains, and herbs.", 10.75),
                ("Mango Lime Cooler", "Fresh mango, lime, mint, and sparkling water.", 4.50),
            ],
        },
        {
            "name": "Starlight Diner",
            "email": "streetbites@kaiexpress.demo",
            "cuisine": "American comfort food",
            "city": "Austin",
            "items": [
                ("Classic Smash Burger", "Two seared beef patties, cheddar, pickles, and burger sauce.", 10.50),
                ("Buffalo Chicken Sandwich", "Crispy chicken, slaw, and spicy ranch in a toasted bun.", 11.25),
                ("Loaded Fries", "Crispy fries with cheddar, scallions, and smoky aioli.", 8.75),
                ("Spicy Buffalo Wings", "Juicy wings tossed in a bold house buffalo glaze.", 9.25),
                ("Bistro Chicken Caesar", "Grilled chicken, romaine, parmesan, and crisp croutons.", 12.00),
                ("House Lemonade", "Freshly squeezed lemon, mint, and sparkling water.", 4.25),
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