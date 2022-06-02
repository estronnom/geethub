import pytest
from app import app as geethub_app


@pytest.fixture()
def app():
    return geethub_app


@pytest.fixture()
def client(app):
    return app.test_client()
