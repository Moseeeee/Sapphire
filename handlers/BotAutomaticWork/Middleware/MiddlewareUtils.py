import logging

from aiogram.types import (
    Message, CallbackQuery, ChatMemberUpdated,
    InlineQuery, ChosenInlineResult,
    ShippingQuery, PreCheckoutQuery, PollAnswer,
    ChatJoinRequest, Update
)
logger = logging.getLogger(__name__)

def extract_user_info(update_or_event):
    """Извлечь информацию о пользователе из Update или события"""
    logger.debug(f"🔍 Extracting user info from: {type(update_or_event).__name__}")

    user = None
    chat = None

    try:
        # Если это Update, извлекаем из него событие
        if isinstance(update_or_event, Update):
            event = None

            # Проверяем все возможные типы событий в Update
            if update_or_event.message:
                event = update_or_event.message
                logger.debug(f"  Found Message in Update")
            elif update_or_event.edited_message:
                event = update_or_event.edited_message
                logger.debug(f"  Found EditedMessage in Update")
            elif update_or_event.callback_query:
                event = update_or_event.callback_query
                logger.debug(f"  Found CallbackQuery in Update")
            elif update_or_event.chat_member:
                event = update_or_event.chat_member
                logger.debug(f"  Found ChatMemberUpdated in Update")
            elif update_or_event.my_chat_member:
                event = update_or_event.my_chat_member
                logger.debug(f"  Found MyChatMember in Update")
            elif update_or_event.chat_join_request:
                event = update_or_event.chat_join_request
                logger.debug(f"  Found ChatJoinRequest in Update")
            elif update_or_event.inline_query:
                event = update_or_event.inline_query
                logger.debug(f"  Found InlineQuery in Update")
            elif update_or_event.chosen_inline_result:
                event = update_or_event.chosen_inline_result
                logger.debug(f"  Found ChosenInlineResult in Update")
            elif update_or_event.shipping_query:
                event = update_or_event.shipping_query
                logger.debug(f"  Found ShippingQuery in Update")
            elif update_or_event.pre_checkout_query:
                event = update_or_event.pre_checkout_query
                logger.debug(f"  Found PreCheckoutQuery in Update")
            elif update_or_event.poll:
                event = update_or_event.poll
                logger.debug(f"  Found Poll in Update")
            elif update_or_event.poll_answer:
                event = update_or_event.poll_answer
                logger.debug(f"  Found PollAnswer in Update")
            elif update_or_event.chat_boost:
                event = update_or_event.chat_boost
                logger.debug(f"  Found ChatBoostUpdated in Update")
            elif update_or_event.removed_chat_boost:
                event = update_or_event.removed_chat_boost
                logger.debug(f"  Found RemovedChatBoost in Update")
            else:
                logger.warning(f"  No known event found in Update")
                return None

            if event:
                logger.debug(f"  Processing event type: {type(event).__name__}")
                return extract_user_info(event)  # Рекурсивно обрабатываем событие
            else:
                return None

        # Обработка конкретных типов событий
        elif isinstance(update_or_event, Message):
            user = update_or_event.from_user
            chat = update_or_event.chat
            logger.debug(f"  Message: user_id={user.id if user else 'None'}, chat_id={chat.id if chat else 'None'}")

        elif isinstance(update_or_event, CallbackQuery):
            user = update_or_event.from_user
            if update_or_event.message:
                chat = update_or_event.message.chat
            logger.debug(f"  CallbackQuery: user_id={user.id if user else 'None'}, chat={'has' if chat else 'no'} chat")

        elif isinstance(update_or_event, ChatMemberUpdated):
            # Получаем пользователя из new_chat_member
            if update_or_event.new_chat_member:
                user = update_or_event.new_chat_member.user
            elif update_or_event.old_chat_member:
                user = update_or_event.old_chat_member.user
            chat = update_or_event.chat
            logger.debug(
                f"  ChatMemberUpdated: user_id={user.id if user else 'None'}, chat_id={chat.id if chat else 'None'}")

        elif isinstance(update_or_event, ChatJoinRequest):
            user = update_or_event.from_user
            chat = update_or_event.chat
            logger.debug(
                f"  ChatJoinRequest: user_id={user.id if user else 'None'}, chat_id={chat.id if chat else 'None'}")

        elif isinstance(update_or_event, InlineQuery):
            user = update_or_event.from_user
            logger.debug(f"  InlineQuery: user_id={user.id if user else 'None'}")

        elif isinstance(update_or_event, ChosenInlineResult):
            user = update_or_event.from_user
            logger.debug(f"  ChosenInlineResult: user_id={user.id if user else 'None'}")

        elif isinstance(update_or_event, ShippingQuery):
            user = update_or_event.from_user
            logger.debug(f"  ShippingQuery: user_id={user.id if user else 'None'}")

        elif isinstance(update_or_event, PreCheckoutQuery):
            user = update_or_event.from_user
            logger.debug(f"  PreCheckoutQuery: user_id={user.id if user else 'None'}")

        elif isinstance(update_or_event, PollAnswer):
            user = update_or_event.user
            logger.debug(f"  PollAnswer: user_id={user.id if user else 'None'}")

        else:
            logger.warning(f"  Unsupported event type: {type(update_or_event).__name__}")
            return None

    except AttributeError as e:
        logger.warning(f"  AttributeError in extract_user_info: {e}")
        return None
    except Exception as e:
        logger.error(f"  Unexpected error in extract_user_info: {e}", exc_info=True)
        return None

    if not user or not user.id:
        logger.debug(f"  No valid user found: user={user}")
        return None

    # Очистка имени
    from handlers.BotAutomaticWork.users.links.clean_user_name import clean_name
    name = clean_name(user.first_name) if user.first_name else "Без имени"
    username = user.username
    chat_id = chat.id if chat else None

    logger.debug(f"✅ Extracted: user_id={user.id}, name={name[:20]}, "
                 f"username={username}, chat_id={chat_id}")

    return user.id, name, username, chat, chat_id
