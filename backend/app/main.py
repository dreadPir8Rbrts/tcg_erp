from fastapi import FastAPI

from app.api import catalog

app = FastAPI(title="CardOps API", version="0.1.0")

app.include_router(catalog.router, prefix="/api")
