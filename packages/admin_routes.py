from flask import render_template, request, redirect, url_for, flash
from flask_login import (
    login_user,
    login_required,
    logout_user,
    current_user
)
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from . import request_data, json_response


def payout_summary(restaurant_id, Order, Payout):
    orders = Order.query.filter_by(restaurant_id=restaurant_id).all()
    cents = Decimal("0.01")
    gross = sum(
        Decimal(str(order.price or 0)) * Decimal(str(order.quantity or 1))
        for order in orders
    ).quantize(cents, rounding=ROUND_HALF_UP)
    processed_gross = sum(
        Decimal(str(payout.gross_amount or 0)) for payout in Payout.query.filter(
            Payout.restaurant_id == restaurant_id,
            Payout.status.in_(["requested", "paid"]),
        ).all()
    ).quantize(cents, rounding=ROUND_HALF_UP)
    available_gross = max(Decimal("0"), gross - processed_gross).quantize(cents, rounding=ROUND_HALF_UP)
    platform_fee = (available_gross * Decimal("0.10")).quantize(cents, rounding=ROUND_HALF_UP)
    available = (available_gross - platform_fee).quantize(cents, rounding=ROUND_HALF_UP)
    return {
        "gross": float(gross),
        "processed_gross": float(processed_gross),
        "available_gross": float(available_gross),
        "platform_fee": float(platform_fee),
        "available": float(available),
    }


def build_payout(restaurant_id, summary, Payout):
    return Payout(
        restaurant_id=restaurant_id,
        amount=summary["available"],
        gross_amount=summary["available_gross"],
        platform_fee=summary["platform_fee"],
        payment_reference=f"KAI-{uuid4().hex[:16].upper()}",
        status="requested",
    )


def init_admin_routes(app, db, User, MenuItem, Order, Payout):
    @app.route("/restaurant/login", methods=["GET", "POST"])
    def restaurant_login():
        if current_user.is_authenticated and current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            restaurant = User.query.filter_by(email=email, is_restaurant=True).first()
            if restaurant and restaurant.check_password(password):
                login_user(restaurant)
                flash("Restaurant signed in successfully.", "success")
                return redirect(url_for("restaurant_dashboard"))
            flash("Invalid restaurant credentials.", "danger")
        return render_template("admin/login.html")

    @app.route("/restaurant/register", methods=["GET", "POST"])
    def restaurant_register():
        if current_user.is_authenticated and current_user.is_restaurant:
            return redirect(url_for("restaurant_dashboard"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            cuisine = request.form.get("cuisine", "").strip()
            city = request.form.get("city", "").strip()
            if not name or not email or len(password) < 8 or not cuisine or not city:
                flash("All fields are required and the password must have at least 8 characters.", "warning")
                return redirect(url_for("restaurant_register"))

            if User.query.filter_by(email=email).first():
                flash("Email already exists. Please log in.", "warning")
                return redirect(url_for("restaurant_login"))

            restaurant = User(name=name, email=email, is_restaurant=True, cuisine=cuisine, city=city)
            restaurant.set_password(password)
            db.session.add(restaurant)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Email already exists. Please log in.", "warning")
                return redirect(url_for("restaurant_login"))
            login_user(restaurant)
            flash("Restaurant registered successfully.", "success")
            return redirect(url_for("restaurant_dashboard"))

        return render_template("admin/register.html")

    @app.route("/restaurant/dashboard")
    @login_required
    def restaurant_dashboard():
        if not current_user.is_authenticated or not current_user.is_restaurant:
            flash("Unauthorized access.", "danger")
            return redirect(url_for("home"))
        orders = Order.query.filter_by(restaurant_id=current_user.id).order_by(Order.created_at.desc()).all()
        menu = MenuItem.query.filter_by(restaurant_id=current_user.id).all()
        payouts = Payout.query.filter_by(restaurant_id=current_user.id).order_by(Payout.requested_at.desc()).all()
        return render_template(
            "admin/dashboard.html",
            orders=orders,
            menu=menu,
            payouts=payouts,
            payout_summary=payout_summary(current_user.id, Order, Payout),
        )

    @app.route("/restaurant/payouts/request", methods=["POST"])
    @login_required
    def request_payout():
        if not current_user.is_restaurant:
            return redirect(url_for("home"))
        summary = payout_summary(current_user.id, Order, Payout)
        if summary["available"] <= 0:
            flash("There is no available balance to pay out yet.", "warning")
            return redirect(url_for("restaurant_dashboard"))

        payout = build_payout(current_user.id, summary, Payout)
        db.session.add(payout)
        db.session.commit()
        flash("Payout request submitted successfully.", "success")
        return redirect(url_for("restaurant_dashboard"))

    @app.route("/restaurant/menu", methods=["POST"])
    @login_required
    def add_menu_item():
        if not current_user.is_restaurant:
            return redirect(url_for("home"))

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        try:
            price = float(request.form.get("price", ""))
        except (TypeError, ValueError):
            price = -1

        if not title or not description or price <= 0:
            flash("Enter a name, description, and a positive price.", "warning")
            return redirect(url_for("restaurant_dashboard"))

        db.session.add(MenuItem(
            title=title,
            description=description,
            price=price,
            restaurant_id=current_user.id,
        ))
        db.session.commit()
        flash("Menu item added successfully.", "success")
        return redirect(url_for("restaurant_dashboard"))

    @app.route("/api/restaurant/login", methods=["POST"])
    def api_restaurant_login():
        data = request_data()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        restaurant = User.query.filter_by(email=email, is_restaurant=True).first()
        if restaurant and restaurant.check_password(password):
            login_user(restaurant)
            return json_response(True, "Restaurant signed in successfully.", next=url_for("restaurant_dashboard"))
        return json_response(False, "Invalid restaurant credentials.", status=401)

    @app.route("/api/restaurant/register", methods=["POST"])
    def api_restaurant_register():
        data = request_data()
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        cuisine = data.get("cuisine", "").strip()
        city = data.get("city", "").strip()
        if not name or not email or len(password) < 8 or not cuisine or not city:
            return json_response(False, "All fields are required and the password must have at least 8 characters.", status=400)
        if User.query.filter_by(email=email).first():
            return json_response(False, "Email already exists. Please log in.", status=400)
        restaurant = User(name=name, email=email, is_restaurant=True, cuisine=cuisine, city=city)
        restaurant.set_password(password)
        db.session.add(restaurant)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return json_response(False, "Email already exists. Please log in.", status=400)
        login_user(restaurant)
        return json_response(True, "Restaurant registered successfully.", next=url_for("restaurant_dashboard"))

    @app.route("/api/restaurant/payout", methods=["POST"])
    @login_required
    def api_request_payout():
        if not current_user.is_restaurant:
            return json_response(False, "Restaurant access is required.", status=403)
        summary = payout_summary(current_user.id, Order, Payout)
        if summary["available"] <= 0:
            return json_response(False, "There is no available balance to pay out yet.", status=400)
        payout = build_payout(current_user.id, summary, Payout)
        db.session.add(payout)
        db.session.commit()
        return json_response(
            True,
            "Payout request submitted successfully.",
            payout_id=payout.id,
            amount=payout.amount,
            status=payout.status,
            payment_reference=payout.payment_reference,
        )

    @app.route("/api/restaurant/payouts")
    @login_required
    def api_payouts():
        if not current_user.is_restaurant:
            return json_response(False, "Restaurant access is required.", status=403)
        payouts = Payout.query.filter_by(restaurant_id=current_user.id).order_by(Payout.requested_at.desc()).all()
        return {
            "success": True,
            "balance": payout_summary(current_user.id, Order, Payout),
            "payouts": [{
                "id": payout.id,
                "amount": payout.amount,
                "gross_amount": payout.gross_amount,
                "platform_fee": payout.platform_fee,
                "status": payout.status,
                "payment_reference": payout.payment_reference,
                "requested_at": payout.requested_at.isoformat() if payout.requested_at else None,
            } for payout in payouts],
        }

    @app.route("/restaurant/logout")
    @login_required
    def restaurant_logout():

        logout_user()

        flash("Logged out successfully.", "success")

        return redirect(url_for("restaurant_login"))
    
    @app.route("/restaurant/profile")
    @login_required
    def restaurant_profile():

        if not current_user.is_restaurant:
            return redirect(url_for("home"))

        return render_template(
            "admin/profile.html",
            restaurant=current_user
        )