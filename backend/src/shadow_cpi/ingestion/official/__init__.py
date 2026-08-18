"""Sources with an official API: government and institutional data feeds.

These are preferred over scraping wherever they exist. They are free, stable, and
carry no question about whether automated access is permitted.

Importing this package registers every source in it, which is how the scheduler
discovers them without holding a list of its own.
"""

from shadow_cpi.ingestion.official.eia import EiaPetroleumSpotIngestor
from shadow_cpi.ingestion.official.sec_edgar import SecThirteenFIngestor
from shadow_cpi.ingestion.official.usda_mars import UsdaGrainPriceIngestor

__all__ = [
    "EiaPetroleumSpotIngestor",
    "SecThirteenFIngestor",
    "UsdaGrainPriceIngestor",
]
