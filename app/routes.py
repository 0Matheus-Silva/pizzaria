from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import wraps
from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.forms import (
    AddressForm,
    CheckoutConfirmForm,
    ContactForm,
    EmptyForm,
    LoginForm,
    ProductForm,
    RegistrationForm,
    StatusForm,
    CheckoutForm,
)
from app.models import (
    AuditLog,
    Category,
    ContactMessage,
    CustomerAddress,
    DeliveryZone,
    Order,
    Product,
    ProductSize,
    StoreSettings,
    User,
)
from app.services import (
    ALLOWED_TRANSITIONS,
    CommerceError,
    change_order_status,
    confirm_payment,
    create_order,
    price_cart,
    quote_order,
)

main_bp = Blueprint("main", __name__)
auth_bp = Blueprint("auth", __name__)
shop_bp = Blueprint("shop", __name__)
admin_bp = Blueprint("admin", __name__)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role not in {"admin", "manager", "attendant"}:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def cart_items() -> list[dict]:
    cart = session.get("cart", [])
    return cart if isinstance(cart, list) else []


def cart_count() -> int:
    return sum(int(item.get("quantity", 0)) for item in cart_items())


def cart_fingerprint(cart: list[dict]) -> str:
    encoded = json.dumps(cart, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@main_bp.app_context_processor
def inject_store_and_cart():
    return {
        "store": StoreSettings.query.first(),
        "cart_count": cart_count(),
        "money": lambda amount: f"R$ {Decimal(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "status_labels": {
            "awaiting_confirmation": "Aguardando confirmação",
            "awaiting_payment": "Aguardando pagamento",
            "payment_confirmed": "Pagamento confirmado",
            "received": "Pedido recebido",
            "preparing": "Em preparação",
            "out_for_delivery": "Saiu para entrega",
            "ready_for_pickup": "Disponível para retirada",
            "completed": "Concluído",
            "cancelled": "Cancelado",
        },
    }


@main_bp.route("/")
def home():
    products = Product.query.filter_by(is_active=True, is_available=True).order_by(
        Product.is_featured.desc(), Product.name
    ).limit(6).all()
    categories = Category.query.filter_by(is_active=True).order_by(Category.display_order).all()
    return render_template("main/home.html", products=products, categories=categories)


@main_bp.route("/cardapio")
def menu():
    category_id = request.args.get("categoria", type=int)
    search = request.args.get("q", "").strip()[:100]
    query = Product.query.filter_by(is_active=True, is_available=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        query = query.filter(
            Product.name.ilike(f"%{search}%")
            | Product.description.ilike(f"%{search}%")
        )
    products = query.order_by(Product.is_featured.desc(), Product.name).all()
    return render_template(
        "catalog/menu.html",
        products=products,
        categories=Category.query.filter_by(is_active=True).order_by(Category.display_order).all(),
        selected_category=category_id,
        search=search,
    )


@main_bp.route("/produto/<int:product_id>")
def product_detail(product_id: int):
    product = Product.query.filter_by(id=product_id, is_active=True, is_available=True).first_or_404()
    sizes = [size for size in product.sizes if size.is_available]
    return render_template("catalog/product.html", product=product, sizes=sizes)


@main_bp.route("/sobre")
def about():
    return render_template("main/about.html")


@main_bp.route("/termos")
def terms():
    return render_template("main/terms.html")


@main_bp.route("/privacidade")
def privacy():
    return render_template("main/privacy.html")


@main_bp.route("/contato", methods=["GET", "POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        message = form.message.data.strip()
        recent_duplicate = ContactMessage.query.filter_by(
            email=email, message=message
        ).filter(
            ContactMessage.created_at >= datetime.now(timezone.utc) - timedelta(minutes=2)
        ).first()
        if recent_duplicate:
            flash("Esta mensagem foi recebida recentemente. Aguarde antes de reenviar.", "info")
            return redirect(url_for("main.contact"))
        db.session.add(ContactMessage(
            name=form.name.data.strip(),
            email=email,
            message=message,
        ))
        db.session.commit()
        flash("Mensagem enviada. Obrigado por entrar em contato!", "success")
        return redirect(url_for("main.contact"))
    return render_template("main/contact.html", form=form)


@auth_bp.route("/cadastro", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            form.email.errors.append("Este e-mail já está cadastrado.")
        else:
            user = User(
                name=form.name.data.strip(),
                email=email,
                phone=form.phone.data.strip(),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Conta criada com sucesso.", "success")
            return redirect(url_for("customer.account"))
    return render_template("auth/register.html", form=form)


@auth_bp.route("/entrar", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        now = datetime.now(timezone.utc)
        locked = False
        if user and user.locked_until:
            lock_time = user.locked_until
            if lock_time.tzinfo is None:
                lock_time = lock_time.replace(tzinfo=timezone.utc)
            locked = lock_time > now
        if user and user.is_active and not locked and user.check_password(form.password.data):
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()
            login_user(user, remember=False, fresh=True)
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("customer.account"))
        if user and not locked:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.failed_login_attempts = 0
                user.locked_until = now + timedelta(minutes=15)
            db.session.commit()
        flash("E-mail ou senha incorretos, ou conta temporariamente indisponível.", "error")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/sair", methods=["POST"])
@login_required
def logout():
    form = EmptyForm()
    if form.validate_on_submit():
        logout_user()
        session.pop("cart", None)
        flash("Você saiu da sua conta.", "success")
    return redirect(url_for("main.home"))


@shop_bp.route("/carrinho")
def cart():
    try:
        lines = price_cart(cart_items())
    except CommerceError as error:
        flash(str(error), "error")
        lines = []
    return render_template("cart/cart.html", lines=lines)


@shop_bp.route("/adicionar/<int:product_id>", methods=["POST"])
def add_to_cart(product_id: int):
    from app.forms import EmptyForm
    form = EmptyForm()
    if not form.validate_on_submit():
        abort(400)
    product = Product.query.filter_by(id=product_id, is_active=True, is_available=True).first_or_404()
    size_id = request.form.get("size_id", type=int)
    size = ProductSize.query.filter_by(id=size_id, product_id=product.id, is_available=True).first()
    if size is None:
        flash("Selecione um tamanho disponível.", "error")
        return redirect(url_for("main.product_detail", product_id=product.id))
    addon_ids = sorted({int(value) for value in request.form.getlist("addon_ids") if value.isdigit()})
    observation = request.form.get("observation", "").strip()[:250]
    quantity = request.form.get("quantity", 1, type=int)
    item = {
        "product_id": product.id,
        "size_id": size.id,
        "addon_ids": addon_ids,
        "quantity": quantity,
        "observation": observation,
    }
    try:
        price_cart([item])
    except CommerceError as error:
        flash(str(error), "error")
        return redirect(url_for("main.product_detail", product_id=product.id))
    cart_data = cart_items()
    cart_data.append(item)
    session["cart"] = cart_data
    flash("Produto adicionado ao carrinho.", "success")
    return redirect(url_for("shop.cart"))


@shop_bp.route("/atualizar/<int:index>", methods=["POST"])
def update_cart(index: int):
    from app.forms import EmptyForm
    form = EmptyForm()
    cart_data = cart_items()
    if not form.validate_on_submit() or not 0 <= index < len(cart_data):
        abort(400)
    quantity = request.form.get("quantity", type=int)
    if quantity is None or not 1 <= quantity <= 20:
        flash("A quantidade deve ficar entre 1 e 20.", "error")
    else:
        cart_data[index]["quantity"] = quantity
        session["cart"] = cart_data
        flash("Quantidade atualizada.", "success")
    return redirect(url_for("shop.cart"))


@shop_bp.route("/remover/<int:index>", methods=["POST"])
def remove_from_cart(index: int):
    from app.forms import EmptyForm
    form = EmptyForm()
    cart_data = cart_items()
    if not form.validate_on_submit() or not 0 <= index < len(cart_data):
        abort(400)
    cart_data.pop(index)
    session["cart"] = cart_data
    return redirect(url_for("shop.cart"))


@shop_bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart_data = cart_items()
    try:
        lines = price_cart(cart_data)
    except CommerceError as error:
        flash(str(error), "error")
        session["cart"] = []
        return redirect(url_for("shop.cart"))
    if not lines:
        flash("Adicione produtos antes de finalizar.", "info")
        return redirect(url_for("shop.cart"))
    form = CheckoutForm()
    form.address_id.choices = [(0, "Selecione um endereço")] + [
        (address.id, f"{address.label} — {address.street}, {address.number}, {address.neighborhood}")
        for address in current_user.addresses
    ]
    settings = StoreSettings.query.first()
    form.payment_method.choices = [
        (key, label)
        for key, label, enabled in (
            ("pix", "Pix manual", settings.accepts_pix if settings else True),
            ("cash", "Dinheiro na entrega", settings.accepts_cash if settings else True),
            ("card", "Cartão na entrega", settings.accepts_card if settings else True),
        )
        if enabled
    ]
    if form.validate_on_submit():
        address_id = form.address_id.data or None
        try:
            quote = quote_order(
                user=current_user,
                cart=cart_data,
                order_type=form.order_type.data,
                payment_method=form.payment_method.data,
                address_id=address_id,
                change_for=form.change_for.data,
            )
        except CommerceError as error:
            flash(str(error), "error")
            return render_template(
                "checkout/checkout.html",
                form=form,
                lines=lines,
                subtotal=sum((line.total for line in lines), Decimal("0.00")),
                zones=DeliveryZone.query.filter_by(is_active=True).all(),
                settings=settings,
            )
        session["checkout_review"] = {
            "checkout_key": uuid4().hex,
            "cart_fingerprint": cart_fingerprint(cart_data),
            "order_type": form.order_type.data,
            "payment_method": form.payment_method.data,
            "address_id": address_id,
            "customer_note": (form.customer_note.data or "")[:500],
            "change_for": str(form.change_for.data) if form.change_for.data is not None else None,
            "expected_total": str(quote.total),
        }
        return redirect(url_for("shop.review_checkout"))
    subtotal = sum((line.total for line in lines), Decimal("0.00"))
    return render_template(
        "checkout/checkout.html",
        form=form,
        lines=lines,
        subtotal=subtotal,
        zones=DeliveryZone.query.filter_by(is_active=True).all(),
        settings=settings,
    )


@shop_bp.route("/checkout/revisar", methods=["GET", "POST"])
@login_required
def review_checkout():
    review = session.get("checkout_review")
    cart_data = cart_items()
    if not review:
        flash("Revise os dados de entrega antes de confirmar.", "info")
        return redirect(url_for("shop.checkout"))
    if review["cart_fingerprint"] != cart_fingerprint(cart_data):
        session.pop("checkout_review", None)
        flash("O carrinho mudou. Confira novamente os valores.", "error")
        return redirect(url_for("shop.checkout"))
    try:
        quote = quote_order(
            user=current_user,
            cart=cart_data,
            order_type=review["order_type"],
            payment_method=review["payment_method"],
            address_id=review["address_id"],
            change_for=Decimal(review["change_for"]) if review["change_for"] else None,
        )
    except CommerceError as error:
        session.pop("checkout_review", None)
        flash(str(error), "error")
        return redirect(url_for("shop.checkout"))
    if quote.total != Decimal(review["expected_total"]):
        session.pop("checkout_review", None)
        flash("O preço ou a taxa mudou. Revise os valores atualizados.", "error")
        return redirect(url_for("shop.checkout"))

    form = CheckoutConfirmForm()
    if form.validate_on_submit():
        existing_order = Order.query.filter_by(
            checkout_key=review["checkout_key"],
            user_id=current_user.id,
        ).first()
        if existing_order:
            session["cart"] = []
            session.pop("checkout_review", None)
            return redirect(url_for("customer.order_detail", public_id=existing_order.public_id))
        try:
            order = create_order(
                user=current_user,
                cart=cart_data,
                order_type=review["order_type"],
                payment_method=review["payment_method"],
                address_id=review["address_id"],
                customer_note=review["customer_note"],
                change_for=Decimal(review["change_for"]) if review["change_for"] else None,
                idempotency_key=review["checkout_key"],
                expected_total=Decimal(review["expected_total"]),
            )
            db.session.add(AuditLog(
                actor_id=current_user.id,
                action="order_created",
                entity_type="Order",
                entity_id=order.public_id,
            ))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            order = Order.query.filter_by(
                checkout_key=review["checkout_key"],
                user_id=current_user.id,
            ).first()
            if order is None:
                current_app.logger.exception("Conflito ao registrar pedido idempotente")
                flash("Não foi possível registrar o pedido. Tente novamente.", "error")
                return redirect(url_for("shop.checkout"))
        except CommerceError as error:
            db.session.rollback()
            session.pop("checkout_review", None)
            flash(str(error), "error")
            return redirect(url_for("shop.checkout"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Falha ao registrar pedido")
            flash("Não foi possível registrar o pedido. Tente novamente.", "error")
            return redirect(url_for("shop.checkout"))
        session["cart"] = []
        session.pop("checkout_review", None)
        return redirect(url_for("customer.order_detail", public_id=order.public_id))
    return render_template(
        "checkout/review.html",
        form=form,
        quote=quote,
        order_type=review["order_type"],
        payment_method=review["payment_method"],
        customer_note=review["customer_note"],
        change_for=review["change_for"],
        address=quote.delivery_snapshot,
        settings=StoreSettings.query.first(),
    )


@shop_bp.route("/pedido/<public_id>")
@login_required
def track_order(public_id: str):
    return redirect(url_for("customer.order_detail", public_id=public_id))


customer_bp = Blueprint("customer", __name__, url_prefix="/minha-conta")


@customer_bp.route("/")
@login_required
def account():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(10).all()
    return render_template("customer/account.html", orders=orders)


@customer_bp.route("/enderecos", methods=["GET", "POST"])
@login_required
def addresses():
    form = AddressForm()
    if form.validate_on_submit():
        address = CustomerAddress(
            user_id=current_user.id,
            label=form.label.data.strip(),
            postal_code=form.postal_code.data.strip(),
            street=form.street.data.strip(),
            number=form.number.data.strip(),
            complement=(form.complement.data or "").strip(),
            neighborhood=form.neighborhood.data.strip(),
            city=form.city.data.strip(),
            state=form.state.data.strip().upper(),
            reference=(form.reference.data or "").strip(),
        )
        db.session.add(address)
        db.session.commit()
        flash("Endereço salvo.", "success")
        return redirect(url_for("customer.addresses"))
    return render_template("customer/addresses.html", form=form, addresses=current_user.addresses)


@customer_bp.route("/pedido/<public_id>")
@login_required
def order_detail(public_id: str):
    order = Order.query.filter_by(public_id=public_id, user_id=current_user.id).first_or_404()
    return render_template("customer/order_detail.html", order=order)


admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@admin_required
def dashboard():
    today = datetime.now(timezone.utc).date()
    today_orders = Order.query.filter(func.date(Order.created_at) == today).all()
    revenue = sum(
        (Decimal(order.total) for order in today_orders if order.payment_status == "confirmed"),
        Decimal("0.00"),
    )
    return render_template(
        "admin/dashboard.html",
        orders_today=len(today_orders),
        revenue=revenue,
        pending=Order.query.filter(Order.status.in_(["awaiting_confirmation", "awaiting_payment"])).count(),
        active_products=Product.query.filter_by(is_active=True).count(),
        latest_orders=Order.query.order_by(Order.created_at.desc()).limit(10).all(),
    )


@admin_bp.route("/produtos", methods=["GET", "POST"])
@admin_required
def products():
    form = ProductForm()
    categories = Category.query.order_by(Category.name).all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    if form.validate_on_submit():
        product = Product(
            name=form.name.data.strip(),
            description=(form.description.data or "").strip(),
            ingredients=(form.ingredients.data or "").strip(),
            category_id=form.category_id.data,
            image_url=(form.image_url.data or "").strip(),
            is_available=form.is_available.data,
            is_featured=form.is_featured.data,
        )
        db.session.add(product)
        db.session.flush()
        db.session.add(ProductSize(
            product_id=product.id,
            name=form.size_name.data.strip(),
            price=form.price.data,
        ))
        db.session.add(AuditLog(
            actor_id=current_user.id,
            action="product_created",
            entity_type="Product",
            entity_id=str(product.id),
        ))
        db.session.commit()
        flash("Produto cadastrado.", "success")
        return redirect(url_for("admin.products"))
    product_list = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html", form=form, products=product_list)


@admin_bp.route("/produto/<int:product_id>/alternar", methods=["POST"])
@admin_required
def toggle_product(product_id: int):
    from app.forms import EmptyForm
    form = EmptyForm()
    product = Product.query.get_or_404(product_id)
    if not form.validate_on_submit():
        abort(400)
    product.is_active = not product.is_active
    db.session.add(AuditLog(
        actor_id=current_user.id,
        action="product_toggled",
        entity_type="Product",
        entity_id=str(product.id),
    ))
    db.session.commit()
    return redirect(url_for("admin.products"))


@admin_bp.route("/pedido/<public_id>", methods=["GET", "POST"])
@admin_required
def manage_order(public_id: str):
    order = Order.query.filter_by(public_id=public_id).first_or_404()
    form = StatusForm()
    choices = [(status, label) for status, label in (
        ("awaiting_confirmation", "Aguardando confirmação"),
        ("awaiting_payment", "Aguardando pagamento"),
        ("payment_confirmed", "Pagamento confirmado"),
        ("received", "Pedido recebido"),
        ("preparing", "Em preparação"),
        ("out_for_delivery", "Saiu para entrega"),
        ("ready_for_pickup", "Disponível para retirada"),
        ("completed", "Concluído"),
        ("cancelled", "Cancelado"),
    )]
    form.status.choices = choices
    if form.validate_on_submit():
        try:
            change_order_status(order, form.status.data, current_user, form.note.data or "")
            db.session.add(AuditLog(
                actor_id=current_user.id,
                action="order_status_changed",
                entity_type="Order",
                entity_id=order.public_id,
            ))
            db.session.commit()
            flash("Status atualizado.", "success")
        except CommerceError as error:
            db.session.rollback()
            flash(str(error), "error")
        return redirect(url_for("admin.manage_order", public_id=order.public_id))
    return render_template("admin/order.html", order=order, form=form, allowed=ALLOWED_TRANSITIONS[order.status])


@admin_bp.route("/pedido/<public_id>/confirmar-pagamento", methods=["POST"])
@admin_required
def mark_payment(public_id: str):
    from app.forms import EmptyForm
    form = EmptyForm()
    order = Order.query.filter_by(public_id=public_id).first_or_404()
    if not form.validate_on_submit():
        abort(400)
    try:
        confirm_payment(order, current_user)
        db.session.add(AuditLog(
            actor_id=current_user.id,
            action="payment_confirmed",
            entity_type="Order",
            entity_id=order.public_id,
        ))
        db.session.commit()
        flash("Pagamento confirmado manualmente.", "success")
    except CommerceError as error:
        db.session.rollback()
        flash(str(error), "error")
    return redirect(url_for("admin.manage_order", public_id=order.public_id))
