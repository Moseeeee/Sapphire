import random
import string
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Tuple, Any


class CaptchaGenerator:
    def __init__(self):
        self.captcha_types = {
            'легкая': [
                'text_simple', 'text_letters', 'text_digits',
                'code_short', 'text_clean'
            ],
            'средняя': [
                'text_noise', 'text_lines', 'text_distorted',
                'code_medium', 'text_waves'
            ],
            'тяжелая': [
                'text_advanced', 'text_heavy_noise', 'text_warped',
                'code_long', 'text_multi_effect'
            ],
            'хардкорд': [
                'text_extreme', 'text_chaos', 'text_ultra_warped',
                'code_extreme', 'text_max_effect'
            ]
        }

        # Символы для капч
        self.letters = string.ascii_uppercase
        self.digits = string.digits
        self.symbols = '!@#$%&*+-=?'
        self.all_chars = self.letters + self.digits + self.symbols

    async def generate_captcha(self, difficulty: str) -> Tuple[str, Any, str]:
        """Генерирует случайную капчу в зависимости от сложности"""
        captcha_type = random.choice(self.captcha_types[difficulty])
        return await self._generate_text_captcha(captcha_type, difficulty)

    async def _generate_text_captcha(self, captcha_type: str, difficulty: str) -> Tuple[str, BytesIO, str]:
        """Генератор текстовых капч"""
        # Определяем параметры в зависимости от сложности
        if difficulty == 'легкая':
            chars = self.letters + self.digits
            length = 4
        elif difficulty == 'средняя':
            chars = self.letters + self.digits
            length = 5
        elif difficulty == 'тяжелая':
            chars = self.all_chars
            length = 6
        else:  # хардкорд
            chars = self.all_chars
            length = 8

        # Генерируем текст
        text = ''.join(random.choices(chars, k=length))

        # Создаем изображение
        if difficulty == 'легкая':
            image = self._create_simple_image(text, captcha_type)
        elif difficulty == 'средняя':
            image = self._create_medium_image(text, captcha_type)
        elif difficulty == 'тяжелая':
            image = self._create_hard_image(text, captcha_type)
        else:  # хардкорд
            image = self._create_extreme_image(text, captcha_type)

        buffer = BytesIO()
        image.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)

        return text, buffer, captcha_type

    def _create_simple_image(self, text: str, captcha_type: str) -> Image.Image:
        """Создает простое изображение для легкой сложности"""
        image = Image.new('RGB', (160, 60), color='white')
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except:
            font = ImageFont.load_default()

        # Простой текст
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (160 - text_width) // 2
        y = (60 - text_height) // 2 - 5

        draw.text((x, y), text, font=font, fill='black')

        return image

    def _create_medium_image(self, text: str, captcha_type: str) -> Image.Image:
        """Создает изображение средней сложности"""
        image = Image.new('RGB', (180, 70), color='white')
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 26)
        except:
            font = ImageFont.load_default()

        # Текст с небольшими искажениями
        char_width = 180 // len(text)
        for i, char in enumerate(text):
            x = i * char_width + random.randint(-2, 2)
            y = 20 + random.randint(-3, 3)
            draw.text((x, y), char, font=font, fill='black')

        # Легкий шум
        for _ in range(30):
            x = random.randint(0, 179)
            y = random.randint(0, 69)
            draw.point((x, y), fill='gray')

        # Линии для некоторых типов
        if 'lines' in captcha_type:
            for _ in range(3):
                x1, y1 = random.randint(0, 179), random.randint(0, 69)
                x2, y2 = random.randint(0, 179), random.randint(0, 69)
                draw.line([(x1, y1), (x2, y2)], fill='lightgray', width=1)

        return image

    def _create_hard_image(self, text: str, captcha_type: str) -> Image.Image:
        """Создает сложное изображение"""
        image = Image.new('RGB', (200, 80), color='white')
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except:
            font = ImageFont.load_default()

        # Сильно искаженный текст
        char_width = 200 // len(text)
        for i, char in enumerate(text):
            x = i * char_width + random.randint(-5, 5)
            y = 25 + random.randint(-8, 8)
            rotation = random.randint(-10, 10)

            # Создаем отдельное изображение для символа
            char_image = Image.new('RGBA', (30, 40), (255, 255, 255, 0))
            char_draw = ImageDraw.Draw(char_image)
            char_draw.text((5, 5), char, font=font, fill='black')

            # Поворачиваем символ
            rotated_char = char_image.rotate(rotation, expand=True)

            # Вставляем в основное изображение
            image.paste(rotated_char, (x, y), rotated_char)

        # Шум и линии
        for _ in range(80):
            x = random.randint(0, 199)
            y = random.randint(0, 79)
            draw.point((x, y), fill='gray')

        for _ in range(4):
            x1, y1 = random.randint(0, 199), random.randint(0, 79)
            x2, y2 = random.randint(0, 199), random.randint(0, 79)
            draw.line([(x1, y1), (x2, y2)], fill='lightgray', width=1)

        return image

    def _create_extreme_image(self, text: str, captcha_type: str) -> Image.Image:
        """Создает экстремально сложное изображение"""
        image = Image.new('RGB', (220, 90), color='white')
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", 22)
        except:
            font = ImageFont.load_default()

        # Максимально искаженный текст
        char_width = 220 // len(text)
        for i, char in enumerate(text):
            x = i * char_width + random.randint(-8, 8)
            y = 30 + random.randint(-12, 12)
            rotation = random.randint(-20, 20)

            char_image = Image.new('RGBA', (35, 45), (255, 255, 255, 0))
            char_draw = ImageDraw.Draw(char_image)
            char_draw.text((5, 5), char, font=font, fill='black')

            rotated_char = char_image.rotate(rotation, expand=True)
            image.paste(rotated_char, (x, y), rotated_char)

        # Интенсивный шум
        for _ in range(150):
            x = random.randint(0, 219)
            y = random.randint(0, 89)
            draw.point((x, y), fill=random.choice(['gray', 'darkgray', 'lightgray']))

        # Много линий
        for _ in range(8):
            x1, y1 = random.randint(0, 219), random.randint(0, 89)
            x2, y2 = random.randint(0, 219), random.randint(0, 89)
            draw.line([(x1, y1), (x2, y2)], fill='gray', width=1)

        # Волны искажения
        if 'warped' in captcha_type:
            image = image.filter(ImageFilter.SMOOTH_MORE)

        return image