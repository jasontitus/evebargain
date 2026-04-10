# Key EVE Online IDs
THE_FORGE_REGION_ID = 10000002  # Region containing Jita
JITA_SYSTEM_ID = 30000142
JITA_STATION_ID = 60003760  # Jita IV - Moon 4 - Caldari Navy Assembly Plant

# ESI required scopes
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

# Categories available for user tracking
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
