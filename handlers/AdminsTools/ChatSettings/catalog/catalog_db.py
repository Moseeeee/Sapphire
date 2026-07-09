import logging
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool

logger = logging.getLogger(__name__)

# БЫСТРЫЙ СЛОВАРЬ КАТЕГОРИЙ В RAM (Заменяет старую таблицу в БД)
CATALOG_CATEGORIES = {
    1: {"name": "Спорт", "emoji": "⚽"},
    2: {"name": "IT", "emoji": "💻"},
    3: {"name": "Игры", "emoji": "🎮"},
    4: {"name": "Общение", "emoji": "💬"},
    5: {"name": "Музыка", "emoji": "🎵"},
    6: {"name": "Кино", "emoji": "🎬"},
    7: {"name": "Юмор", "emoji": "😂"},
    8: {"name": "Аниме", "emoji": "🏮"},
    9: {"name": "Ролевые (RP)", "emoji": "🎭"},
    10: {"name": "Знакомства", "emoji": "❤️"},
    11: {"name": "Новости", "emoji": "📰"},
    12: {"name": "Политика", "emoji": "🏛"},
    13: {"name": "Искусство", "emoji": "🎨"},
    14: {"name": "Литература", "emoji": "📚"},
    15: {"name": "Фотография", "emoji": "📸"},
    16: {"name": "Авто & Мото", "emoji": "🚗"},
    17: {"name": "Рыбалка", "emoji": "🎣"},
    18: {"name": "Кулинария", "emoji": "🍳"},
    19: {"name": "Путешествия", "emoji": "✈️"},
    20: {"name": "Животные", "emoji": "🐾"},
    21: {"name": "Наука", "emoji": "🧪"},
    22: {"name": "Психология", "emoji": "🧠"},
    23: {"name": "Криптовалюта", "emoji": "💎"},
    24: {"name": "Бизнес", "emoji": "💼"},
    25: {"name": "Нейросети", "emoji": "🤖"},
    26: {"name": "Финансы", "emoji": "💰"},
    27: {"name": "Здоровье", "emoji": "🍏"},
    28: {"name": "Работа", "emoji": "📝"},
    29: {"name": "Барахолка", "emoji": "📦"},
    30: {"name": "Городские чаты", "emoji": "🏙"},
    31: {"name": "Киберспорт", "emoji": "🖱"},
    32: {"name": "18+", "emoji": "🔞"}
}


async def init_catalog_tables():
    """Инициализация и мягкая миграция структуры таблицы каталога."""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        # Создаем таблицу чатов (категории хранятся внутри массива INT[])
        await conn.execute('''
        CREATE TABLE IF NOT EXISTS catalog_chats (
            chat_id BIGINT PRIMARY KEY,
            owner_id BIGINT NOT NULL,
            category_ids INT[] DEFAULT '{}',
            description TEXT,
            status TEXT DEFAULT 'draft',
            hide_admins BOOLEAN DEFAULT FALSE,
            is_private_link BOOLEAN DEFAULT FALSE,
            hide_stats BOOLEAN DEFAULT FALSE,
            title TEXT,
            username TEXT,
            member_count INT DEFAULT 0,
            invite_link TEXT,
            rating INT DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        ''')

        # Мягкие миграции на случай, если у тебя уже была создана старая версия таблицы
        await conn.execute('''
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS title TEXT;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS username TEXT;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS member_count INT DEFAULT 0;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS invite_link TEXT;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS category_ids INT[] DEFAULT '{}';
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS hide_admins BOOLEAN DEFAULT FALSE;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS is_private_link BOOLEAN DEFAULT FALSE;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS hide_stats BOOLEAN DEFAULT FALSE;
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft';
            ALTER TABLE catalog_chats ADD COLUMN IF NOT EXISTS rating INT DEFAULT 0;
        ''')


async def update_chat_catalog_draft(chat_id: int, owner_id: int, description: str, title: str, username: str,
                                    member_count: int, invite_link: str):
    """Добавляет чат или обновляет его базовые метаданные при вызове команды +каталог."""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO catalog_chats (chat_id, owner_id, description, title, username, member_count, invite_link, category_ids) 
            VALUES ($1, $2, $3, $4, $5, $6, $7, '{}')
            ON CONFLICT (chat_id) DO UPDATE SET 
                description = EXCLUDED.description,
                title = EXCLUDED.title,
                username = EXCLUDED.username,
                member_count = EXCLUDED.member_count,
                invite_link = EXCLUDED.invite_link
        ''', chat_id, owner_id, description, title, username, member_count, invite_link)


async def set_catalog_param(chat_id: int, column: str, value: any):
    """Универсальный апдейтер любого флага или поля в таблице каталога."""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE catalog_chats SET {column} = $1 WHERE chat_id = $2", value, chat_id)


async def get_catalog_chat(chat_id: int):
    """Получить полную запись чата из каталога."""
    pool = get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM catalog_chats WHERE chat_id = $1", chat_id)