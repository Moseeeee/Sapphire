import re

REF_LINK_PATTERNS = [
    r't\.me\/\+[\w-]+',  # реферальные ссылки типа t.me/+
    r't\.me\/[\w]+\?start=[\w]+',  # реферальные ссылки с start параметром
    r't\.me\/(?:[\w]+\/)?[\w]+\?startapp=[\w]+',  # реферальные ссылки с startapp
    r't\.g\.me\/[\w]+\/[\w]+',  # t.g.me ссылки
    r't\.me\/(?:joinchat|\\+)[\w-]+'  # инвайт-ссылки в чаты
]



def contains_ref_links(text):
    """Проверяет текст на наличие реферальных или инвайт-ссылок"""
    if not text:
        return False

    text_lower = text.lower()

    # Проверяем по регулярным выражениям
    for pattern in REF_LINK_PATTERNS:
        if re.search(pattern, text_lower):
            return True


    return False