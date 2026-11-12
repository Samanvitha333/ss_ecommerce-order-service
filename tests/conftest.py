import pytest

from fastapi.testclient import TestClient

from app.database import Base, engine, get_db
from app.main import app


# Use the DATABASE_URL supplied when running pytest.
# It must point to order_test_db, not order_db.


def override_get_db():
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
