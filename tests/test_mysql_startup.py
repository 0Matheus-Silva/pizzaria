from __future__ import annotations

from flask import Flask
from sqlalchemy.engine import URL

import app.mysql_startup as mysql_startup
from app import create_app
from app.extensions import db


class FakeMySQLState:
    def __init__(self, *, database_exists: bool, charset: str | None = "utf8mb4"):
        self.database_exists = database_exists
        self.charset = charset if database_exists else None
        self.statements: list[tuple[str, tuple | None, str]] = []
        self.connected_users: list[str] = []


class FakeCursor:
    def __init__(self, connection, state: FakeMySQLState):
        self.connection = connection
        self.state = state
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement: str, parameters: tuple | None = None):
        self.state.statements.append((statement, parameters, self.connection.user))
        if "GET_LOCK" in statement:
            self.result = (1,)
        elif "RELEASE_LOCK" in statement:
            self.result = (1,)
        elif "INFORMATION_SCHEMA.SCHEMATA" in statement:
            self.result = (self.state.charset,) if self.state.database_exists else None
        elif statement.startswith("CREATE DATABASE"):
            self.state.database_exists = True
            self.state.charset = "utf8mb4"
        else:
            raise AssertionError(f"Unexpected SQL in startup: {statement}")

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, user: str, state: FakeMySQLState):
        self.user = user
        self.state = state
        self.closed = False

    def cursor(self):
        return FakeCursor(self, self.state)

    def close(self):
        self.closed = True


def _mysql_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "mysql+pymysql",
        username="pizzaria_app",
        password="app-test-password",
        host="127.0.0.1",
        port=3306,
        database="pizzaria_test",
    )
    return app


def _install_fake_mysql(monkeypatch, state: FakeMySQLState):
    connections = []

    def connect(**kwargs):
        state.connected_users.append(kwargs["user"])
        connection = FakeConnection(kwargs["user"], state)
        connections.append(connection)
        return connection

    monkeypatch.setattr(mysql_startup.pymysql, "connect", connect)
    monkeypatch.setattr(mysql_startup, "_apply_migrations_and_validate", lambda: "test-head")
    return connections


def test_existing_mysql_database_uses_app_user_without_provisioning(monkeypatch):
    state = FakeMySQLState(database_exists=True)
    connections = _install_fake_mysql(monkeypatch, state)

    revision = mysql_startup.initialize_mysql_database(_mysql_app())

    assert revision == "test-head"
    assert state.connected_users == ["pizzaria_app"]
    assert all(connection.closed for connection in connections)
    statements = [statement.upper() for statement, _, _ in state.statements]
    assert not any(statement.startswith("CREATE DATABASE") for statement in statements)
    assert not any(
        statement.startswith(("DROP ", "DELETE ", "ALTER "))
        for statement in statements
    )


def test_missing_mysql_database_is_created_with_provisioning_user(monkeypatch):
    state = FakeMySQLState(database_exists=False)
    connections = _install_fake_mysql(monkeypatch, state)
    monkeypatch.setenv("MYSQL_PROVISION_USER", "pizzaria_provisioner")
    monkeypatch.setenv("MYSQL_PROVISION_PASSWORD", "provision-test-password")

    revision = mysql_startup.initialize_mysql_database(_mysql_app())

    create_statements = [
        (statement, user)
        for statement, _, user in state.statements
        if statement.startswith("CREATE DATABASE")
    ]
    assert revision == "test-head"
    assert state.database_exists
    assert state.charset == "utf8mb4"
    assert state.connected_users == ["pizzaria_app", "pizzaria_provisioner"]
    assert len(create_statements) == 1
    assert create_statements[0][1] == "pizzaria_provisioner"
    assert all(connection.closed for connection in connections)


def test_missing_database_without_provision_credentials_fails(monkeypatch):
    state = FakeMySQLState(database_exists=False)
    _install_fake_mysql(monkeypatch, state)
    monkeypatch.delenv("MYSQL_PROVISION_USER", raising=False)
    monkeypatch.delenv("MYSQL_PROVISION_PASSWORD", raising=False)

    try:
        mysql_startup.initialize_mysql_database(_mysql_app())
    except mysql_startup.DatabaseStartupError as error:
        assert "MYSQL_PROVISION_USER" in str(error)
    else:
        raise AssertionError("Startup should require provisioner credentials for a missing database.")

    assert not any(statement.startswith("CREATE DATABASE") for statement, _, _ in state.statements)


def test_existing_database_with_other_charset_is_not_modified(monkeypatch):
    state = FakeMySQLState(database_exists=True, charset="latin1")
    _install_fake_mysql(monkeypatch, state)

    try:
        mysql_startup.initialize_mysql_database(_mysql_app())
    except mysql_startup.DatabaseStartupError as error:
        assert "utf8mb4" in str(error)
    else:
        raise AssertionError("Startup should reject an existing database with a different charset.")

    assert not any(
        statement.upper().startswith(("CREATE ", "DROP ", "ALTER ", "DELETE "))
        for statement, _, _ in state.statements
    )


def test_unavailable_mysql_fails_without_sqlite_fallback(monkeypatch):
    def unavailable(**kwargs):
        raise mysql_startup.pymysql.err.OperationalError(2003, "connection unavailable")

    monkeypatch.setattr(mysql_startup.pymysql, "connect", unavailable)
    app = _mysql_app()

    try:
        mysql_startup.initialize_mysql_database(app)
    except mysql_startup.DatabaseStartupError as error:
        assert "indisponível" in str(error)
    else:
        raise AssertionError("Startup should fail if MySQL is unavailable.")

    assert app.config["SQLALCHEMY_DATABASE_URI"].drivername == "mysql+pymysql"


def test_invalid_mysql_credentials_fail_without_exposing_password(monkeypatch):
    def invalid_credentials(**kwargs):
        raise mysql_startup.pymysql.err.OperationalError(1045, "access denied")

    monkeypatch.setattr(mysql_startup.pymysql, "connect", invalid_credentials)
    app = _mysql_app()

    try:
        mysql_startup.initialize_mysql_database(app)
    except mysql_startup.DatabaseStartupError as error:
        assert "Autenticação" in str(error)
        assert "app-test-password" not in str(error)
    else:
        raise AssertionError("Startup should fail if MySQL credentials are invalid.")


def test_repeated_migrations_preserve_data_and_do_not_duplicate_schema(tmp_path):
    database_path = tmp_path / "auto-init.sqlite"
    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "SECRET_KEY": "migration-test-secret-long-enough",
    }

    first_app = create_app(config)
    with first_app.app_context():
        first_revision = mysql_startup._apply_migrations_and_validate()
        category = mysql_startup.db.metadata.tables["categories"]
        connection = db.engine.connect()
        try:
            connection.execute(
                category.insert().values(
                    name="Persistência fictícia",
                    slug="persistencia-ficticia",
                    description="Registro de teste",
                    is_active=True,
                    display_order=0,
                )
            )
            connection.commit()
        finally:
            connection.close()
            db.session.remove()
            db.engine.dispose()

    second_app = create_app(config)
    with second_app.app_context():
        second_revision = mysql_startup._apply_migrations_and_validate()
        inspector_tables = set(db.inspect(db.engine).get_table_names())
        saved = db.session.execute(
            db.select(mysql_startup.db.metadata.tables["categories"]).where(
                mysql_startup.db.metadata.tables["categories"].c.slug == "persistencia-ficticia"
            )
        ).one()

        assert first_revision == second_revision == "b40ca30e4742"
        assert "categories" in inspector_tables
        assert saved.name == "Persistência fictícia"
        db.session.remove()
        db.engine.dispose()
