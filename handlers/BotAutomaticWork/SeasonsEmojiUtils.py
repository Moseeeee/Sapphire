from datetime import date

# === 1. Твои эмодзи-наборы ===
EMOJI_SETS = {
    "warn_emoji": {"winter": "🥶", "spring": "🚫", "summer": "🚫", "autumn": "🚫"},
    # добавляй сколько угодно!
}

# === 2. Определяем сезон ОДИН РАЗ в день ===
def _get_season():
    month = date.today().month
    if month in (12, 1, 2):
        return "winter"
    elif month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    else:
        return "autumn"

# === 3. Кешируем сезон, чтобы не вызывать дату на каждый запрос ===
_cached_season = None
_cached_date = None

def get_season():
    global _cached_season, _cached_date
    today = date.today()
    if _cached_date != today:
        _cached_season = _get_season()
        _cached_date = today
    return _cached_season

# === 4. Главная функция: получи эмодзи по имени набора ===
def get_emoji(key: str) -> str:
    season = get_season()
    emoji_dict = EMOJI_SETS.get(key)
    if emoji_dict is None:
        return "❓"  # или raise KeyError
    return emoji_dict.get(season, "❓")