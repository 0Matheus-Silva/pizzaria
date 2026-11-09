from __future__ import annotations

import os
from getpass import getpass
from decimal import Decimal

import click
from dotenv import load_dotenv
from flask import Flask, render_template

from app.extensions import csrf, db, login_manager, migrate


def create_app(test_config: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config.Config")
    if test_config:
        app.config.update(test_config)
    if os.getenv("APP_ENV") == "production":
        if not os.getenv("SECRET_KEY"):
            raise RuntimeError("Defina SECRET_KEY antes de iniciar em produção.")
        app.config["SESSION_COOKIE_SECURE"] = True
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)

    from app import models
    from app.routes import admin_bp, auth_bp, customer_bp, main_bp, shop_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/conta")
    app.register_blueprint(shop_bp, url_prefix="/pedido")
    app.register_blueprint(customer_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(models.User, int(user_id))

    @app.errorhandler(404)
    def not_found(error):
        del error
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(error):
        del error
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        app.logger.error("Internal server error: %s", type(error).__name__)
        return render_template("errors/500.html"), 500

    @app.cli.command("init-db")
    def init_db() -> None:
        """Create tables for local development; use migrations in deployment."""
        db.create_all()
        click.echo("Estrutura local do banco criada.")

    @app.cli.command("create-admin")
    def create_admin() -> None:
        """Interactively create the first administrator without logging credentials."""
        from app.models import User

        name = click.prompt("Nome")
        email = click.prompt("E-mail").strip().lower()
        password = getpass("Senha (mínimo de 12 caracteres): ")
        if len(password) < 12:
            raise click.ClickException("A senha precisa ter pelo menos 12 caracteres.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("Já existe uma conta com esse e-mail.")
        user = User(name=name, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo("Administrador criado.")

    @app.cli.command("seed-demo")
    def seed_demo() -> None:
        """Create editable demonstration catalog and store settings."""
        from app.models import Addon, Category, DeliveryZone, Product, ProductSize, StoreSettings

        categories = {}
        for name, slug in (
            ("Pizzas tradicionais", "tradicionais"),
            ("Pizzas especiais", "especiais"),
            ("Pizzas vegetarianas", "vegetarianas"),
            ("Pizzas doces", "doces"),
            ("Bebidas", "bebidas"),
            ("Combos", "combos"),
        ):
            category = Category.query.filter_by(slug=slug).first()
            if category is None:
                category = Category(name=name, slug=slug)
                db.session.add(category)
            categories[slug] = category
        db.session.flush()
        demo_products = [
            ("Margherita", "tradicionais", "Molho de tomate, mozzarella fresca e manjericão.", "Tomate, mozzarella e manjericão", Decimal("39.90")),
            ("Calabresa", "tradicionais", "Calabresa artesanal, cebola e mozzarella.", "Calabresa, cebola e mozzarella", Decimal("42.90")),
            ("Quatro Queijos", "especiais", "Uma combinação cremosa de queijos selecionados.", "Mozzarella, provolone, gorgonzola e parmesão", Decimal("49.90")),
            ("Portuguesa", "especiais", "Um clássico generoso e cheio de sabor.", "Presunto, ovo, cebola, ervilha e mozzarella", Decimal("47.90")),
        ]
        for name, slug, description, ingredients, price in demo_products:
            product = Product.query.filter_by(name=name).first()
            if product is None:
                product = Product(
                    name=name,
                    category=categories[slug],
                    description=description,
                    ingredients=ingredients,
                    is_featured=name in {"Margherita", "Calabresa"},
                )
                db.session.add(product)
                db.session.flush()
                db.session.add(ProductSize(
                    product_id=product.id, name="Grande", price=price, slices=8
                ))
        addon = Addon.query.filter_by(name="Queijo extra").first()
        if addon is None:
            addon = Addon(name="Queijo extra", price=Decimal("6.00"))
            db.session.add(addon)
        db.session.flush()
        for name in ("Margherita", "Calabresa", "Quatro Queijos", "Portuguesa"):
            product = Product.query.filter_by(name=name).first()
            if product and addon not in product.addons:
                product.addons.append(addon)
        if not StoreSettings.query.first():
            db.session.add(StoreSettings(store_name=os.getenv("STORE_NAME", "Bella Pizza")))
        if not DeliveryZone.query.first():
            db.session.add(DeliveryZone(
                neighborhood="Centro", delivery_fee=Decimal("7.00")
            ))
        db.session.commit()
        click.echo("Catálogo demonstrativo criado. Revise preços, bairros e dados comerciais.")

    return app
