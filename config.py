from __future__ import annotations

import os
import secrets
from datetime import timedelta

from sqlalchemy.engine import URL


def _database_uri() -> str | URL:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    mysql_host = os.getenv("MYSQL_HOST")
    if mysql_host:
        return URL.create(
            drivername="mysql+pymysql",
            username=os.getenv("MYSQL_USER", "pizzaria_app"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            host=mysql_host,
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=os.getenv("MYSQL_DATABASE", "pizzaria_picon"),
            query={"charset": "utf8mb4"},
        )

    return "sqlite:///bella_pizza.db"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    TEMPLATES_AUTO_RELOAD = True
    WTF_CSRF_TIME_LIMIT = 3600
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
