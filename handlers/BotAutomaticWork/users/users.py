import logging
import os

from aiogram import Router


#from handlers.testDirectiry.save_video.save_video_web import detect_platform, download_clean_video
from handlers.BotAutomaticWork.BotCreatedGlobal import get_bot


logger = logging.getLogger(__name__)


users = Router()
bot = get_bot()

# downloader.py
import os
import asyncio
from urllib.parse import urlparse



SUPPORTED = {
    'youtube.com': 'YouTube',
    'youtu.be': 'YouTube',
    'tiktok.com': 'TikTok',
    'instagram.com': 'Instagram',
    'vk.com': 'VK',
    'pinterest.com': 'Pinterest',
    'pin.it': 'Pinterest',
}

def detect_platform(url: str) -> str:
    netloc = urlparse(url.lower()).netloc.replace('www.', '')
    for domain, name in SUPPORTED.items():
        if domain in netloc:
            return name
    raise ValueError("Неподдерживаемый URL")

def is_instagram_reel(url: str) -> bool:
    return any(x in url for x in ['/reel/', '/tv/', '/p/'])

async def compress_video(input_path: str) -> str:
    """Сжимает видео до <50 МБ с сохранением 1080p (если возможно)."""
    output_path = input_path.replace(".mp4", "_compressed.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-b:v", "2M", "-maxrate", "2M", "-bufsize", "4M",
        "-vf", "scale=1080:trunc(1080/dar/2)*2",  # сохраняем 1080 по высоте или ширине
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.communicate()
    if proc.returncode == 0 and os.path.exists(output_path):
        os.remove(input_path)
        return output_path
    else:
        raise RuntimeError("Не удалось сжать видео")




user_tasks = set()




#@users.message()
#async def handle_url(message: Message, bot: Bot):
