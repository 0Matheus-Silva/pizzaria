from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pymysql
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from flask import Flask
from flask_migrate import upgrade
from sqlalchemy import inspect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, migrate

_DATABASE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_]{1,64}\Z")
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class DatabaseStartupError(RuntimeError):
    pass


def _connect(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
) -> Any:
    try:
        return pymysql.connect(
            host=host,
            port=port,
            user=username,
            password=password,
            charset="utf8mb4",
            connect_timeout=5,
            autocommit=True,
        )
    except pymysql.MySQLError as error:
        code = error.args[0] if error.args else None
        if code == 1045:
            message = "Autenticação MySQL recusada; confira o usuário e a senha configurados."
        elif code in {2002, 2003, 2006, 2013}:
            message = "Servidor MySQL indisponível; confira se o serviço está ativo e o host/porta."
        else:
            message = "Não foi possível conectar ao servidor MySQL; confira a configuração e as permissões."
        raise DatabaseStartupError(message) from None


def _database_url(app: Flask) -> URL:
    try:
        url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    except (KeyError, SQLAlchemyError, ValueError):
        raise DatabaseStartupError("A URL de conexão MySQL está inválida.") from None
    if url.drivername.split("+", 1)[0] != "mysql":
        raise DatabaseStartupError(
            "A inicialização automática requer MySQL. Configure MYSQL_*; "
            "não será usado SQLite como alternativa."
        )
    if not url.host or not url.username or not url.database:
        raise DatabaseStartupError("Configure host, usuário e banco na URL MySQL.")
    if not _DATABASE_NAME_PATTERN.fullmatch(url.database):
        raise DatabaseStartupError("O nome do banco MySQL contém caracteres não permitidos.")
    if url.query.get("charset", "utf8mb4").lower() != "utf8mb4":
        raise DatabaseStartupError("A conexão MySQL precisa usar charset utf8mb4.")
    url = url.update_query_dict({"charset": "utf8mb4"})
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    return url


def _read_schema_charset(connection: Any, database: str) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DEFAULT_CHARACTER_SET_NAME "
            "FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
            (database,),
        )
        result = cursor.fetchone()
    return result[0] if result else None


def _create_database(url: URL) -> None:
    provision_user = os.getenv("MYSQL_PROVISION_USER")
    provision_password = os.getenv("MYSQL_PROVISION_PASSWORD")
    if not provision_user or not provision_password:
        raise DatabaseStartupError(
            f"O banco '{url.database}' não existe. Configure MYSQL_PROVISION_USER e "
            "MYSQL_PROVISION_PASSWORD para criá-lo automaticamente, ou peça ao "
            "administrador MySQL para criá-lo."
        )

    connection = _connect(
        host=url.host,
        port=url.port or 3306,
        username=provision_user,
        password=provision_password,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
    except pymysql.MySQLError as error:
        code = error.args[0] if error.args else None
        if code == 1044 or code == 1142:
            message = (
                "A conta de provisionamento não tem permissão CREATE para criar "
                "o banco configurado."
            )
        else:
            message = "O MySQL recusou a criação do banco; confira a configuração de provisionamento."
        raise DatabaseStartupError(message) from None
    finally:
        connection.close()


def _apply_migrations_and_validate() -> str:
    try:
        upgrade(directory=str(_MIGRATIONS_DIR))
        migration_config = migrate.get_config(directory=str(_MIGRATIONS_DIR))
        expected_head = ScriptDirectory.from_config(migration_config).get_current_head()
        with db.engine.connect() as connection:
            current_revision = MigrationContext.configure(connection).get_current_revision()
        if current_revision != expected_head:
            raise DatabaseStartupError(
                "A versão aplicada do banco não corresponde à migration mais recente."
            )

        missing_tables = {
            table.name for table in db.metadata.sorted_tables
        } - set(inspect(db.engine).get_table_names())
        if missing_tables:
            raise DatabaseStartupError(
                "A validação do banco encontrou tabelas ausentes: "
                + ", ".join(sorted(missing_tables))
            )
        return expected_head
    except DatabaseStartupError:
        raise
    except (CommandError, SQLAlchemyError, pymysql.MySQLError):
        raise DatabaseStartupError(
            "Não foi possível aplicar ou validar as migrations MySQL. "
            "Confira o estado do banco e as permissões do usuário da aplicação."
        ) from None


def initialize_mysql_database(app: Flask) -> str:
    url = _database_url(app)
    lock_name = f"pizzaria:{url.database}"[:64]
    application_connection = _connect(
        host=url.host,
        port=url.port or 3306,
        username=url.username,
        password=url.password or "",
    )
    try:
        with application_connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, 30))
            lock_result = cursor.fetchone()
        if not lock_result or lock_result[0] != 1:
            raise DatabaseStartupError(
                "Outra inicialização está usando o banco; tente novamente em instantes."
            )

        schema_charset = _read_schema_charset(application_connection, url.database)
        if schema_charset is None:
            _create_database(url)
            schema_charset = _read_schema_charset(application_connection, url.database)
            if schema_charset is None:
                raise DatabaseStartupError(
                    "O banco foi criado, mas o usuário da aplicação não tem acesso a ele. "
                    "Confira as permissões MySQL para esse banco."
                )
        if schema_charset.lower() != "utf8mb4":
            raise DatabaseStartupError(
                f"O banco existente '{url.database}' não usa utf8mb4. "
                "Ele não foi alterado; ajuste seu charset manualmente após verificar os dados."
            )

        with app.app_context():
            return _apply_migrations_and_validate()
    finally:
        application_connection.close()
