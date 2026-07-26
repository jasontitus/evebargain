"""Re-exports every model so they can be imported from one place.

This also guarantees all models are imported before `Base.metadata.create_all()`
runs -- SQLAlchemy only knows about a table if its class has been imported, so a
model that nothing imports would silently never be created.

`__all__` lists the public names, which is what `from app.models import *`
would pull in and what linters use to tell a deliberate re-export from an
unused import.
"""

from app.models.user import User, UserConfig
from app.models.item import ItemType, ItemCategory
from app.models.market import MarketCache
from app.models.alert import Alert

__all__ = ["User", "UserConfig", "ItemType", "ItemCategory", "MarketCache", "Alert"]
