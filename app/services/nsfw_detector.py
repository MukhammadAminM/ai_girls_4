"""Сервис для определения 18+ контента в диалогах."""
import re
from typing import Sequence

from app.models import ChatMessage


# Ключевые слова и фразы, указывающие на 18+ контент
NSFW_KEYWORDS = [
    # Действия
    "раздеваюсь", "раздеваешься", "разделся", "разделась",
    "снимаю", "снимаешь", "снял", "сняла",
    "обнажен", "обнажена", "голый", "голая", "голые",
    "топлесс", "без одежды", "без трусов", "без лифчика",
    "обнимаю", "целую", "ласкаю", "касаюсь",
    "интим", "секс", "постель", "кровать",
    "грудь", "сиськи", "попа", "попка",
    "возбуж", "хочу тебя", "хочу тебя",
    
    # Эмоции и состояния
    "возбужден", "возбуждена", "возбуждение",
    "страстн", "желаю", "хочу",
    
    # Части тела (явные)
    "соски", "соски", "клитор", "член",
    
    # Действия (более явные)
    "траха", "еба", "конча", "оргазм",
]


def detect_nsfw_in_messages(messages: Sequence[ChatMessage], check_last: int = 10) -> bool:
    """
    Определяет, содержит ли диалог 18+ контент.
    
    Args:
        messages: Список сообщений диалога
        check_last: Количество последних сообщений для проверки
    
    Returns:
        True если обнаружен 18+ контент, False иначе
    """
    if not messages:
        return False
    
    # Берем последние N сообщений
    recent_messages = list(messages[-check_last:]) if len(messages) > check_last else list(messages)
    
    # Объединяем текст всех сообщений
    combined_text = " ".join([msg.content.lower() for msg in recent_messages])
    
    # Проверяем наличие ключевых слов
    nsfw_count = 0
    for keyword in NSFW_KEYWORDS:
        # Используем регулярное выражение для поиска слова целиком
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        matches = len(re.findall(pattern, combined_text))
        nsfw_count += matches
    
    # Если найдено 2+ совпадения в последних сообщениях - считаем что это 18+
    return nsfw_count >= 2

