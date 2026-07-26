"""Fixed EVE Online identifiers.

These are game constants, not settings: CCP assigns them and they do not change
between installs, so they are hardcoded rather than being read from .env.

Naming them matters for readability -- `region_id == THE_FORGE_REGION_ID` says
what it means, where `region_id == 10000002` would need a comment every time.
"""

# The Forge is the region containing Jita, EVE's main trade hub. Every price
# in this app is compared against Jita, which makes this the reference market
# rather than a destination -- several endpoints exclude it for that reason.
THE_FORGE_REGION_ID = 10000002
JITA_SYSTEM_ID = 30000142
JITA_STATION_ID = 60003760  # Jita IV - Moon 4 - Caldari Navy Assembly Plant

# Permissions requested during login. This app asks for exactly one: the
# ability to read where your character is. It cannot see your assets, wallet
# or mail, and asking for less makes the consent screen honest.
SSO_SCOPES = [
    "esi-location.read_location.v1",
]

# Item Category IDs from EVE SDE
CATEGORY_SHIPS = 6
CATEGORY_MODULES = 7
CATEGORY_CHARGES = 8  # Ammunition
CATEGORY_BLUEPRINTS = 9
CATEGORY_SKILLS = 16
CATEGORY_DRONES = 18
CATEGORY_IMPLANTS = 20
CATEGORY_MATERIALS = 4  # Minerals, PI, manufacturing components
CATEGORY_PLANETARY = 43
CATEGORY_SKINS = 91  # Ship SKINs

# The categories offered in the UI, mapping EVE's numeric id to a readable
# name. A dict rather than a list so lookups by id are direct.
TRACKABLE_CATEGORIES = {
    CATEGORY_SHIPS: "Ships",
    CATEGORY_MODULES: "Modules",
    CATEGORY_CHARGES: "Ammunition & Charges",
    CATEGORY_DRONES: "Drones",
    CATEGORY_SKINS: "Ship SKINs",
    CATEGORY_IMPLANTS: "Implants & Boosters",
    CATEGORY_MATERIALS: "Materials & Components",
    CATEGORY_BLUEPRINTS: "Blueprints",
    CATEGORY_PLANETARY: "Planetary Materials",
}
