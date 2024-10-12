import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_register_user():
    response = client.post("/register/", json={
        "email": "testuser@example.com",
        "password": "testpassword"
    })
    
    assert response.status_code == 200
    assert response.json()["email"] == "testuser@example.com"

def test_register_existing_user():
    client.post("/register/", json={
        "email": "existinguser@example.com",
        "password": "password"
    })
    
    response = client.post("/register/", json={
        "email": "existinguser@example.com",
        "password": "password"
    })
    
    assert response.status_code == 409
    assert response.json()["detail"] == "User with this email already exists"