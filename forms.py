from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
)


class RegistrationForm(FlaskForm):
    name = StringField("Nome completo", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=254)])
    phone = StringField("Telefone", validators=[DataRequired(), Length(max=30)])
    password = PasswordField(
        "Senha", validators=[DataRequired(), Length(min=12, max=128)]
    )
    confirm_password = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("password", message="As senhas não coincidem.")],
    )
    terms = BooleanField("Aceito os termos e a política de privacidade", validators=[DataRequired()])
    submit = SubmitField("Criar conta")


class LoginForm(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(), Email()])
    password = PasswordField("Senha", validators=[DataRequired()])
    submit = SubmitField("Entrar")


class AddressForm(FlaskForm):
    label = StringField("Apelido", validators=[DataRequired(), Length(max=50)])
    postal_code = StringField("CEP", validators=[DataRequired(), Length(max=9)])
    street = StringField("Rua", validators=[DataRequired(), Length(max=160)])
    number = StringField("Número", validators=[DataRequired(), Length(max=20)])
    complement = StringField("Complemento", validators=[Optional(), Length(max=100)])
    neighborhood = StringField("Bairro", validators=[DataRequired(), Length(max=100)])
    city = StringField("Cidade", validators=[DataRequired(), Length(max=100)])
    state = StringField("Estado (UF)", validators=[DataRequired(), Length(min=2, max=2)])
    reference = StringField("Ponto de referência", validators=[Optional(), Length(max=160)])
    submit = SubmitField("Salvar endereço")


class ContactForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=254)])
    message = TextAreaField("Mensagem", validators=[DataRequired(), Length(min=10, max=2000)])
    submit = SubmitField("Enviar mensagem")


class CheckoutForm(FlaskForm):
    order_type = SelectField(
        "Como deseja receber?",
        choices=[("delivery", "Entrega"), ("pickup", "Retirada no local")],
        validators=[DataRequired()],
    )
    address_id = SelectField("Endereço", coerce=int, validators=[Optional()])
    payment_method = SelectField(
        "Forma de pagamento",
        choices=[("pix", "Pix manual"), ("cash", "Dinheiro na entrega"), ("card", "Cartão na entrega")],
        validators=[DataRequired()],
    )
    change_for = DecimalField("Troco para quanto? (R$)", validators=[Optional(), NumberRange(min=0)])
    customer_note = StringField("Observações para entrega", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Confirmar pedido")


class CheckoutConfirmForm(FlaskForm):
    confirm = BooleanField(
        "Confirmo os dados e valores do pedido", validators=[DataRequired()]
    )
    submit = SubmitField("Confirmar pedido")


class ProductForm(FlaskForm):
    name = StringField("Nome", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Descrição", validators=[Optional(), Length(max=2000)])
    ingredients = TextAreaField("Ingredientes", validators=[Optional(), Length(max=1000)])
    category_id = SelectField("Categoria", coerce=int, validators=[DataRequired()])
    size_name = StringField("Tamanho inicial", validators=[DataRequired(), Length(max=40)])
    price = DecimalField("Preço (R$)", validators=[DataRequired(), NumberRange(min=0.01)])
    image_url = StringField("URL da imagem (opcional)", validators=[Optional(), Length(max=500)])
    is_available = BooleanField("Disponível", default=True)
    is_featured = BooleanField("Destaque na página inicial")
    submit = SubmitField("Salvar produto")


class StatusForm(FlaskForm):
    status = SelectField("Novo status", validators=[DataRequired()])
    note = StringField("Observação", validators=[Optional(), Length(max=250)])
    submit = SubmitField("Atualizar status")


class EmptyForm(FlaskForm):
    submit = SubmitField("Confirmar")
