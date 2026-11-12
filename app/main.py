from fastapi import FastAPI

from app.database import Base, engine
from app import models
from app.routes import orders

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="E-Commerce Order Management Service",
    description="Microservice for managing customer orders",
    version="1.0.0"
)

app.include_router(orders.router)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to E-Commerce Order Management Service",
        "documentation": "/docs"
    }


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "service": "Order Management Service",
        "status": "healthy"
    }
