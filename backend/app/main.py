from fastapi import FastAPI

from app.api import catalog
from app.api import vendor

app = FastAPI(title="CardOps API", version="0.1.0")

app.include_router(catalog.router, prefix="/api/v1")
app.include_router(vendor.router, prefix="/api/v1")
