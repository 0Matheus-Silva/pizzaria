from __future__ import annotations

import os
from getpass import getpass
from decimal import Decimal

import click
from dotenv import load_dotenv
from flask import Flask, render_template

from app.extensions import csrf, db, login_manager, migrate


def create_app(test_config: dict | None = None) -> Flask:
    if os.getenv("APP_ENV") != "production":
        load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object("config.Config")
    app.config["APP_ENV"] = os.getenv("APP_ENV", "development")
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
            ("Margherita", "margherita", "tradicionais", "Molho de tomate, mozzarella fresca e manjericão.", "Tomate, mozzarella e manjericão", "Grande", Decimal("39.90"), 8),
            ("Calabresa", "calabresa", "tradicionais", "Calabresa artesanal, cebola e mozzarella.", "Calabresa, cebola e mozzarella", "Grande", Decimal("42.90"), 8),
            ("Muçarela", "mucarela", "tradicionais", "Molho de tomate coberto com mozzarella derretida.", "Tomate, mozzarella e orégano", "Grande", Decimal("39.90"), 8),
            ("Napolitana", "napolitana", "tradicionais", "Mozzarella, rodelas de tomate e parmesão.", "Tomate, mozzarella, parmesão e orégano", "Grande", Decimal("43.90"), 8),
            ("Quatro Queijos", "quatro-queijos", "especiais", "Uma combinação cremosa de queijos selecionados.", "Mozzarella, provolone, gorgonzola e parmesão", "Grande", Decimal("49.90"), 8),
            ("Portuguesa", "portuguesa", "especiais", "Um clássico generoso e cheio de sabor.", "Presunto, ovo, cebola, ervilha e mozzarella", "Grande", Decimal("47.90"), 8),
            ("Frango com Catupiry", "frango-catupiry", "especiais", "Frango desfiado com catupiry cremoso.", "Frango, catupiry e mozzarella", "Grande", Decimal("48.90"), 8),
            ("Bacon", "bacon", "especiais", "Bacon crocante com mozzarella e toque de orégano.", "Bacon, mozzarella e orégano", "Grande", Decimal("46.90"), 8),
            ("Vegetariana", "vegetariana", "vegetarianas", "Legumes frescos e mozzarella sobre molho da casa.", "Abobrinha, champignon, tomate, azeitona e mozzarella", "Grande", Decimal("46.90"), 8),
            ("Brócolis com Catupiry", "brocolis-catupiry", "vegetarianas", "Brócolis temperado com catupiry cremoso.", "Brócolis, catupiry e mozzarella", "Grande", Decimal("47.90"), 8),
            ("Chocolate", "chocolate", "doces", "Chocolate ao leite derretido sobre massa artesanal.", "Chocolate ao leite e chocolate granulado", "Grande", Decimal("45.90"), 8),
            ("Banana com Canela", "banana-canela", "doces", "Banana, açúcar e canela em uma combinação clássica.", "Banana, açúcar, canela e mozzarella", "Grande", Decimal("43.90"), 8),
            ("Refrigerante Cola", "refrigerante-cola", "bebidas", "Refrigerante sabor cola, servido gelado.", "Refrigerante", "2 litros", Decimal("14.00"), 0),
            ("Refrigerante Guaraná", "refrigerante-guarana", "bebidas", "Refrigerante sabor guaraná, servido gelado.", "Refrigerante", "2 litros", Decimal("13.00"), 0),
            ("Refrigerante Laranja", "refrigerante-laranja", "bebidas", "Refrigerante sabor laranja, servido gelado.", "Refrigerante", "2 litros", Decimal("13.00"), 0),
            ("Refrigerante Cola Lata", "cola-lata", "bebidas", "Lata de refrigerante sabor cola, servida gelada.", "Refrigerante", "350 ml", Decimal("6.00"), 0),
            ("Água Mineral", "agua-mineral", "bebidas", "Água mineral sem gás.", "Água mineral", "500 ml", Decimal("4.00"), 0),
            ("Suco de Laranja", "suco-laranja", "bebidas", "Suco de laranja pronto para beber.", "Suco de laranja", "1 litro", Decimal("12.00"), 0),
        ]
        for name, image_key, slug, description, ingredients, size_name, price, slices in demo_products:
            product = Product.query.filter_by(name=name).first()
            if product is None:
                product = Product(
                    name=name,
                    category=categories[slug],
                    description=description,
                    ingredients=ingredients,
                    image_url=f"sprite:{image_key}",
                    is_featured=name in {"Margherita", "Calabresa"},
                )
                db.session.add(product)
                db.session.flush()
            elif not product.image_url:
                product.image_url = f"sprite:{image_key}"
            if not ProductSize.query.filter_by(product_id=product.id, name=size_name).first():
                db.session.add(ProductSize(
                    product_id=product.id, name=size_name, price=price, slices=slices
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
