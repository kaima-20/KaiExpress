from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy.exc import IntegrityError


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


def positive_int(value, default=0):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def init_user_routes(app, db, User, MenuItem, Order):
    @app.route("/api/restaurants")
    def api_restaurants():
        restaurants = User.query.filter_by(is_restaurant=True).order_by(User.name.asc()).all()
        return {
            "success": True,
            "restaurants": [{
                "id": restaurant.id,
                "name": restaurant.name,
                "cuisine": restaurant.cuisine,
                "city": restaurant.city,
                "menu_url": url_for("api_restaurant_menu", restaurant_id=restaurant.id),
            } for restaurant in restaurants],
        }

    @app.route("/api/restaurants/<int:restaurant_id>/menu")
    def api_restaurant_menu(restaurant_id):
        restaurant = User.query.filter_by(id=restaurant_id, is_restaurant=True).first()
        if not restaurant:
            return json_response(False, "Restaurant not found.", status=404)
        return {
            "success": True,
            "restaurant": restaurant.name,
            "items": [{
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "price": item.price,
            } for item in MenuItem.query.filter_by(restaurant_id=restaurant_id).all()],
        }

    @app.route("/")
    def home():
        search = request.args.get("q", "").strip()
        cuisine = request.args.get("cuisine", "").strip()
        query = User.query.filter_by(is_restaurant=True)
        if search:
            query = query.filter(
                db.or_(
                    User.name.ilike(f"%{search}%"),
                    User.cuisine.ilike(f"%{search}%"),
                    User.city.ilike(f"%{search}%"),
                    User.menu_items.any(MenuItem.title.ilike(f"%{search}%")),
                    User.menu_items.any(MenuItem.description.ilike(f"%{search}%")),
                )
            )
        if cuisine:
            query = query.filter_by(cuisine=cuisine)
        restaurants = query.order_by(User.name.asc()).all()
        cuisines = [row[0] for row in db.session.query(User.cuisine).filter(
            User.is_restaurant.is_(True), User.cuisine.isnot(None)
        ).distinct().order_by(User.cuisine.asc()).all()]
        return render_template(
            "user/home.html",
            restaurants=restaurants,
            cuisines=cuisines,
            search=search,
            active_cuisine=cuisine,
        )

    @app.route("/restaurant/<int:restaurant_id>")
    def restaurant_page(restaurant_id):
        restaurant = User.query.filter_by(id=restaurant_id, is_restaurant=True).first()
        if not restaurant:
            return redirect(url_for("home"))
        menu = MenuItem.query.filter_by(restaurant_id=restaurant_id).all()
        return render_template("user/restaurant.html", restaurant=restaurant, menu=menu)

    @app.route("/restaurant/<int:restaurant_id>/order", methods=["POST"])
    def place_order(restaurant_id):
        restaurant = User.query.filter_by(id=restaurant_id, is_restaurant=True).first()
        if not restaurant:
            return redirect(url_for("home"))

        item_id = positive_int(request.form.get("item_id"))
        quantity = max(1, positive_int(request.form.get("quantity"), 1))
        item = MenuItem.query.filter_by(id=item_id, restaurant_id=restaurant_id).first()
        if not item:
            flash("Please select a valid menu item.", "danger")
            return redirect(url_for("restaurant_page", restaurant_id=restaurant_id))

        if current_user.is_authenticated and not current_user.is_restaurant:
            customer_name = current_user.name
            customer_id = current_user.id
        else:
            customer_name = request.form.get("customer_name", "Guest").strip() or "Guest"
            customer_id = None

        order = Order(
            restaurant_id=restaurant_id,
            menu_item_id=item.id,
            customer_id=customer_id,
            customer_name=customer_name,
            quantity=quantity,
            price=item.price,
        )
        db.session.add(order)
        db.session.commit()
        flash("Your order was submitted successfully.", "success")

        if current_user.is_authenticated and not current_user.is_restaurant:
            return redirect(url_for("orders"))
        return redirect(url_for("restaurant_page", restaurant_id=restaurant_id))

    @app.route("/orders")
    @login_required
    def orders():
        if current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))
        orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
        return render_template("user/orders.html", orders=orders)

    @app.route("/api/orders")
    @login_required
    def api_orders():
        if current_user.is_restaurant:
            return json_response(False, "Customer access is required.", status=403)
        orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
        return {
            "success": True,
            "orders": [{
                "id": order.id,
                "restaurant": order.restaurant.name,
                "item": order.menu_item.title,
                "quantity": order.quantity,
                "total": round((order.price or 0) * (order.quantity or 1), 2),
                "created_at": order.created_at.isoformat() if order.created_at else None,
            } for order in orders],
        }

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated and not current_user.is_restaurant:
            return redirect(url_for("orders"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email, is_restaurant=False).first()
            if user and user.check_password(password):
                login_user(user)
                flash("Logged in successfully.", "success")
                return redirect(url_for("orders"))
            flash("Invalid credentials. Please check your email and password.", "danger")
        return render_template("user/login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated and not current_user.is_restaurant:
            return redirect(url_for("orders"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not name or not email or len(password) < 8:
                flash("All fields are required.", "warning")
                return redirect(url_for("register"))

            if User.query.filter_by(email=email).first():
                flash("Email already exists. Please log in.", "warning")
                return redirect(url_for("login"))

            user = User(name=name, email=email, is_restaurant=False)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Email already exists. Please log in.", "warning")
                return redirect(url_for("login"))
            login_user(user)
            flash("Registration successful. You are now logged in.", "success")
            return redirect(url_for("orders"))

        return render_template("user/register.html")

    @app.route("/api/login", methods=["POST"])
    def api_login():
        data = request_data()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        user = User.query.filter_by(email=email, is_restaurant=False).first()
        if user and user.check_password(password):
            login_user(user)
            return json_response(True, "Logged in successfully.", next=url_for("orders"))
        return json_response(False, "Invalid credentials.", status=401)

    @app.route("/api/register", methods=["POST"])
    def api_register():
        data = request_data()
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        if not name or not email or len(password) < 8:
            return json_response(False, "Name, email, and a password of at least 8 characters are required.", status=400)
        if User.query.filter_by(email=email).first():
            return json_response(False, "Email already exists. Please log in.", status=400)
        user = User(name=name, email=email, is_restaurant=False)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return json_response(False, "Email already exists. Please log in.", status=400)
        login_user(user)
        return json_response(True, "Registration successful.", next=url_for("orders"))

    @app.route("/api/checkout", methods=["POST"])
    def api_checkout():
        data = request_data()
        restaurant_id = positive_int(data.get("restaurant_id"))
        item_id = positive_int(data.get("item_id"))
        quantity = max(1, positive_int(data.get("quantity"), 1))
        restaurant = User.query.filter_by(id=restaurant_id, is_restaurant=True).first()
        if not restaurant:
            return json_response(False, "Restaurant not found.", status=404)
        item = MenuItem.query.filter_by(id=item_id, restaurant_id=restaurant_id).first()
        if not item:
            return json_response(False, "Menu item not found.", status=404)

        if current_user.is_authenticated and not current_user.is_restaurant:
            customer_name = current_user.name
            customer_id = current_user.id
        else:
            customer_name = data.get("customer_name", "Guest").strip() or "Guest"
            customer_id = None

        order = Order(
            restaurant_id=restaurant_id,
            menu_item_id=item.id,
            customer_id=customer_id,
            customer_name=customer_name,
            quantity=quantity,
            price=item.price,
        )
        db.session.add(order)
        db.session.commit()
        next_url = url_for("orders") if customer_id else url_for("restaurant_page", restaurant_id=restaurant_id)
        return json_response(True, "Checkout successful.", next=next_url)

    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        logout_user()
        return json_response(True, "Logged out successfully.", next=url_for("home"))

    @app.route("/logout")
    def logout():
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("home"))
