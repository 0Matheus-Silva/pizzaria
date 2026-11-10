from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models import Category, CustomerAddress, Product, ProductSize, Promotion, StoreSettings, User
from app.services import CommerceError, create_order, price_cart, quote_order


def make_product():
    category = Category(name="Tradicionais", slug="tradicionais")
    product = Product(
        name="Margherita",
        category=category,
        description="Tomate, queijo e manjericão.",
    )
    size = ProductSize(name="Grande", price=Decimal("40.00"), slices=8)
    product.sizes.append(size)
    db.session.add(product)
    db.session.commit()
    return product, size


def test_home_and_menu_render(client, app):
    with app.app_context():
        make_product()
    assert client.get("/").status_code == 200
    assert b"Margherita" in client.get("/cardapio").data


def test_inactive_product_cannot_be_priced(app):
    with app.app_context():
        product, size = make_product()
        product.is_active = False
        db.session.commit()
        try:
            price_cart([{
                "product_id": product.id,
                "size_id": size.id,
                "quantity": 1,
            }])
        except CommerceError as error:
            assert "indisponível" in str(error)
        else:
            raise AssertionError("Inactive product was accepted")


def test_valid_promotion_is_recalculated_server_side(app):
    with app.app_context():
        product, size = make_product()
        user = User(name="Cliente", email="promotion@example.com", phone="11999999999")
        user.set_password("senha-muito-segura-123")
        db.session.add(user)
        promotion = Promotion(
            product_id=product.id,
            title="Oferta da casa",
            promotional_price=Decimal("35.00"),
            starts_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
            is_active=True,
        )
        db.session.add_all([promotion, StoreSettings(is_open=True, accepts_pickup=True)])
        db.session.commit()
        quote = quote_order(
            user=user,
            cart=[{"product_id": product.id, "size_id": size.id, "quantity": 1}],
            order_type="pickup",
            payment_method="cash",
            address_id=None,
            change_for=None,
        )
        assert quote.subtotal == Decimal("40.00")
        assert quote.discount == Decimal("5.00")
        assert quote.total == Decimal("35.00")


def test_pickup_checkout_uses_server_price_and_keeps_snapshot(app, client):
    with app.app_context():
        product, size = make_product()
        user = User(name="Cliente Exemplo", email="cliente@example.com", phone="11999999999")
        user.set_password("senha-muito-segura-123")
        db.session.add(user)
        db.session.add(StoreSettings(is_open=True, accepts_pickup=True, accepts_card=True))
        db.session.commit()
        user_id, product_id, size_id = user.id, product.id, size.id

    login = client.post("/conta/entrar", data={
        "email": "cliente@example.com",
        "password": "senha-muito-segura-123",
    }, follow_redirects=True)
    assert login.status_code == 200

    with client.session_transaction() as browser_session:
        browser_session["cart"] = [{
            "product_id": product_id,
            "size_id": size_id,
            "quantity": 2,
            "addon_ids": [],
            "observation": "",
            "price": "0.01",
        }]
    preview = client.post("/pedido/checkout", data={
        "order_type": "pickup",
        "address_id": 0,
        "payment_method": "card",
    })
    assert preview.status_code == 302
    review = client.get(preview.headers["Location"])
    assert review.status_code == 200
    assert b"R$ 80,00" in review.data
    review_url = preview.headers["Location"]
    response = client.post(review_url, data={"confirm": "y"})
    assert response.status_code == 302
    assert "/minha-conta/pedido/" in response.headers["Location"]
    duplicate = client.post(review_url, data={"confirm": "y"})
    assert duplicate.status_code == 302
    with app.app_context():
        from app.models import Order

        order = Order.query.filter_by(user_id=user_id).one()
        assert order.total == Decimal("80.00")
        assert order.items[0].product_name == "Margherita"
        assert order.items[0].quantity == 2


def test_checkout_requires_review_when_price_changes(app, client):
    with app.app_context():
        product, size = make_product()
        user = User(name="Cliente", email="change@example.com", phone="11999999999")
        user.set_password("senha-muito-segura-123")
        db.session.add_all([user, StoreSettings(is_open=True, accepts_pickup=True, accepts_card=True)])
        db.session.commit()
        product_id, size_id = product.id, size.id

    client.post("/conta/entrar", data={
        "email": "change@example.com",
        "password": "senha-muito-segura-123",
    })
    with client.session_transaction() as browser_session:
        browser_session["cart"] = [{
            "product_id": product_id,
            "size_id": size_id,
            "quantity": 1,
            "addon_ids": [],
            "observation": "",
        }]
    preview = client.post("/pedido/checkout", data={
        "order_type": "pickup",
        "address_id": 0,
        "payment_method": "card",
    })
    with app.app_context():
        db.session.get(ProductSize, size_id).price = Decimal("45.00")
        db.session.commit()
    response = client.post(preview.headers["Location"], data={"confirm": "y"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/pedido/checkout")
    with app.app_context():
        from app.models import Order

        assert Order.query.count() == 0


def test_delivery_rejects_unserved_neighborhood(app):
    with app.app_context():
        product, size = make_product()
        user = User(name="Cliente", email="delivery@example.com", phone="11999999999")
        user.set_password("senha-muito-segura-123")
        address = CustomerAddress(
            user=user,
            label="Casa",
            postal_code="01000-000",
            street="Rua Um",
            number="10",
            neighborhood="Bairro fora da área",
            city="São Paulo",
            state="SP",
        )
        db.session.add_all([user, address, StoreSettings(is_open=True)])
        db.session.commit()
        try:
            create_order(
                user=user,
                cart=[{"product_id": product.id, "size_id": size.id, "quantity": 1}],
                order_type="delivery",
                payment_method="cash",
                address_id=address.id,
                customer_note="",
                change_for=None,
                idempotency_key="test-delivery-key",
            )
        except CommerceError as error:
            assert "não atendemos" in str(error)
        else:
            raise AssertionError("Unserved delivery zone was accepted")


def test_customer_cannot_open_admin_dashboard(client):
    response = client.post("/conta/cadastro", data={
        "name": "Cliente",
        "email": "user@example.com",
        "phone": "11999999999",
        "password": "senha-muito-segura-123",
        "confirm_password": "senha-muito-segura-123",
        "terms": "y",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert client.get("/admin/").status_code == 403


def test_csrf_rejects_post_without_token():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SECRET_KEY": "csrf-test-key-with-sufficient-length",
    })
    with application.app_context():
        db.create_all()
    try:
        response = application.test_client().post("/conta/cadastro", data={
            "name": "Cliente",
            "email": "csrf@example.com",
            "phone": "11999999999",
            "password": "senha-muito-segura-123",
            "confirm_password": "senha-muito-segura-123",
            "terms": "y",
        })
        assert response.status_code == 400
    finally:
        with application.app_context():
            db.session.remove()
            db.drop_all()


def test_production_requires_secret_and_uses_secure_cookies(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
    monkeypatch.setenv("SECRET_KEY", "production-secret-for-test-only")
    application = create_app()
    assert application.config["SESSION_COOKIE_SECURE"] is True
