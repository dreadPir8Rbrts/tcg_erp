"""
Celery task: weekly OnTreasure card show scrape.

Scrapes 90 days of upcoming Non-Sports / TCG card shows and upserts
into the card_shows table.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="shows.scrape_ontreasure",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # 5 min between retries
)
def scrape_ontreasure_task(self):
    """
    Weekly card show scrape from OnTreasure.com.
    Scrapes 90 days ahead, upserts all events into card_shows table.
    """
    from scripts.scrape_card_shows import scrape_and_save

    try:
        result = scrape_and_save(days=90)
        logger.info(
            "shows.scrape_ontreasure complete: "
            "scraped=%d upserted=%d skipped=%d",
            result["scraped"], result["upserted"], result["skipped"],
        )
        return result
    except Exception as exc:
        logger.error("shows.scrape_ontreasure failed: %s", exc)
        raise self.retry(exc=exc)
