from aiogram import Router, F
from aiogram.types import Message
from handlers.BotAutomaticWork.DataBase.ConnectDataBase.PoolConnectionPostgreSQL import get_db_pool
from BotAutomaticWork.users.checks.acces_commands.check_access_rang import check_user_access
import  logging

setting_help_online = Router()  # Используй свой существующий роутер
logger = logging.getLogger(__name__)

@setting_help_online.message(F.text == "+помощь")
async def agent_turn_on(message: Message):
    """Включает агента в список действующих (acting_agents)"""
    try:
        user_id = message.from_user.id

        if not await check_user_access(user_id, 1):
            return

        pool = get_db_pool()

        async with pool.acquire() as conn:
            # Проверяем, существует ли уже агент в таблице
            exists = await conn.fetchval(
                'SELECT 1 FROM acting_agents WHERE acting_agent_id = $1',
                user_id
            )

            if not exists:
                # Если агента вообще нет в таблице, добавляем со статусом TRUE
                await conn.execute(
                    'INSERT INTO acting_agents (acting_agent_id, online) VALUES ($1, TRUE)',
                    user_id
                )
            else:
                # Если агент уже есть (был выключен), просто меняем статус на TRUE
                await conn.execute(
                    'UPDATE acting_agents SET online = TRUE WHERE acting_agent_id = $1',
                    user_id
                )

        await message.reply(
            "✅ Вы добавлены в список действующих агентов и теперь отображаетесь в приветственном сообщении.")
    except Exception as e:
        logger.error(f"Ошибка в команде +помощь: {e}", exc_info=True)
        await message.reply("❌ Не удалось войти в режим дежурства. Попробуйте позже.")


@setting_help_online.message(F.text == "-помощь")
async def agent_turn_off(message: Message):
    """Исключает агента из списка действующих (acting_agents)"""
    try:
        user_id = message.from_user.id

        if not await check_user_access(user_id, 1):
            return

        pool = get_db_pool()

        async with pool.acquire() as conn:
            # Просто меняем статус на False, сохраняя агента в базе
            await conn.execute(
                'UPDATE acting_agents SET online = FALSE WHERE acting_agent_id = $1',
                user_id
            )

        await message.reply(
            "❌ Вы удалены из списка действующих агентов. Вы больше не отображаетесь в приветственном сообщении.")
    except Exception as e:
        logger.error(f"Ошибка в команде -помощь: {e}", exc_info=True)
        await message.reply("❌ Не удалось выйти из режима дежурства. Попробуйте позже.")