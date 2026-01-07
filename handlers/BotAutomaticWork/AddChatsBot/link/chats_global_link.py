from handlers.BotAutomaticWork.AddChatsBot.link.chat_global_linkDB import base_chats_info


async def chat_global_link(ChatId):
    chat_info_dict = await base_chats_info([ChatId])

    if not chat_info_dict or ChatId not in chat_info_dict:
        return "Чат не найден"

    chat_info = chat_info_dict[ChatId]
    chat_title = chat_info['title']
    chat_username = chat_info['username']
    invite_link = chat_info['invite_link']

    if chat_username:
        return f"<a href='https://t.me/{chat_username}'>{chat_title}</a>"
    elif invite_link:
        return f"<a href='{invite_link}'>{chat_title}</a>"
    else:
        return chat_title