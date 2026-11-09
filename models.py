from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


product_addons = db.Table(
    "product_addons",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id"), primary_key=True),
    db.Column("addon_id", db.Integer, db.ForeignKey("addons.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, index=True, nullable=False)
    phone = db.Column(db.String(30), nullable=False, default="")
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    addresses = db.relationship("CustomerAddress", back_populates="user", cascade="all, delete-orphan")
    orders = db.relationship("Order", back_populates="user")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class CustomerAddress(db.Model):
    __tablename__ = "customer_addresses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    label = db.Column(db.String(50), nullable=False)
    postal_code = db.Column(db.String(9), nullable=False)
    street = db.Column(db.String(160), nullable=False)
    number = db.Column(db.String(20), nullable=False)
    complement = db.Column(db.String(100))
    neighborhood = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(2), nullable=False)
    reference = db.Column(db.String(160))
    user = db.relationship("User", back_populates="addresses")


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(90), unique=True, nullable=False)
    description = db.Column(db.String(250), nullable=False, default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    display_order = db.Column(db.Integer, nullable=False, default=0)
    products = db.relationship("Product", back_populates="category")


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    ingredients = db.Column(db.Text, nullable=False, default="")
    image_url = db.Column(db.String(500), nullable=False, default="")
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    category = db.relationship("Category", back_populates="products")
    sizes = db.relationship("ProductSize", back_populates="product", cascade="all, delete-orphan")
    addons = db.relationship("Addon", secondary=product_addons, back_populates="products")
    promotions = db.relationship("Promotion", back_populates="product", cascade="all, delete-orphan")


class ProductSize(db.Model):
    __tablename__ = "product_sizes"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    name = db.Column(db.String(40), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    slices = db.Column(db.Integer, nullable=False, default=8)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    product = db.relationship("Product", back_populates="sizes")
    __table_args__ = (db.UniqueConstraint("product_id", "name"),)


class Addon(db.Model):
    __tablename__ = "addons"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    products = db.relationship("Product", secondary=product_addons, back_populates="addons")


class Promotion(db.Model):
    __tablename__ = "promotions"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    promotional_price = db.Column(db.Numeric(10, 2), nullable=False)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=False)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    product = db.relationship("Product", back_populates="promotions")


class DeliveryZone(db.Model):
    __tablename__ = "delivery_zones"

    id = db.Column(db.Integer, primary_key=True)
    neighborhood = db.Column(db.String(100), unique=True, nullable=False)
    delivery_fee = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class StoreSettings(db.Model):
    __tablename__ = "store_settings"

    id = db.Column(db.Integer, primary_key=True, default=1)
    store_name = db.Column(db.String(100), nullable=False, default="Bella Pizza")
    phone = db.Column(db.String(30), nullable=False, default="")
    whatsapp = db.Column(db.String(30), nullable=False, default="")
    address = db.Column(db.String(250), nullable=False, default="")
    opening_hours = db.Column(db.String(250), nullable=False, default="Todos os dias, das 18h às 23h")
    is_open = db.Column(db.Boolean, nullable=False, default=True)
    accepts_pickup = db.Column(db.Boolean, nullable=False, default=True)
    accepts_pix = db.Column(db.Boolean, nullable=False, default=True)
    accepts_cash = db.Column(db.Boolean, nullable=False, default=True)
    accepts_card = db.Column(db.Boolean, nullable=False, default=True)
    pix_key = db.Column(db.String(180), nullable=False, default="")
    pix_instructions = db.Column(db.String(300), nullable=False, default="")


class Order(db.Model):
    __tablename__ = "orders"
    __table_args__ = (db.Index("uq_orders_checkout_key", "checkout_key", unique=True),)

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(16), unique=True, nullable=False, index=True)
    checkout_key = db.Column(db.String(64), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    order_type = db.Column(db.String(12), nullable=False, default="delivery")
    status = db.Column(db.String(32), nullable=False, default="awaiting_confirmation", index=True)
    payment_method = db.Column(db.String(20), nullable=False)
    payment_status = db.Column(db.String(20), nullable=False, default="pending")
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    discount = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    delivery_fee = db.Column(db.Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    total = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_snapshot = db.Column(db.Text, nullable=False, default="")
    customer_note = db.Column(db.String(500), nullable=False, default="")
    change_for = db.Column(db.Numeric(10, 2))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    user = db.relationship("User", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    history = db.relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan", order_by="OrderStatusHistory.created_at")
    payment = db.relationship("Payment", back_populates="order", uselist=False, cascade="all, delete-orphan")


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    product_name = db.Column(db.String(120), nullable=False)
    size_name = db.Column(db.String(40), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    observation = db.Column(db.String(250), nullable=False, default="")
    order = db.relationship("Order", back_populates="items")
    addons = db.relationship("OrderItemAddon", back_populates="order_item", cascade="all, delete-orphan")


class OrderItemAddon(db.Model):
    __tablename__ = "order_item_addons"

    id = db.Column(db.Integer, primary_key=True)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_items.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    order_item = db.relationship("OrderItem", back_populates="addons")


class OrderStatusHistory(db.Model):
    __tablename__ = "order_status_history"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    note = db.Column(db.String(250), nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    order = db.relationship("Order", back_populates="history")


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), unique=True, nullable=False)
    method = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    confirmed_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    confirmed_at = db.Column(db.DateTime(timezone=True))
    order = db.relationship("Order", back_populates="payment")


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    message = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
