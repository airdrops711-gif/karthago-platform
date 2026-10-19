"""Presentation metadata for the storefront categories.

The emoji shown on a category tile must be the same whether the category was
created by the source seeder or by the scraper while it filed a product under
a finer department. The map therefore lives in its own module, imported by
both sides.
"""

CATEGORY_ICONS = {
    # Computers & electronics
    "Ordinateurs Portables": "💻",
    "Informatique & Accessoires": "🖥️",
    "Informatique": "🖥️",
    "Accessoires": "🎧",
    "Câbles & Adaptateurs": "🔌",
    "Adaptateurs": "🔌",
    "Téléphones Portables": "📱",
    "Smartphones": "📱",
    "Téléphones & Tablettes": "📱",
    "Téléphones": "📱",
    "TV & Audio": "📺",
    "Photo & Caméras": "📷",
    # Appliances
    "Électroménager": "🔌",
    "Cuisine & Électroménager": "🍳",
    "Cuisine": "🍳",
    "Éclairage": "💡",
    # Home
    "Maison & Bureau": "🛋️",
    "Décoration": "🕯️",
    "Décoration Maison": "🕯️",
    "Literie": "🛏️",
    "Rangement": "🗄️",
    "Mobilier": "🛋️",
    # Fashion
    "Mode & Bijoux": "👗",
    "Mode": "👗",
    "Mode Femme": "👗",
    "Mode Homme": "👔",
    "Pantalons": "👖",
    "Jupes": "👗",
    "Ensembles": "👗",
    "Robes": "👗",
    "T-Shirts": "👕",
    "Chemises": "👔",
    "Polos": "👕",
    "Sweats": "🧥",
    "Manteaux": "🧥",
    "Vestes": "🧥",
    "Sportswear": "🏃",
    "Chaussures": "👟",
    "Sacs": "👜",
    "Accessoires Mode": "👜",
    "Bijoux": "💍",
    "Parfums": "🌸",
    "Beauté & Bien-être": "🧴",
    "Santé & Beauté": "🧴",
    "Beauté": "🧴",
    # Leisure
    "Consoles & Jeux": "🎮",
    "Gaming": "🎮",
    "Jouets & Jeux": "🧸",
    "Jeux & Jouets": "🧸",
    "Jouets": "🧸",
    "Enfants": "🧸",
    "Sport": "⚽",
    "Sport & Loisirs": "⚽",
    "Instruments de Musique": "🎸",
    # Work & misc
    "Fournitures de Bureau": "📎",
    "Mobilité & Transport": "🚗",
    "Auto & Moto": "🚗",
    "Supérette & Épicerie": "🛒",
    "Épicerie": "🛒",
    "Animalerie": "🐾",
    "Jardin": "🌱",
    "Bricolage": "🔨",
    "Made in Tunisia": "🇹🇳",
    "High-Tech": "🚀",
    "Soldes": "🔥",
    "Best-sellers": "⭐",
    "General": "📦",
}

DEFAULT_ICON = "📦"


def icon_for(category_name):
    """Return the emoji tile for a category name (never empty)."""
    return CATEGORY_ICONS.get((category_name or "").strip(), DEFAULT_ICON)
