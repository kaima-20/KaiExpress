from datetime import datetime
from uuid import uuid4

import requests
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
    payment_methods = {
        "card": "Paystack / Card",
        "paystack": "Paystack",
        "bank_transfer": "Bank Transfer",
        "ussd": "USSD",
        "qr": "QR Code",
        "cash_on_delivery": "Cash on Delivery",
    }

    def get_order_total(order):
        return round((float(order.price or 0) * int(order.quantity or 1)), 2)

    def paystack_headers():
        return {
            "Authorization": f"Bearer {app.config.get('PAYSTACK_SECRET_KEY', '')}",
            "Content-Type": "application/json",
        }

    def verify_paystack_payment(reference):
        secret_key = app.config.get("PAYSTACK_SECRET_KEY")
        if not secret_key:
            return {"status": False, "message": "Paystack secret key is not configured."}

        response = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=paystack_headers(),
            timeout=30,
        )
        data = response.json()
        if response.status_code != 200 or not data.get("status"):
            return {
                "status": False,
                "message": data.get("message", "Paystack verification failed."),
            }

        payload = data.get("data") or {}
        return {
            "status": payload.get("status") == "success",
            "message": payload.get("gateway_response") or data.get("message"),
            "reference": payload.get("reference"),
            "amount": payload.get("amount"),
        }

    def initialize_paystack_payment(order):
        secret_key = app.config.get("PAYSTACK_SECRET_KEY")
        if not secret_key:
            return None, "Paystack is not configured. Add PAYSTACK_SECRET_KEY to your environment variables."

        total_amount = int(round(get_order_total(order) * 100))
        if total_amount <= 0:
            return None, "The order total must be greater than zero before paying."

        channels = {
            "card": ["card"],
            "bank_transfer": ["bank_transfer"],
            "ussd": ["ussd"],
            "qr": ["qr"],
        }
        reference = f"KAI-{order.id}-{uuid4().hex[:12].upper()}"
        payload = {
            "email": current_user.email,
            "amount": total_amount,
            "currency": "NGN",
            "reference": reference,
            "callback_url": url_for("paystack_callback", order_id=order.id, _external=True),
            "metadata": {
                "order_id": order.id,
                "customer_name": order.customer_name or current_user.name,
                "total_amount": get_order_total(order),
                "payment_method": order.payment_method,
            },
        }
        if order.payment_method != "paystack":
            payload["channels"] = channels[order.payment_method]

        try:
            response = requests.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers=paystack_headers(),
                timeout=30,
            )
            response_data = response.json()
        except requests.RequestException as exc:
            app.logger.error("Paystack init failed: %s", exc)
            return None, f"Paystack initialization failed: {exc}"

        if response.status_code != 200 or not response_data.get("status"):
            message = response_data.get("message") or "Unable to start Paystack payment right now."
            app.logger.error("Paystack init error: %s", message)
            return None, message

        authorization_url = (response_data.get("data") or {}).get("authorization_url")
        if not authorization_url:
            app.logger.error("Paystack response missing authorization_url: %s", response_data)
            return None, "Paystack did not return a valid payment link."

        order.payment_reference = reference
        order.payment_status = "pending"
        db.session.commit()
        return authorization_url, None

    def build_order(data, restaurant_id):
        payment_method = data.get("payment_method", "").strip()
        if payment_method not in payment_methods:
            return None, "Please select a valid payment method."

        item_id = positive_int(data.get("item_id"))
        quantity = max(1, positive_int(data.get("quantity"), 1))
        restaurant = User.query.filter_by(id=restaurant_id, is_restaurant=True).first()
        if not restaurant:
            return None, "Restaurant not found."
        item = MenuItem.query.filter_by(id=item_id, restaurant_id=restaurant_id).first()
        if not item:
            return None, "Menu item not found."

        if current_user.is_authenticated and not current_user.is_restaurant:
            customer_name = current_user.name
            customer_id = current_user.id
        else:
            customer_name = data.get("customer_name", "Guest").strip() or "Guest"
            customer_id = None

        return Order(
            restaurant_id=restaurant_id,
            menu_item_id=item.id,
            customer_id=customer_id,
            customer_name=customer_name,
            quantity=quantity,
            price=item.price,
            payment_method=payment_method,
            payment_status="pending",
        ), None

    def normalize_payment_method(order):
        if order.payment_method in {None, "paystack"}:
            order.payment_method = "card"
            db.session.commit()
        return order.payment_method

    @app.route("/api/restaurants")
    @login_required
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
    @login_required
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
    @login_required
    def home():
        search = request.args.get("q", "").strip()
        cuisine = request.args.get("cuisine", "").strip()
        if current_user.is_authenticated and not current_user.is_restaurant:
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
        else:
            restaurants = []
            cuisines = []
        return render_template(
            "user/home.html",
            restaurants=restaurants,
            cuisines=cuisines,
            search=search,
            active_cuisine=cuisine,
        )

    @app.route("/restaurants")
    @login_required
    def restaurants_page():
        restaurants = User.query.filter_by(is_restaurant=True).order_by(User.name.asc()).all()
        return render_template("user/restaurants.html", restaurants=restaurants)

    @app.route("/menu")
    @login_required
    def menu_page():
        restaurants = User.query.filter_by(is_restaurant=True).order_by(User.name.asc()).all()
        return render_template("user/menu.html", restaurants=restaurants)

    @app.route("/about")
    def about_page():
        return render_template("user/about.html")

    @app.route("/contact")
    def contact_page():
        return render_template("user/contact.html")

    @app.route("/restaurant/<int:restaurant_id>")
    @login_required
    def restaurant_page(restaurant_id):
        restaurant = User.query.filter_by(id=restaurant_id, is_restaurant=True).first()
        if not restaurant:
            return redirect(url_for("home"))
        menu = MenuItem.query.filter_by(restaurant_id=restaurant_id).all()
        return render_template("user/restaurant.html", restaurant=restaurant, menu=menu)

    @app.route("/restaurant/<int:restaurant_id>/order", methods=["POST"])
    def place_order(restaurant_id):
        order, error = build_order(request.form, restaurant_id)
        if error:
            flash(error, "danger")
            return redirect(url_for("restaurant_page", restaurant_id=restaurant_id))
        db.session.add(order)
        db.session.commit()

        if current_user.is_authenticated and not current_user.is_restaurant:
            flash("Your order was created. Continue with your selected payment method.", "success")
            return redirect(url_for("payment_checkout", order_id=order.id))
        flash("Your order was submitted successfully.", "success")
        return redirect(url_for("restaurant_page", restaurant_id=restaurant_id))

    @app.route("/orders")
    @login_required
    def orders():
        if current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))
        orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
        return render_template("user/orders.html", orders=orders)

    @app.route("/orders/<int:order_id>/checkout", methods=["GET"]) 
    @login_required
    def payment_checkout(order_id):
        if current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))

        order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
        normalize_payment_method(order)
        if order.payment_status == "paid":
            flash("This order has already been paid.", "info")
            return redirect(url_for("orders"))

        return render_template("user/payment.html", order=order, payment_methods=payment_methods)

    @app.route("/orders/<int:order_id>/paystack/initialize", methods=["POST"])
    @login_required
    def paystack_initialize(order_id):
        if current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))

        order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
        normalize_payment_method(order)
        if order.payment_status == "paid":
            flash("This order has already been paid.", "info")
            return redirect(url_for("orders"))

        selected_method = request.form.get("payment_method", order.payment_method).strip()
        if selected_method not in payment_methods:
            flash("Please select a valid payment method.", "warning")
            return redirect(url_for("payment_checkout", order_id=order.id))

        order.payment_method = selected_method
        if selected_method == "cash_on_delivery":
            order.payment_status = "pending"
            order.payment_reference = None
            db.session.commit()
            flash("Cash on delivery selected. Payment is due when your order arrives.", "success")
            return redirect(url_for("orders"))

        if order.payment_method not in {"card", "paystack", "bank_transfer", "ussd", "qr"}:
            flash("This order does not require an online payment.", "info")
            return redirect(url_for("orders"))

        db.session.commit()
        authorization_url, error = initialize_paystack_payment(order)
        if error:
            flash(error, "warning")
            return redirect(url_for("payment_checkout", order_id=order.id))
        return redirect(authorization_url)

    @app.route("/orders/<int:order_id>/paystack/callback", methods=["GET", "POST"])
    @login_required
    def paystack_callback(order_id):
        if current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))

        order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
        reference = request.args.get("reference") or request.args.get("trxref")

        if not reference:
            flash("Payment was cancelled or did not complete. Please try again.", "warning")
            return redirect(url_for("payment_checkout", order_id=order.id))

        verification = verify_paystack_payment(reference)
        expected_amount = int(round(get_order_total(order) * 100))
        reference_matches = not order.payment_reference or order.payment_reference == reference
        amount_matches = verification.get("amount") == expected_amount
        transaction_matches = verification.get("reference") == reference
        if verification.get("status") and reference_matches and amount_matches and transaction_matches:
            order.payment_status = "paid"
            order.payment_reference = reference
            order.paid_at = datetime.utcnow()
            db.session.commit()
            flash("Payment received. Your order is being prepared.", "success")
            return redirect(url_for("orders"))

        flash("Payment could not be verified for the expected order amount. Please try again or choose another payment method.", "warning")
        return redirect(url_for("payment_checkout", order_id=order.id))

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
                "payment_status": order.payment_status,
                "payment_method": order.payment_method,
                "checkout_url": url_for("payment_checkout", order_id=order.id),
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
        order, error = build_order(data, restaurant_id)
        if error:
            return json_response(False, error, status=400)
        db.session.add(order)
        db.session.commit()
        if order.customer_id:
            if order.payment_method == "cash_on_delivery":
                return json_response(True, "Order placed. Payment is due when your order is delivered.", next=url_for("orders"))
            return json_response(True, "Order created. Continue with your selected payment method.", next=url_for("payment_checkout", order_id=order.id))
        return json_response(True, "Order submitted successfully.", next=url_for("restaurant_page", restaurant_id=restaurant_id))

    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        logout_user()
        return json_response(True, "Logged out successfully.", next=url_for("home"))

    @app.route("/logout")
    def logout():
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("home"))
