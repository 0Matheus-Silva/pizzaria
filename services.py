from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.extensions import db
from app.models import (
    Addon,
    DeliveryZone,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderStatusHistory,
    Payment,
    Product,
    ProductSize,
    Promotion,
    StoreSettings,
    User,
)

ZERO = Decimal("0.00")
MAX_QUANTITY = 20
ALLOWED_TRANSITIONS = {
    "awaiting_confirmation": {"awaiting_payment", "received", "cancelled"},
    "awaiting_payment": {"payment_confirmed", "cancelled"},
    "payment_confirmed": {"received", "cancelled"},
    "received": {"preparing", "cancelled"},
    "preparing": {"out_for_delivery", "ready_for_pickup", "cancelled"},
    "out_for_delivery": {"completed"},
    "ready_for_pickup": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


class CommerceError(ValueError):
    pass


@dataclass(frozen=True)
class PricedLine:
    product: Product
    size: ProductSize
    addons: list[Addon]
    quantity: int
    observation: str
    unit_price: Decimal
    discount_per_unit: Decimal

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class OrderQuote:
    lines: list[PricedLine]
    subtotal: Decimal
    discount: Decimal
    delivery_fee: Decimal
    total: Decimal
    delivery_snapshot: str


def active_promotion(product_id: int, size: ProductSize) -> Promotion | None:
    now = datetime.now(timezone.utc)
    promotions = Promotion.query.filter_by(
        product_id=product_id, is_active=True
    ).all()
    for promotion in promotions:
        starts = promotion.starts_at
        ends = promotion.ends_at
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=timezone.utc)
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        if starts <= now <= ends and ZERO < promotion.promotional_price <= size.price:
            return promotion
    return None


def price_cart(cart: list[dict]) -> list[PricedLine]:
    if not cart:
        return []
    result = []
    for item in cart:
        try:
            product_id = int(item["product_id"])
            size_id = int(item["size_id"])
            quantity = int(item["quantity"])
            addon_ids = {int(value) for value in item.get("addon_ids", [])}
        except (KeyError, TypeError, ValueError) as error:
            raise CommerceError("Um item do carrinho está inválido.") from error
        if not 1 <= quantity <= MAX_QUANTITY:
            raise CommerceError("A quantidade deve ficar entre 1 e 20.")

        product = db.session.get(Product, product_id)
        size = db.session.get(ProductSize, size_id)
        if (
            product is None
            or not product.is_active
            or not product.is_available
            or size is None
            or size.product_id != product.id
            or not size.is_available
        ):
            raise CommerceError("Um produto ou tamanho ficou indisponível.")

        addons = [addon for addon in product.addons if addon.id in addon_ids]
        if len(addons) != len(addon_ids) or any(not addon.is_available for addon in addons):
            raise CommerceError("Um adicional selecionado não está mais disponível.")

        promotion = active_promotion(product.id, size)
        base_price = promotion.promotional_price if promotion else size.price
        discount_per_unit = (
            Decimal(size.price) - Decimal(base_price) if promotion else ZERO
        )
        unit_price = Decimal(base_price) + sum(
            (Decimal(addon.price) for addon in addons), start=ZERO
        )
        result.append(
            PricedLine(
                product=product,
                size=size,
                addons=addons,
                quantity=quantity,
                observation=str(item.get("observation", ""))[:250],
                unit_price=unit_price,
                discount_per_unit=discount_per_unit,
            )
        )
    return result


def quote_order(
    *,
    user: User,
    cart: list[dict],
    order_type: str,
    payment_method: str,
    address_id: int | None,
    change_for: Decimal | None,
) -> OrderQuote:
    settings = StoreSettings.query.first() or StoreSettings()
    if not settings.is_open:
        raise CommerceError("A loja está fechada e não está recebendo pedidos.")
    lines = price_cart(cart)
    if not lines:
        raise CommerceError("Seu carrinho está vazio.")

    if order_type not in {"delivery", "pickup"}:
        raise CommerceError("Escolha entrega ou retirada.")
    if order_type == "pickup" and not settings.accepts_pickup:
        raise CommerceError("A retirada não está disponível.")
    if payment_method not in {"pix", "cash", "card"}:
        raise CommerceError("Forma de pagamento inválida.")
    if payment_method == "pix" and not settings.accepts_pix:
        raise CommerceError("O pagamento por Pix não está disponível.")
    if payment_method == "cash" and not settings.accepts_cash:
        raise CommerceError("O pagamento em dinheiro não está disponível.")
    if payment_method == "card" and not settings.accepts_card:
        raise CommerceError("O pagamento com cartão não está disponível.")
    if payment_method != "cash" and change_for is not None:
        raise CommerceError("O troco só pode ser informado para pagamento em dinheiro.")

    address_snapshot = ""
    delivery_fee = ZERO
    if order_type == "delivery":
        address = next((a for a in user.addresses if a.id == address_id), None)
        if address is None:
            raise CommerceError("Selecione um endereço de entrega válido.")
        zone = DeliveryZone.query.filter_by(
            neighborhood=address.neighborhood, is_active=True
        ).first()
        if zone is None:
            raise CommerceError("Ainda não atendemos esse bairro.")
        delivery_fee = Decimal(zone.delivery_fee)
        address_snapshot = " | ".join(
            part for part in (
                f"{address.street}, {address.number}",
                address.complement,
                address.neighborhood,
                f"{address.city}/{address.state}",
                address.postal_code,
                address.reference,
            ) if part
        )
    elif address_id is not None:
        raise CommerceError("Endereço não se aplica a pedidos para retirada.")

    subtotal = sum(
        (
            (Decimal(line.size.price) + sum(
                (Decimal(addon.price) for addon in line.addons), start=ZERO
            )) * line.quantity
            for line in lines
        ),
        start=ZERO,
    )
    discount = sum(
        (line.discount_per_unit * line.quantity for line in lines),
        start=ZERO,
    )
    total = subtotal - discount + delivery_fee
    if payment_method == "cash" and change_for is not None and change_for < total:
        raise CommerceError("O valor para troco precisa cobrir o total do pedido.")
    return OrderQuote(
        lines=lines,
        subtotal=subtotal,
        discount=discount,
        delivery_fee=delivery_fee,
        total=total,
        delivery_snapshot=address_snapshot,
    )


def create_order(
    *,
    user: User,
    cart: list[dict],
    order_type: str,
    payment_method: str,
    address_id: int | None,
    customer_note: str,
    change_for: Decimal | None,
    idempotency_key: str,
    expected_total: Decimal | None = None,
) -> Order:
    existing_order = Order.query.filter_by(checkout_key=idempotency_key).first()
    if existing_order:
        if existing_order.user_id != user.id:
            raise CommerceError("Não foi possível validar esta confirmação.")
        return existing_order
    quote = quote_order(
        user=user,
        cart=cart,
        order_type=order_type,
        payment_method=payment_method,
        address_id=address_id,
        change_for=change_for,
    )
    if expected_total is not None and expected_total != quote.total:
        raise CommerceError("O preço ou a taxa mudou. Revise o pedido antes de confirmar.")
    payment_status = "pending"
    initial_status = "awaiting_payment" if payment_method == "pix" else "received"
    order = Order(
        public_id=uuid4().hex[:10].upper(),
        checkout_key=idempotency_key,
        user_id=user.id,
        order_type=order_type,
        status=initial_status,
        payment_method=payment_method,
        payment_status=payment_status,
        subtotal=quote.subtotal,
        discount=quote.discount,
        delivery_fee=quote.delivery_fee,
        total=quote.total,
        delivery_snapshot=quote.delivery_snapshot,
        customer_note=customer_note[:500],
        change_for=change_for,
    )
    db.session.add(order)
    db.session.flush()
    for line in quote.lines:
        order_item = OrderItem(
            order_id=order.id,
            product_id=line.product.id,
            product_name=line.product.name,
            size_name=line.size.name,
            unit_price=line.unit_price,
            quantity=line.quantity,
            observation=line.observation,
        )
        db.session.add(order_item)
        db.session.flush()
        for addon in line.addons:
            db.session.add(
                OrderItemAddon(
                    order_item_id=order_item.id,
                    name=addon.name,
                    unit_price=addon.price,
                )
            )
    db.session.add(
        Payment(order_id=order.id, method=payment_method, amount=quote.total)
    )
    db.session.add(
        OrderStatusHistory(
            order_id=order.id,
            status=initial_status,
            actor_id=user.id,
            note="Pedido criado pelo cliente.",
        )
    )
    return order


def change_order_status(order: Order, status: str, actor: User, note: str = "") -> None:
    if status not in ALLOWED_TRANSITIONS.get(order.status, set()):
        raise CommerceError("Essa mudança de status não é permitida.")
    if status == "completed" and order.payment_status != "confirmed":
        raise CommerceError("Confirme o pagamento antes de concluir o pedido.")
    order.status = status
    db.session.add(
        OrderStatusHistory(
            order_id=order.id,
            status=status,
            actor_id=actor.id,
            note=note[:250],
        )
    )


def confirm_payment(order: Order, actor: User) -> None:
    if order.payment_status == "confirmed":
        raise CommerceError("O pagamento já foi confirmado.")
    if order.status == "cancelled":
        raise CommerceError("Não é possível confirmar o pagamento de um pedido cancelado.")
    order.payment_status = "confirmed"
    order.payment.status = "confirmed"
    order.payment.confirmed_by = actor.id
    order.payment.confirmed_at = datetime.now(timezone.utc)
    if order.status == "awaiting_payment":
        change_order_status(order, "payment_confirmed", actor, "Pagamento confirmado manualmente.")
