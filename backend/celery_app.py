"""
Celery application factory and beat schedule for CardOps.

Workers are started with:
    celery -A celery_app worker --loglevel=info

Beat scheduler is started with:
    celery -A celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from app.db.session import settings

app = Celery(
    "cardops",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.catalog_sync",
        "app.tasks.price_sync",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Beat schedule — all times UTC
    beat_schedule={
        "catalog-sync-new-sets": {
            "task": "catalog.sync_new_sets",
            "schedule": crontab(hour=2, minute=0),       # 2am daily
        },
        "catalog-delta-sync": {
            "task": "catalog.delta_sync_cards",
            "schedule": crontab(hour=3, minute=0),       # 3am daily
        },
        "prices-refresh": {
            "task": "prices.refresh_active_inventory",
            "schedule": crontab(minute=0, hour="*/6"),   # every 6 hours
        },
    },
)
