import asyncio
import logging
import re
import html
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Tuple, Dict, Any, List

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from handlers.BotAutomaticWork.users.GenderUtils import g
from handlers.BotAutomaticWork.users.checks.acces_commands.check_access_rang import auto_check_AccessLevel_for_rang
from handlers.BotAutomaticWork.users.checks.check_users_id import resolve_id
from handlers.BotAutomaticWork.users.links.usersLinksUtils.users_global_link import user_link_with_pseudonym
from handlers.UserCommands.SettingsUsersProfile.GenderSettings.GenderSettingsDB import get_user_gender

# Настройка логирования
logger = logging.getLogger(__name__)

RP = Router()

# Константы
DISABLED_RATING = -1
MAX_COMMENT_LENGTH = 256
MAX_CLARIFICATION_LENGTH = 100
COMMAND_PREFIXES = ('!', '.', '/')
CACHE_CLEANUP_INTERVAL = 3600  # 1 час в секундах
CACHE_MAX_AGE = 7200  # 2 часа в секундах


class AgeRating(Enum):
    """Возрастные рейтинги"""
    ZERO_PLUS = 0
    THIRTEEN_PLUS = 13
    EIGHTEEN_PLUS = 18
    DISABLED = DISABLED_RATING


class RPCommand:
    """Класс для представления RP команды"""

    def __init__(self, base_command: str, data: Dict[str, Any]):
        self.base_command = base_command
        self.emoji = data["emoji"]
        self.action_template = data["action"]
        self.rating = data["rating"]

    def get_action(self, gender: str) -> str:
        """Получить действие с учетом пола"""
        return re.sub(r"g\('([^']+)'\)", lambda m: g(m.group(1), gender), self.action_template)


RP_COMMANDS_DATA = {
    # === ФИЗИЧЕСКИЕ ДЕЙСТВИЯ (0+) ===
    'пнуть': {"emoji": "👢", "action": "пнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'кик': {"emoji": "👢", "action": "пнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'толкнуть': {"emoji": "🤜", "action": "толкнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'дать пять': {"emoji": "✋", "action": "даg('ал') пять", "rating": AgeRating.ZERO_PLUS.value},
    'помахать': {"emoji": "👋", "action": "помахg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'погрозить пальцем': {"emoji": "☝️", "action": "погрозg('ил') пальцем", "rating": AgeRating.ZERO_PLUS.value},
    'показать язычок': {"emoji": "😛", "action": "показg('ал') язычок", "rating": AgeRating.ZERO_PLUS.value},
    'покрутить в воздухе': {"emoji": "🌀", "action": "покрутg('ил') в воздухе", "rating": AgeRating.ZERO_PLUS.value},
    'предложить руку': {"emoji": "🤝", "action": "предложg('ил') руку", "rating": AgeRating.ZERO_PLUS.value},
    'погладить по голове': {"emoji": "🫶", "action": "погладg('ил') по голове", "rating": AgeRating.ZERO_PLUS.value},
    'пощекотать подбородок': {"emoji": "😏", "action": "пощекотg('ал') подбородок", "rating": AgeRating.ZERO_PLUS.value},
    'пожелать спокойной ночи': {"emoji": "🌙", "action": "пожелg('ал') спокойной ночи", "rating": AgeRating.ZERO_PLUS.value},
    'пожелать удачи': {"emoji": "🍀", "action": "пожелg('ал') удачи", "rating": AgeRating.ZERO_PLUS.value},
    'показать звезду': {"emoji": "🌟", "action": "показg('ал') звезду", "rating": AgeRating.ZERO_PLUS.value},
    'сделать комплимент': {"emoji": "✨", "action": "сделg('ал') комплимент", "rating": AgeRating.ZERO_PLUS.value},
    'поднять на руки': {"emoji": "🫶", "action": "поднg('ял') на руки", "rating": AgeRating.ZERO_PLUS.value},
    'бросить в снег': {"emoji": "❄️", "action": "бросg('ил') в снег", "rating": AgeRating.ZERO_PLUS.value},
    'подбросить вверх': {"emoji": "🤸", "action": "подбросg('ил') вверх", "rating": AgeRating.ZERO_PLUS.value},
    'покрутить за руку': {"emoji": "🕺", "action": "покрутg('ил') за руку", "rating": AgeRating.ZERO_PLUS.value},
    'пощекотать живот': {"emoji": "🤣", "action": "пощекотg('ал') живот", "rating": AgeRating.ZERO_PLUS.value},
    'слегка толкнуть плечом': {"emoji": "🤏", "action": "слегка толкнg('ул') плечом", "rating": AgeRating.ZERO_PLUS.value},

    # === ЛАСКОВЫЕ ДЕЙСТВИЯ (0+) ===
    'погладить': {"emoji": "🤗", "action": "погладg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'обнять': {"emoji": "🫂", "action": "обнg('ял')", "rating": AgeRating.ZERO_PLUS.value},
    'обрыгать': {"emoji": "🤢", "action": "обрыгg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'понюхать': {"emoji": "👃", "action": "понюхg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'посадить на ручки': {"emoji": "👑", "action": "посадg('ил') на ручки", "rating": AgeRating.ZERO_PLUS.value},
    'покормить': {"emoji": "🍕", "action": "покормg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'согреть': {"emoji": "🔥", "action": "согреg('л')", "rating": AgeRating.ZERO_PLUS.value},  # окончание 1 буква, но 'л' - исключение

    # === ВЕСЁЛЫЕ ДЕЙСТВИЯ (0+) ===
    'подмигнуть': {"emoji": "😉", "action": "подмигнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'пощекотать': {"emoji": "😆", "action": "пощекотg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'испугать': {"emoji": "😱", "action": "испугg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'пожать руку': {"emoji": "🤝", "action": "пожg('ал') руку", "rating": AgeRating.ZERO_PLUS.value},
    'подставить щёку': {"emoji": "😊", "action": "подставg('ил') щёку", "rating": AgeRating.ZERO_PLUS.value},

    # === ДРАМАТИЧЕСКИЕ ДЕЙСТВИЯ (0+) ===
    'простить': {"emoji": "🤍", "action": "простg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'спасти': {"emoji": "🛡️", "action": "спg('ас')", "rating": AgeRating.ZERO_PLUS.value},  # окончание 2 буквы 'ас'
    'вылечить': {"emoji": "💊", "action": "вылечg('ил')", "rating": AgeRating.ZERO_PLUS.value},

    # === ЕДА / НАПИТКИ (0+) ===
    'напоить': {"emoji": "🍵", "action": "напоg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'угостить': {"emoji": "🍰", "action": "угостg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'угостить чаем': {"emoji": "☕", "action": "угостg('ил') чаем", "rating": AgeRating.ZERO_PLUS.value},

    # === СПЕЦИАЛЬНЫЕ (0+) ===
    'похвалить': {"emoji": "⭐", "action": "похвалg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'поблагодарить': {"emoji": "🙏", "action": "поблагодарg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'поздравить': {"emoji": "🎉", "action": "поздравg('ил')", "rating": AgeRating.ZERO_PLUS.value},

    # === ЭМОЦИИ И ВЫРАЖЕНИЯ ЛИЦА (0+) ===
    'засмеяться': {"emoji": "😂", "action": "засмеяg('лся')", "rating": AgeRating.ZERO_PLUS.value},  # 3 буквы 'лся' - исключение
    'заплакать': {"emoji": "😢", "action": "заплакg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'вздохнуть': {"emoji": "😮‍💨", "action": "вздохнg('ул')", "rating": AgeRating.ZERO_PLUS.value},
    'закатить глаза': {"emoji": "🙄", "action": "закатg('ил') глаза", "rating": AgeRating.ZERO_PLUS.value},
    'нахмуриться': {"emoji": "😠", "action": "нахмуриg('лся')", "rating": AgeRating.ZERO_PLUS.value},  # 3 буквы 'лся' - исключение
    'улыбнуться': {"emoji": "🙂", "action": "улыбнуg('лся')", "rating": AgeRating.ZERO_PLUS.value},  # 3 буквы 'лся' - исключение
    'сделать сердечко руками': {"emoji": "🫶", "action": "сделg('ал') сердечко руками", "rating": AgeRating.ZERO_PLUS.value},
    'покраснеть': {"emoji": "😳", "action": "покраснg('ел')", "rating": AgeRating.ZERO_PLUS.value},
    'посмотреть снизу вверх': {"emoji": "🥺", "action": "посмотрg('ел') снизу вверх", "rating": AgeRating.ZERO_PLUS.value},

    # === ИГРОВЫЕ / ШУТЛИВЫЕ (0+) ===
    'притвориться мертвым': {"emoji": "💀", "action": "притвориg('лся') мёртвым", "rating": AgeRating.ZERO_PLUS.value},  # 3 буквы 'лся' - исключение
    'подмигнуть дважды': {"emoji": "😉", "action": "подмигнg('ул') дважды", "rating": AgeRating.ZERO_PLUS.value},
    'сыграть в прятки': {"emoji": "🙈", "action": "сыгрg('ал') в прятки", "rating": AgeRating.ZERO_PLUS.value},
    'показать фокус': {"emoji": "🎩", "action": "показg('ал') фокус", "rating": AgeRating.ZERO_PLUS.value},
    'сыграть на воображаемой скрипке': {"emoji": "🎻", "action": "сыгрg('ал') на воображаемой скрипке", "rating": AgeRating.ZERO_PLUS.value},
    'изобразить призрака': {"emoji": "👻", "action": "изобразg('ил') призрака", "rating": AgeRating.ZERO_PLUS.value},
    'притвориться спящим': {"emoji": "😴", "action": "притвориg('лся') спящим", "rating": AgeRating.ZERO_PLUS.value},  # 3 буквы 'лся' - исключение

    # === ПОДДЕРЖКА И ЗАБОТА (0+) ===
    'спрятать': {"emoji": "🙈", "action": "спрятg('ал')", "rating": AgeRating.ZERO_PLUS.value},
    'накинуть пальто': {"emoji": "🧥", "action": "накинg('ул') пальто", "rating": AgeRating.ZERO_PLUS.value},
    'успокоить': {"emoji": "🕊️", "action": "успокоg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'ободрить': {"emoji": "💪", "action": "ободрg('ил')", "rating": AgeRating.ZERO_PLUS.value},
    'прикрыть одеялом': {"emoji": "🛏️", "action": "прикрg('ыл') одеялом", "rating": AgeRating.ZERO_PLUS.value},
    'дать плед': {"emoji": "🧣", "action": "дg('ал') плед", "rating": AgeRating.ZERO_PLUS.value},
    'предложить чай': {"emoji": "☕", "action": "предложg('ил') чай", "rating": AgeRating.ZERO_PLUS.value},

    # === ПРИРОДНЫЕ / АТМОСФЕРНЫЕ (0+) ===
    'показать радугу': {"emoji": "🌈", "action": "показg('ал') радугу", "rating": AgeRating.ZERO_PLUS.value},
    'собрать листочки': {"emoji": "🍂", "action": "собрg('ал') листочки", "rating": AgeRating.ZERO_PLUS.value},
    'поймать снежинку': {"emoji": "❄️", "action": "поймg('ал') снежинку", "rating": AgeRating.ZERO_PLUS.value},
    'выпустить бабочку': {"emoji": "🦋", "action": "выпустg('ил') бабочку", "rating": AgeRating.ZERO_PLUS.value},
    'посадить цветок': {"emoji": "🌱", "action": "посадg('ил') цветок", "rating": AgeRating.ZERO_PLUS.value},

    # === АБСТРАКТНЫЕ / СИМВОЛИЧЕСКИЕ (0+) ===
    'передать мысль': {"emoji": "💭", "action": "передg('ал') мысль", "rating": AgeRating.ZERO_PLUS.value},
    'нарисовать в воздухе сердце': {"emoji": "❤️", "action": "нарисовg('ал') в воздухе сердце", "rating": AgeRating.ZERO_PLUS.value},
    'бросить монетку': {"emoji": "🪙", "action": "бросg('ил') монетку", "rating": AgeRating.ZERO_PLUS.value},
    'зажечь свечу': {"emoji": "🕯️", "action": "зажg('ёг') свечу", "rating": AgeRating.ZERO_PLUS.value},
    'открыть дверь в будущее': {"emoji": "🚪", "action": "открg('ыл') дверь в будущее", "rating": AgeRating.ZERO_PLUS.value},

    # === ТЕАТРАЛЬНЫЕ / ДРАМАТИЧНЫЕ (13+) ===
    'ударить': {"emoji": "👊", "action": "ударg('ил')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'шлепнуть': {"emoji": "👋", "action": "шлёпнg('ул')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'укусить': {"emoji": "🦷", "action": "укусg('ил')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'пощечина': {"emoji": "😮", "action": "даg('ал') пощечину", "rating": AgeRating.THIRTEEN_PLUS.value},
    'дать пощёчину': {"emoji": "😮", "action": "даg('ал') пощечину", "rating": AgeRating.THIRTEEN_PLUS.value},
    'поцеловать': {"emoji": "💋", "action": "поцеловg('ал')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'приласкать': {"emoji": "🥰", "action": "приласкg('ал')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'предать': {"emoji": "🗡️", "action": "предg('ал')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'пленить': {"emoji": "🦊", "action": "пленg('ил')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'пригласить на свидание': {"emoji": "💌", "action": "пригласg('ил') на свидание", "rating": AgeRating.THIRTEEN_PLUS.value},
    'сделать предложение': {"emoji": "💍", "action": "сделg('ал') предложение", "rating": AgeRating.THIRTEEN_PLUS.value},
    'облизать': {"emoji": "👅", "action": "облизнg('ул')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'прижаться': {"emoji": "💞", "action": "прижаg('лся')", "rating": AgeRating.THIRTEEN_PLUS.value},  # 3 буквы 'лся' - исключение
    'шепнуть на ухо': {"emoji": "👂", "action": "шепнg('ул') на ухо", "rating": AgeRating.THIRTEEN_PLUS.value},
    'прижать к стене': {"emoji": "🧱", "action": "прижg('ал') к стене", "rating": AgeRating.THIRTEEN_PLUS.value},
    'обнять сзади': {"emoji": "🫂", "action": "обнg('ял') сзади", "rating": AgeRating.THIRTEEN_PLUS.value},
    'пощупать': {"emoji": "👀", "action": "пощупg('ал')", "rating": AgeRating.THIRTEEN_PLUS.value},
    'прижать к груди': {"emoji": "💞", "action": "прижg('ал') к груди", "rating": AgeRating.THIRTEEN_PLUS.value},
    'обнять за талию': {"emoji": "🫂", "action": "обнg('ял') за талию", "rating": AgeRating.THIRTEEN_PLUS.value},
    'провести рукой по волосам': {"emoji": "💆", "action": "провg('ёл') рукой по волосам", "rating": AgeRating.THIRTEEN_PLUS.value},
    'раскрыть тайну': {"emoji": "🤫", "action": "раскрg('ыл') тайну", "rating": AgeRating.THIRTEEN_PLUS.value},
    'упасть на колени': {"emoji": "🥹", "action": "упg('ал') на колени", "rating": AgeRating.THIRTEEN_PLUS.value},
    'произнести монолог': {"emoji": "🎭", "action": "произнg('ёс') монолог", "rating": AgeRating.THIRTEEN_PLUS.value},
    'взорваться эмоциями': {"emoji": "💥", "action": "взорваg('лся') эмоциями", "rating": AgeRating.THIRTEEN_PLUS.value},  # 3 буквы 'лся' - исключение
    'поцеловать в лоб': {"emoji": "💋", "action": "поцеловg('ал') в лоб", "rating": AgeRating.ZERO_PLUS.value},
    'поцеловать в щёку': {"emoji": "💋", "action": "поцеловg('ал') в щёку", "rating": AgeRating.ZERO_PLUS.value},
    'поцеловать в нос': {"emoji": "👃", "action": "поцеловg('ал') в нос", "rating": AgeRating.ZERO_PLUS.value},

    # === ЖЁСТКОЕ НАСИЛИЕ (18+) ===
    'избить': {"emoji": "💢", "action": "избg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'задушить': {"emoji": "🫁", "action": "задушg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'пытать': {"emoji": "🔪", "action": "пытg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'изнасиловать': {"emoji": "⛓️", "action": "изнасиловg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'разорвать': {"emoji": "💔", "action": "разорвg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'растерзать': {"emoji": "🧸", "action": "растерзg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'перерезать горло': {"emoji": "🩸", "action": "перерезg('ал') горло", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выколоть глаза': {"emoji": "👁️", "action": "выколg('ол') глаза", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'сломать кости': {"emoji": "🦴", "action": "сломg('ал') кости", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отрезать руку': {"emoji": "✂️", "action": "отрезg('ал') руку", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'привязать к стулу': {"emoji": "🪑", "action": "привязg('ал') к стулу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'заклеймить': {"emoji": "🔥", "action": "заклеймg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'изуродовать': {"emoji": "🧟", "action": "изуродовg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'заковать в цепи': {"emoji": "⛓️", "action": "заковg('ал') в цепи", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'бросить в яму': {"emoji": "🕳️", "action": "бросg('ил') в яму", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'залить кислотой': {"emoji": "🧪", "action": "залg('ил') кислотой", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'сжечь заживо': {"emoji": "🔥", "action": "сжёg('г') заживо", "rating": AgeRating.EIGHTEEN_PLUS.value},  # окончание 1 буква 'г' - исключение
    'утопить': {"emoji": "💧", "action": "утопg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'повесить': {"emoji": "🪢", "action": "повесg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'распять': {"emoji": "✝️", "action": "распg('ял')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'четвертовать': {"emoji": "🪓", "action": "четвертовg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отрубить голову': {"emoji": "⚔️", "action": "отрубg('ил') голову", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'вырвать сердце': {"emoji": "❤️‍🔥", "action": "вырвg('ал') сердце", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'содрать кожу': {"emoji": "🧻", "action": "содрg('ал') кожу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'ослепить': {"emoji": "🕶️", "action": "ослепg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'обезглавить': {"emoji": "🗡️", "action": "обезглавg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'раздавить': {"emoji": "🐍", "action": "раздавg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'заткнуть рот': {"emoji": "🤐", "action": "заткнg('ул') рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'закопать заживо': {"emoji": "⚰️", "action": "закопg('ал') заживо", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выпустить кишки': {"emoji": "🪱", "action": "выпустg('ил') кишки", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'переломать ноги': {"emoji": "🦵", "action": "переломg('ал') ноги", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'сломать позвоночник': {"emoji": "⚡", "action": "сломg('ал') позвоночник", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'разбить голову': {"emoji": "💥", "action": "разбg('ил') голову", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выбить зубы': {"emoji": "😁", "action": "выбg('ил') зубы", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'проломить череп': {"emoji": "🧠", "action": "проломg('ил') череп", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'замуровать': {"emoji": "🧱", "action": "замуровg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'распороть живот': {"emoji": "🪡", "action": "распорg('ол') живот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выжечь глаза': {"emoji": "🔥", "action": "выжg('ёг') глаза", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отрезать уши': {"emoji": "👂", "action": "отрезg('ал') уши", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'размозжить голову': {"emoji": "🔨", "action": "размозжg('ил') голову", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'забить до смерти': {"emoji": "🪦", "action": "забg('ил') до смерти", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'сбросить с обрыва': {"emoji": "🏔️", "action": "сбросg('ил') с обрыва", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'прибить гвоздями': {"emoji": "🔩", "action": "прибg('ил') гвоздями", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выкрутить руки': {"emoji": "🦾", "action": "выкрутg('ил') руки", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'разорвать рот': {"emoji": "👄", "action": "разорвg('ал') рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'воткнуть нож в спину': {"emoji": "🔪", "action": "воткнg('ул') нож в спину", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'перерезать сухожилия': {"emoji": "🩻", "action": "перерезg('ал') сухожилия", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'разрезать язык': {"emoji": "👅", "action": "разрезg('ал') язык", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выколоть иглой': {"emoji": "🪡", "action": "выколg('ол') иглой", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отпилить ногу': {"emoji": "🪚", "action": "отпилg('ил') ногу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'съесть заживо': {"emoji": "🍖", "action": "съg('ел') заживо", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'утопить в болоте': {"emoji": "🪷", "action": "утопg('ил') в болоте", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засыпать песком': {"emoji": "⏳", "action": "засыпg('ал') песком", "rating": AgeRating.EIGHTEEN_PLUS.value},

    # === СЕКСУАЛЬНЫЕ (18+) ===
    'выебать': {"emoji": "🍆", "action": "выеbg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'оттрахать': {"emoji": "💦", "action": "оттрахg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'вставить': {"emoji": "🔞", "action": "вставg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засадить': {"emoji": "🍑", "action": "засадg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'иметь': {"emoji": "🔥", "action": "имg('ел')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'поиметь': {"emoji": "💢", "action": "поимg('ел')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отжарить': {"emoji": "🍳", "action": "отжарg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отшлёпать': {"emoji": "🖐️", "action": "отшлёпg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'вылизать': {"emoji": "👅", "action": "вылизg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отсосать': {"emoji": "🥤", "action": "отсосg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'взять в рот': {"emoji": "👄", "action": "взg('ял') в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'заглотить': {"emoji": "🥵", "action": "заглотg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'кончить': {"emoji": "💦", "action": "кончg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'спустить': {"emoji": "💧", "action": "спустg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'обкончать': {"emoji": "🌊", "action": "обкончg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'залить спермой': {"emoji": "🥛", "action": "залg('ил') спермой", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'вымазать спермой': {"emoji": "🎨", "action": "вымазg('ал') спермой", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отливать': {"emoji": "🚿", "action": "отливg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'обоссать': {"emoji": "💛", "action": "обоссg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'зассать': {"emoji": "💦", "action": "зассg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'нассать в рот': {"emoji": "👄", "action": "нассg('ал') в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'нассать на лицо': {"emoji": "😳", "action": "нассg('ал') на лицо", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'накакать': {"emoji": "💩", "action": "накакg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'измазать калом': {"emoji": "🤎", "action": "измазg('ал') калом", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выесть': {"emoji": "🍽️", "action": "выg('ел')", "rating": AgeRating.EIGHTEEN_PLUS.value},  # окончание 1 буква 'л' - исключение
    'вылизать киску': {"emoji": "😺", "action": "вылизg('ал') киску", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отлизать': {"emoji": "👅", "action": "отлизg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засунуть': {"emoji": "📥", "action": "засунg('ул')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засунуть в жопу': {"emoji": "🍑", "action": "засунg('ул') в жопу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засунуть в рот': {"emoji": "👄", "action": "засунg('ул') в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засунуть в пизду': {"emoji": "🌮", "action": "засунg('ул') в пизду", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засунуть руку': {"emoji": "🖐️", "action": "засунg('ул') руку", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'засунуть пальцы': {"emoji": "👆", "action": "засунg('ул') пальцы", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'раздвинуть ноги': {"emoji": "🦵", "action": "раздвинg('ул') ноги", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'раздвинуть ягодицы': {"emoji": "🍑", "action": "раздвинg('ул') ягодицы", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'запрокинуть ноги': {"emoji": "🦶", "action": "запрокинg('ул') ноги", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'привязать к кровати': {"emoji": "🛏️", "action": "привязg('ал') к кровати", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'связать руки': {"emoji": "🪢", "action": "связg('ал') руки", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'завязать глаза': {"emoji": "👀", "action": "завязg('ал') глаза", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'кляп в рот': {"emoji": "🔴", "action": "вставg('ил') кляп в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отшлёпать ремнём': {"emoji": "🪢", "action": "отшлёпg('ал') ремнём", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выпороть': {"emoji": "🪄", "action": "выпорg('ол')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отходить плёткой': {"emoji": "🐍", "action": "отходg('ил') плёткой", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отходить': {"emoji": "🪄", "action": "отходg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'оттрахать в жопу': {"emoji": "🍑", "action": "оттрахg('ал') в жопу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'оттрахать в рот': {"emoji": "👄", "action": "оттрахg('ал') в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'оттрахать в пизду': {"emoji": "🌮", "action": "оттрахg('ал') в пизду", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'иметь в жопу': {"emoji": "🍑", "action": "имg('ел') в жопу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'иметь в рот': {"emoji": "👄", "action": "имg('ел') в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'иметь в пизду': {"emoji": "🌮", "action": "имg('ел') в пизду", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выебать в жопу': {"emoji": "🍑", "action": "выebg('ал') в жопу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выебать в рот': {"emoji": "👄", "action": "выebg('ал') в рот", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выебать в пизду': {"emoji": "🌮", "action": "выebg('ал') в пизду", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выдрать': {"emoji": "🪵", "action": "выдрg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'выдрать в жопу': {"emoji": "🍑", "action": "выдрg('ал') в жопу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отодрать': {"emoji": "💢", "action": "отодрg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'отодрать в жопу': {"emoji": "🍑", "action": "отодрg('ал') в жопу", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'нагнуть': {"emoji": "🔄", "action": "нагнg('ул')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'нагнуть и выебать': {"emoji": "🔄🍆", "action": "нагнg('ул') и выebg('ал')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'раком поставить': {"emoji": "🐕", "action": "раком поставg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
    'четвереньки': {"emoji": "🦶", "action": "на четвереньки поставg('ил')", "rating": AgeRating.EIGHTEEN_PLUS.value},
}

# Создаем объекты команд
RP_COMMANDS = {key: RPCommand(key, value) for key, value in RP_COMMANDS_DATA.items()}

# Карта рейтингов для отображения
RATING_DISPLAY = {
    DISABLED_RATING: "❌ отключены",
    0: "0+ (для всех)",
    13: "13+ (для подростков)",
    18: "18+ (для взрослых)"
}

# Допустимые значения рейтингов
ALLOWED_RATINGS = [DISABLED_RATING, 0, 13, 18]


class CacheManager:
    """Менеджер кэша с автоматической очисткой"""

    def __init__(self):
        self.cache_usage = defaultdict(dict)
        self.last_cleanup = datetime.now()
        self.cache_stats = {"hits": 0, "misses": 0, "cleared": 0}
        self.ratings_cache = {}
        self.cache_lock = asyncio.Lock()

    async def start_cleanup_task(self):
        """Запустить задачу автоматической очистки кэша"""
        asyncio.create_task(self._periodic_cleanup())

    async def _periodic_cleanup(self):
        """Периодическая очистка устаревшего кэша"""
        while True:
            try:
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL)
                await self.cleanup_old_cache()
            except Exception as e:
                logger.error(f"Ошибка в задаче очистки кэша: {e}")

    async def cleanup_old_cache(self):
        """Очистка устаревших записей кэша"""
        try:
            current_time = datetime.now()

            async with self.cache_lock:
                keys_to_remove = []
                for chat_id, cache_data in self.ratings_cache.items():
                    if "timestamp" in cache_data:
                        cache_age = current_time - cache_data["timestamp"]
                        if cache_age > timedelta(seconds=CACHE_MAX_AGE):
                            keys_to_remove.append(chat_id)

                for key in keys_to_remove:
                    del self.ratings_cache[key]
                    self.cache_stats["cleared"] += 1

                if keys_to_remove:
                    logger.info(f"Кэш очищен. Очищено записей: {len(keys_to_remove)}")
                    self.last_cleanup = current_time

            self.log_cache_stats()

        except Exception as e:
            logger.error(f"Ошибка при очистке кэша: {e}")

    def log_cache_stats(self):
        """Логирование статистики использования кэша"""
        try:
            cache_size = len(self.ratings_cache)
            logger.debug(
                f"Кэш статистика: hits={self.cache_stats['hits']}, misses={self.cache_stats['misses']}, "
                f"cleared={self.cache_stats['cleared']}, currsize={cache_size}"
            )
        except Exception as e:
            logger.error(f"Ошибка логирования статистики кэша: {e}")

    def record_cache_hit(self, chat_id: int):
        """Запись попадания в кэш"""
        self.cache_stats["hits"] += 1
        self.cache_usage[chat_id]["last_access"] = datetime.now()

    def record_cache_miss(self, chat_id: int):
        """Запись промаха кэша"""
        self.cache_stats["misses"] += 1
        self.cache_usage[chat_id]["last_access"] = datetime.now()

    async def get_cached_rating(self, chat_id: int) -> Optional[int]:
        """Получить рейтинг из кэша"""
        async with self.cache_lock:
            cache_data = self.ratings_cache.get(chat_id)
            if cache_data and "rating" in cache_data:
                self.record_cache_hit(chat_id)
                return cache_data["rating"]
        return None

    async def set_cached_rating(self, chat_id: int, rating: int):
        """Установить рейтинг в кэш"""
        async with self.cache_lock:
            self.ratings_cache[chat_id] = {
                "rating": rating,
                "timestamp": datetime.now()
            }

    async def invalidate_cache(self, chat_id: int = None):
        """Инвалидировать кэш"""
        async with self.cache_lock:
            if chat_id is None:
                self.ratings_cache.clear()
            elif chat_id in self.ratings_cache:
                del self.ratings_cache[chat_id]


cache_manager = CacheManager()


class RPInputParser:
    """Парсер ввода для RP команд"""

    @staticmethod
    def clean_command(text: str) -> str:
        """Очистка команды от префиксов"""
        for prefix in COMMAND_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        return text.strip()

    @staticmethod
    def parse_text(text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Упрощенный парсер: первое слово - команда, второе - упоминание, остальное - уточнение
        """
        try:
            lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
            if not lines:
                return None, None, None, None

            command_line = RPInputParser.clean_command(lines[0])
            parts = command_line.split()

            if len(parts) < 1:
                return None, None, None, None

            base_command = parts[0].lower()
            normalized_command = base_command.replace(' ', '_')

            command_obj = None
            for cmd_key, cmd_obj in RP_COMMANDS.items():
                if normalized_command.startswith(cmd_key):
                    command_obj = cmd_obj
                    base_command = cmd_key
                    break

            if not command_obj:
                return None, None, None, None

            mention = parts[1] if len(parts) > 1 else None
            clarification = ' '.join(parts[2:]) if len(parts) > 2 else None
            comment = '\n'.join(lines[1:]) if len(lines) > 1 else None

            return base_command, mention, clarification, comment

        except Exception as e:
            logger.error(f"Ошибка парсинга RP команды: {e}", exc_info=True)
            return None, None, None, None


class RPChecker:
    """Класс для проверок RP команд"""

    @staticmethod
    async def ensure_rp_rating_column(pool) -> None:
        """Убедиться, что колонка min_rp_rating существует в таблице chats"""
        try:
            async with pool.acquire() as conn:
                column_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = 'chats' 
                        AND column_name = 'min_rp_rating'
                    )
                """)

                if not column_exists:
                    await conn.execute('''
                        ALTER TABLE chats 
                        ADD COLUMN IF NOT EXISTS min_rp_rating INTEGER DEFAULT 0
                    ''')
                    await conn.execute('''
                        UPDATE chats SET min_rp_rating = 0 WHERE min_rp_rating IS NULL
                    ''')
        except Exception as e:
            logger.error(f"Ошибка при проверке колонки min_rp_rating: {e}")
            raise

    @staticmethod
    async def get_cached_chat_rating(chat_id: int) -> int:
        """Получить кэшированный рейтинг чата"""
        cached_rating = await cache_manager.get_cached_rating(chat_id)
        if cached_rating is not None:
            return cached_rating

        cache_manager.record_cache_miss(chat_id)

        pool = get_db_pool()
        await RPChecker.ensure_rp_rating_column(pool)

        async with pool.acquire() as conn:
            rating = await conn.fetchval('''
                SELECT min_rp_rating FROM chats WHERE chat_id = $1
            ''', chat_id)

            if rating is None:
                await conn.execute('''
                    INSERT INTO chats (chat_id, min_rp_rating)
                    VALUES ($1, 0)
                    ON CONFLICT (chat_id) DO NOTHING
                ''', chat_id)
                rating = 0

            if rating not in ALLOWED_RATINGS:
                rating = 0
                await conn.execute('''
                    UPDATE chats SET min_rp_rating = $1 WHERE chat_id = $2
                ''', rating, chat_id)

        await cache_manager.set_cached_rating(chat_id, rating)
        return rating

    @staticmethod
    async def get_chat_rating_uncached(chat_id: int) -> int:
        """Получить рейтинг чата без использования кэша"""
        pool = get_db_pool()
        await RPChecker.ensure_rp_rating_column(pool)

        async with pool.acquire() as conn:
            rating = await conn.fetchval('''
                SELECT min_rp_rating FROM chats WHERE chat_id = $1
            ''', chat_id)

            if rating is None:
                await conn.execute('''
                    INSERT INTO chats (chat_id, min_rp_rating)
                    VALUES ($1, 0)
                    ON CONFLICT (chat_id) DO NOTHING
                ''', chat_id)
                rating = 0

            if rating not in ALLOWED_RATINGS:
                rating = 0
                await conn.execute('''
                    UPDATE chats SET min_rp_rating = $1 WHERE chat_id = $2
                ''', rating, chat_id)

        await cache_manager.invalidate_cache(chat_id)
        await cache_manager.set_cached_rating(chat_id, rating)
        return rating

    @staticmethod
    async def is_command_allowed(chat_id: int, command_rating: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Проверяет, разрешена ли RP-команда с данным рейтингом в чате"""
        try:
            chat_min_rating = await RPChecker.get_cached_chat_rating(chat_id)

            if chat_min_rating == DISABLED_RATING:
                return False, await RPChecker.get_rp_disabled_message(command_rating, chat_id)

            if command_rating <= chat_min_rating:
                return True, None

            return False, await RPChecker.get_rp_disabled_message(command_rating, chat_id)

        except Exception as e:
            logger.error(f"Ошибка проверки команды: {e}", exc_info=True)
            return False, {"text": "❌ Произошла ошибка при проверке разрешений"}

    @staticmethod
    async def get_rp_disabled_message(rating: int, chat_id: int) -> Dict[str, Any]:
        """Получить сообщение о том, что RP отключены"""
        rating_display = RATING_DISPLAY.get(rating, f"{rating}+")

        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"✅ Включить РП {rating_display}",
            callback_data=f"enable_rp:{rating}:{chat_id}"
        )
        builder.adjust(1)

        return {
            "text": f"❌ РП-команды отключены в этом чате.\nХотите включить РП-команды с рейтингом {rating_display}?",
            "reply_markup": builder.as_markup()
        }

    @staticmethod
    def validate_comment(comment: str) -> Tuple[bool, Optional[str]]:
        """Проверка комментария"""
        if len(comment) > MAX_COMMENT_LENGTH:
            return False, f'❌ Длина комментария не должна превышать {MAX_COMMENT_LENGTH} символов!'
        return True, None

    @staticmethod
    def validate_clarification(clarification: str) -> Tuple[bool, Optional[str]]:
        """Проверка уточнения"""
        if len(clarification) > MAX_CLARIFICATION_LENGTH:
            return False, f'❌ Длина уточнения не должна превышать {MAX_CLARIFICATION_LENGTH} символов!'
        return True, None


class RPUserResolver:
    """Класс для разрешения пользователей в RP командах"""

    @staticmethod
    async def resolve_target_user(m: Message, mention: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Получить целевого пользователя для RP-команды

        Приоритет:
        1. Ответ на сообщение (reply)
        2. Упоминание в тексте (через resolve_id)
        """
        try:
            target_id = None
            user_obj = None

            # 1. Проверяем reply (наивысший приоритет)
            if m.reply_to_message and m.reply_to_message.from_user:
                target_id = m.reply_to_message.from_user.id
                user_obj = m.reply_to_message.from_user
                logger.info(f"Найден target_id из reply: {target_id}")
                return {
                    'id': target_id,
                    'user_obj': user_obj
                }

            # 2. Если есть упоминание - передаем в resolve_id
            if mention:
                # Пробуем как есть
                target_id = await resolve_id(m, mention)

                if not target_id and mention.startswith('@'):
                    # Пробуем без @
                    alt_mention = mention[1:]
                    target_id = await resolve_id(m, alt_mention)

                if not target_id and '/' in mention:
                    # Пробуем извлечь username из ссылки
                    parts = mention.split('/')
                    last_part = parts[-1]
                    if '?' in last_part:
                        last_part = last_part.split('?')[0]
                    if last_part and len(last_part) > 1:
                        target_id = await resolve_id(m, f"@{last_part}")

                if target_id:
                    try:
                        # Пытаемся получить информацию о пользователе
                        chat_member = await m.bot.get_chat_member(m.chat.id, target_id)
                        user_obj = chat_member.user if hasattr(chat_member, 'user') else None
                    except Exception as e:
                        logger.debug(f"Не удалось получить chat_member: {e}")
                        # Создаем минимальный объект
                        user_obj = type('MinimalUser', (), {
                            'id': target_id,
                            'first_name': f"User",
                            'last_name': None,
                            'username': None
                        })()

                    return {
                        'id': target_id,
                        'user_obj': user_obj
                    }
                else:
                    logger.warning(f"resolve_id не смог разрешить: '{mention}'")
                    return None

            logger.info("Не удалось определить целевого пользователя")
            return None

        except Exception as e:
            logger.error(f"Ошибка разрешения пользователя: {e}", exc_info=True)
            return None

    @staticmethod
    def validate_users(admin_user, target_user) -> Tuple[bool, Optional[str]]:
        """Проверка пользователей"""
        if not target_user:
            return False, "❌ Не удалось определить пользователя"

        if admin_user.id == target_user['id']:
            return False, "❌ Нельзя взаимодействовать с самим собой!"

        return True, None


class RPFormatter:
    """Класс для форматирования RP сообщений"""

    @staticmethod
    async def format_rp_message(
            command: RPCommand,
            admin_id: int,
            target_user: Dict[str, Any],
            chat_id: int,
            clarification: Optional[str] = None,
            comment: Optional[str] = None
    ) -> str:
        """Форматировать RP-сообщение"""
        try:
            # Получаем пол администратора
            admin_gender = await get_user_gender(admin_id)

            # Получаем действие с учетом пола
            action = command.get_action(admin_gender)

            # Создаем ссылки
            admin_link = await user_link_with_pseudonym(admin_id, chat_id)
            admin_tag_link = f'<a href="tg://user?id={admin_id}">\u200e</a>'
            target_link = await user_link_with_pseudonym(target_user['id'], chat_id)
            tag_link = f'<a href="tg://user?id={target_user["id"]}">\u200e</a>'

            # Формируем сообщение
            message_parts = [f"{command.emoji} | {admin_link} {admin_tag_link}{action} {tag_link}{target_link}"]

            # Добавляем уточнение
            if clarification:
                RPFormatter._add_clarification(message_parts, clarification)

            # Добавляем комментарий
            if comment:
                RPFormatter._add_comment(message_parts, comment)

            return "\n".join(message_parts)

        except Exception as e:
            logger.error(f"Ошибка форматирования сообщения: {e}", exc_info=True)
            return "❌ Произошла ошибка при создании сообщения"

    @staticmethod
    def _add_clarification(message_parts: List[str], clarification: str) -> None:
        """Добавить уточнение к сообщению"""
        preposition_pattern = r'^(по|на|за|в|с|к|у|о|об|от|до|из|без|под|над|перед|при|про|через)\s+'

        if re.match(preposition_pattern, clarification.lower()):
            message_parts[0] += f" {clarification}"
        else:
            message_parts[0] += f". {clarification.capitalize()}"

    @staticmethod
    def _add_comment(message_parts: List[str], comment: str) -> None:
        """Добавить комментарий к сообщению"""
        if len(comment) > MAX_COMMENT_LENGTH:
            comment = comment[:MAX_COMMENT_LENGTH - 3] + "..."
        message_parts.append(f"💬 Комментарий: {comment}")


class RPSettingsHandler:
    """Обработчик настроек RP"""

    @staticmethod
    async def set_rp_rating(chat_id: int, rating: int) -> bool:
        """Установить рейтинг RP для чата"""
        try:
            if rating not in ALLOWED_RATINGS:
                return False

            pool = get_db_pool()
            await RPChecker.ensure_rp_rating_column(pool)

            async with pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO chats (chat_id, min_rp_rating)
                    VALUES ($1, $2)
                    ON CONFLICT (chat_id) 
                    DO UPDATE SET min_rp_rating = $2
                ''', chat_id, rating)

            await cache_manager.invalidate_cache(chat_id)
            return True

        except Exception as e:
            logger.error(f"Ошибка установки рейтинга RP: {e}", exc_info=True)
            return False

    @staticmethod
    def parse_rating_argument(arg: str) -> Tuple[bool, Optional[int]]:
        """Парсинг аргумента рейтинга"""
        try:
            rating_str = arg.strip()

            if not rating_str.isdigit():
                return False, None

            rating = int(rating_str)

            if rating >= 18:
                return True, 18
            elif rating >= 13:
                return True, 13
            else:
                return True, 0

        except Exception:
            return False, None


async def cleanup_cache_on_startup():
    """Запустить очистку кэша при старте"""
    await cache_manager.start_cleanup_task()
    logger.info("Задача автоматической очистки кэша запущена")


async def handle_rp_command(m: Message) -> None:
    """Основной обработчик RP команд"""
    try:
        chat_id = m.chat.id
        user_id = m.from_user.id
        text = m.text.strip()

        # Парсим команду
        base_command, mention, clarification, comment = RPInputParser.parse_text(text)

        if not base_command:
            return

        # Получаем объект команды
        command = RP_COMMANDS.get(base_command)
        if not command:
            return

        # Проверяем ограничения по рейтингу
        allowed, error_message = await RPChecker.is_command_allowed(chat_id, command.rating)

        if not allowed:
            if error_message:
                await m.answer(**error_message)
            return

        # Валидируем комментарий
        if comment:
            is_valid, error_msg = RPChecker.validate_comment(comment)
            if not is_valid:
                await m.answer(error_msg)
                return

        # Валидируем уточнение
        if clarification:
            is_valid, error_msg = RPChecker.validate_clarification(clarification)
            if not is_valid:
                await m.answer(error_msg)
                return

        # Получаем целевого пользователя
        target_user_data = await RPUserResolver.resolve_target_user(m, mention)

        if not target_user_data:
            error_text = "❌ Не удалось определить пользователя.\n\n"

            if mention:
                error_text += f"Указано: <code>{html.escape(mention)}</code>\n\n"
                error_text += "Возможные причины:\n"
                error_text += "• Пользователь не найден в базе данных бота\n"
                error_text += "• Неверный формат упоминания\n"
                error_text += "• Пользователь заблокировал бота\n\n"
                error_text += "Попробуйте:\n"
                error_text += "1. Ответить на сообщение пользователя\n"
                error_text += "2. Указать @никнейм\n"
                error_text += "3. Указать ID пользователя"
            else:
                error_text += "Укажите пользователя одним из способов:\n"
                error_text += "• Ответьте на сообщение пользователя\n"
                error_text += "• Напишите @никнейм\n"
                error_text += "• Укажите ID пользователя\n"
                error_text += "• Пришлите ссылку на профиль"

            await m.answer(error_text, parse_mode="HTML")
            return

        target_id = target_user_data['id']

        # Проверяем валидность пользователей
        is_valid, error_msg = RPUserResolver.validate_users(m.from_user, target_user_data)
        if not is_valid:
            await m.answer(error_msg)
            return

        # Форматируем и отправляем сообщение
        formatted_message = await RPFormatter.format_rp_message(
            command=command,
            admin_id=user_id,
            target_user=target_user_data,
            chat_id=chat_id,
            clarification=clarification,
            comment=comment
        )

        await m.answer(formatted_message, parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка обработки RP команды: {e}", exc_info=True)
        await m.answer("❌ Произошла ошибка при обработке команды")


@RP.message(F.text.regexp(r'^[+\-]?рп\b'))
async def handle_rp_settings_command(m: Message):
    """Обработчик команд управления настройками RP"""

    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 72):
        return

    try:
        text = m.text.strip().lower()

        # Команда отключения RP
        if text.startswith('-рп'):
            success = await RPSettingsHandler.set_rp_rating(m.chat.id, DISABLED_RATING)
            if success:
                await m.answer("✅ РП-команды отключены в этом чате")
            else:
                await m.answer("❌ Произошла ошибка при отключении РП")
            return

        # Убираем префикс + если есть
        if text.startswith('+рп'):
            text = 'рп' + text[3:]

        # Обработка команды установки рейтинга
        pattern = r'^рп\s+(.+)$'
        match = re.match(pattern, text, re.IGNORECASE)

        if not match:
            # Показываем текущие настройки
            current_rating = await RPChecker.get_cached_chat_rating(m.chat.id)
            current_display = RATING_DISPLAY.get(current_rating, f"{current_rating}+")

            builder = InlineKeyboardBuilder()
            builder.button(text="🔴 Отключить РП", callback_data="rp_settings:disable")
            builder.button(text="🟢 0+", callback_data="rp_settings:0")
            builder.button(text="🟡 13+", callback_data="rp_settings:13")
            builder.button(text="🔴 18+", callback_data="rp_settings:18")
            builder.adjust(2, 2)

            await m.answer(
                f"📊 Текущие настройки РП:\n"
                f"Рейтинг: {current_display}\n\n"
                f"Доступные команды:\n"
                f"• <code>+рп 0</code> - только детские команды\n"
                f"• <code>+рп 13</code> - + подростковые команды\n"
                f"• <code>+рп 18</code> - все РП команды\n"
                f"• <code>-рп</code> - отключить все РП",
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
            return

        args = match.group(1).strip()
        success, rating = RPSettingsHandler.parse_rating_argument(args.split()[0])

        if not success:
            await m.answer(
                "❌ Некорректный формат команды.\n\n"
                "Используйте:\n"
                "• <code>+рп 18</code> - разрешить все РП\n"
                "• <code>+рп 13</code> - разрешить РП 13+\n"
                "• <code>+рп 0</code> - разрешить только РП 0+\n"
                "• <code>-рп</code> - отключить все РП",
                parse_mode="HTML"
            )
            return

        success = await RPSettingsHandler.set_rp_rating(m.chat.id, rating)

        if success:
            rating_display = RATING_DISPLAY.get(rating, f"{rating}+")
            await m.answer(f"✅ Установлен рейтинг РП: {rating_display}")
        else:
            await m.answer("❌ Произошла ошибка при установке рейтинга")

    except Exception as e:
        logger.error(f"Ошибка обработки настроек RP: {e}", exc_info=True)
        await m.answer("❌ Произошла ошибка при обработке команды")


@RP.callback_query(F.data.startswith("enable_rp:"))
async def handle_enable_rp_callback(callback: CallbackQuery):
    """Обработчик callback для включения RP"""
    try:
        # Проверяем права доступа
        if not await auto_check_AccessLevel_for_rang(callback.from_user.id, callback.message.chat.id, 72):
            await callback.answer("❌ У вас нет прав для выполнения этого действия", show_alert=True)
            return

        data_parts = callback.data.split(":")
        if len(data_parts) != 3:
            await callback.answer("❌ Неверный формат данных", show_alert=True)
            return

        _, rating_str, chat_id_str = data_parts
        rating = int(rating_str)
        chat_id = int(chat_id_str)

        # Проверяем, что callback из того же чата
        if callback.message.chat.id != chat_id:
            await callback.answer("❌ Эта кнопка действительна только для этого чата", show_alert=True)
            return

        success = await RPSettingsHandler.set_rp_rating(chat_id, rating)

        if not success:
            await callback.answer("❌ Ошибка при включении РП", show_alert=True)
            return

        rating_display = RATING_DISPLAY.get(rating, f"{rating}+")
        admin_mention = callback.from_user.mention_html(callback.from_user.first_name)

        try:
            await callback.message.edit_text(
                f"✅ РП-команды включены!\n"
                f"Текущий рейтинг: {rating_display}\n\n"
                f"👮🏻 Администратор: {admin_mention}",
                parse_mode="HTML",
                reply_markup=None
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                await callback.answer("✅ Настройки уже применены")
                return
            raise

        await callback.answer(f"✅ РП рейтинг установлен: {rating_display}")

    except ValueError:
        await callback.answer("❌ Ошибка в данных", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка обработки enable_rp callback: {e}", exc_info=True)
        await callback.answer(f"❌ Произошла ошибка", show_alert=True)


@RP.callback_query(F.data.startswith("rp_settings:"))
async def handle_rp_settings_callback(callback: CallbackQuery):
    """Обработчик callback для быстрой настройки RP"""
    try:
        # Проверяем права доступа
        if not await auto_check_AccessLevel_for_rang(callback.from_user.id, callback.message.chat.id, 72):
            await callback.answer("❌ У вас нет прав для выполнения этого действия", show_alert=True)
            return

        action = callback.data.split(":")[1]

        if action == "disable":
            rating_to_set = DISABLED_RATING
            rating_display = "отключены"
        else:
            try:
                rating_to_set = int(action)
                rating_display = RATING_DISPLAY.get(rating_to_set, f"{rating_to_set}+")
            except ValueError:
                await callback.answer("❌ Неверное значение рейтинга", show_alert=True)
                return

        success = await RPSettingsHandler.set_rp_rating(callback.message.chat.id, rating_to_set)

        if not success:
            await callback.answer("❌ Ошибка при изменении настроек", show_alert=True)
            return

        try:
            await callback.message.edit_text(
                f"✅ Настройки РП обновлены!\n"
                f"Новый рейтинг: {rating_display}\n\n"
                f"👮🏻 Администратор: {callback.from_user.mention_html(callback.from_user.first_name)}",
                parse_mode="HTML",
                reply_markup=None
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                await callback.answer("✅ Настройки уже применены")
                return
            raise

        await callback.answer(f"✅ РП установлен: {rating_display}")

    except IndexError:
        await callback.answer("❌ Неверный формат данных", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка обработки rp_settings callback: {e}", exc_info=True)
        await callback.answer(f"❌ Произошла ошибка", show_alert=True)


# Регистрируем обработчик для всех RP команд
ALL_RP_COMMANDS = '|'.join(RP_COMMANDS.keys())
RP_PATTERN = rf'^[!./]?({ALL_RP_COMMANDS})(?:\s|$)'


@RP.message(F.text.regexp(RP_PATTERN, flags=re.IGNORECASE))
async def handle_all_rp_commands(m: Message):
    if not await auto_check_AccessLevel_for_rang(m.from_user.id, m.chat.id, 71):
        return

    """Обработчик всех RP-команд"""
    await handle_rp_command(m)


# Функция для тестирования ссылок
async def test_telegram_links():
    """Тестирование различных форматов ссылок Telegram"""
    test_cases = [
        "@username",
        "https://t.me/username",
        "t.me/username",
        "telegram.me/username",
        "tg://resolve?domain=username",
        "tg://user?id=123456789",
        "https://t.me/username?start=123",
        "https://t.me/username/456",
        "username",
        "123456789",
    ]

    logger.info("=== Тестирование форматов ссылок ===")
    for test_case in test_cases:
        logger.info(f"Тест: {test_case}")

    logger.info("=== Конец тестирования ===")