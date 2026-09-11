import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://process:process@db:5432/process_control")
os.environ["JWT_SECRET"] = "test-secret-only-must-be-at-least-32-bytes"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal
from app.main import app
from app.models.core import Base
from app.services.bootstrap import bootstrap_admin, ensure_base_roles


@pytest.fixture(autouse=True)
def clean_database():
    with SessionLocal.begin() as db:
        tables = ", ".join(table.name for table in reversed(Base.metadata.sorted_tables))
        db.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_token(client):
    with SessionLocal.begin() as db:
        bootstrap_admin(db, legajo="TEST-001", nombre="Admin de Prueba", username="admin.test", password="Clave-de-prueba-123", sector="Administracion")
    response = client.post("/api/v1/auth/login", json={"username": "admin.test", "password": "Clave-de-prueba-123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
