"""Shared PostgreSQL connection configuration."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from sqlalchemy import URL


load_dotenv(override=False)
load_dotenv(".env.postgres", override=False)


def settings() -> dict[str, str | int]:
    values = {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    missing = [key for key in ("dbname", "user", "password") if not values[key]]
    if missing:
        names = ", ".join(f"POSTGRES_{key.upper()}" for key in missing)
        raise RuntimeError(f"Missing PostgreSQL configuration: {names}")
    return values


def connect():
    return psycopg.connect(**settings(), row_factory=dict_row)


def sqlalchemy_url() -> URL:
    config = settings()
    return URL.create(
        "postgresql+psycopg",
        username=str(config["user"]),
        password=str(config["password"]),
        host=str(config["host"]),
        port=int(config["port"]),
        database=str(config["dbname"]),
    )
