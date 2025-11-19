from typing import Any

import httpx

from app.config import settings


def _normalize_base_url(url: str) -> str:
    # Приводим к варианту .../api/v1 во избежание 404
    clean = url.rstrip("/")
    if clean.endswith("/v1") and "/api/" not in clean:
        return clean[:-3] + "/api/v1"
    if clean.endswith("/api"):
        return clean + "/v1"
    if not (clean.endswith("/api/v1")) and clean.endswith("/v1") is False and clean.endswith("/api/v1") is False:
        # если дали базу без версии, добавим /api/v1
        return clean + "/api/v1"
    return clean


class VeniceClient:
    def __init__(self) -> None:
        base_url = _normalize_base_url(settings.venice_api_base_url)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {settings.venice_api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def generate_reply(self, system_prompt: str, history: list[dict[str, str]]) -> str:
        # Анализируем последние сообщения ассистента, чтобы запретить их повторение
        last_assistant_messages = []
        for msg in reversed(history[-10:]):  # Проверяем последние 10 сообщений
            if msg.get("role") == "assistant":
                last_assistant_messages.append(msg.get("content", ""))
                if len(last_assistant_messages) >= 3:  # Берем последние 3 сообщения ассистента
                    break
        
        # Добавляем динамическую инструкцию о запрете повторений
        anti_repetition_instruction = ""
        if last_assistant_messages:
            anti_repetition_instruction = (
                "\n\n"
                "КРИТИЧЕСКИ ВАЖНО - ЗАПРЕТ НА ПОВТОРЕНИЯ:\n"
                "Твои последние сообщения были:\n"
            )
            for i, msg in enumerate(reversed(last_assistant_messages), 1):
                # Берем первые 100 символов каждого сообщения для краткости
                msg_preview = msg[:100] + "..." if len(msg) > 100 else msg
                anti_repetition_instruction += f"{i}. {msg_preview}\n"
            
            anti_repetition_instruction += (
                "\n"
                "СТРОГО ЗАПРЕЩЕНО:\n"
                "- Повторять любые фразы, предложения или части предложений из этих сообщений\n"
                "- Использовать те же формулировки, что были выше\n"
                "- Говорить о том же действии, если оно уже было описано\n"
                "- Повторять вопросы или предложения из предыдущих сообщений\n\n"
                "ВМЕСТО ЭТОГО:\n"
                "- Говори что-то СОВЕРШЕННО НОВОЕ\n"
                "- Продвигай ситуацию дальше, добавляй новые детали\n"
                "- Если действие уже сделано - описывай СЛЕДУЮЩЕЕ действие или результат\n"
                "- Используй ДРУГИЕ слова и формулировки\n"
            )
        
        # Объединяем system prompt с инструкцией о запрете повторений
        enhanced_system_prompt = system_prompt + anti_repetition_instruction
        
        messages: list[dict[str, str]] = [{"role": "system", "content": enhanced_system_prompt}, *history]
        payload: dict[str, Any] = {
            "model": settings.venice_model,
            "messages": messages,
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def generate_image_prompt(
        self,
        girl_name: str,
        girl_description: str,
        recent_dialogue: list[dict[str, str]],
        full_dialogue: list[dict[str, str]] | None = None,
        undressing_clothing: str | None = None,
    ) -> str:
        """
        Генерирует промпт для изображения на основе диалога с персонажем.
        Возвращает только эмоции и уровень обнажения.
        
        Args:
            girl_name: Имя персонажа
            girl_description: Описание персонажа
            recent_dialogue: Последние сообщения диалога
            undressing_clothing: Какую одежду снимает персонаж (shirt/dress и т.д.)
        
        Returns:
            str: Промпт с эмоциями и уровнем обнажения
        """
        # Формируем инструкцию про конкретную одежду при раздевании
        clothing_instruction = ""
        if undressing_clothing:
            clothing_instruction = (
                f"\n"
                f"⚠️ ВАЖНО - КОНКРЕТНАЯ ОДЕЖДА ПРИ РАЗДЕВАНИИ:\n"
                f"У персонажа {girl_name} при раздевании снимается: '{undressing_clothing}'.\n"
                f"Если персонаж РАЗДЕВАЕТСЯ - обязательно укажи конкретную одежду: 'undressing {undressing_clothing}, removing {undressing_clothing}, {undressing_clothing} coming off'.\n"
            )
        
        system_prompt = (
            f"Ты помощник для генерации контекста для промптов изображений. "
            f"Персонаж: {girl_name} - {girl_description}.\n"
            f"{clothing_instruction}\n"
            f"ТВОЯ ЗАДАЧА:\n"
            f"Проанализируй последние сообщения диалога и определи:\n"
            f"1. ЭМОЦИИ персонажа (smiling, blushing, playful, excited, aroused, seductive, shy, confident и т.д.)\n"
            f"2. УРОВЕНЬ ОБНАЖЕНИЯ:\n"
            f"   - Если персонаж ОДЕТ: ничего не добавляй про обнажение\n"
            f"   - Если персонаж РАЗДЕВАЕТСЯ: 'undressing {undressing_clothing if undressing_clothing else 'clothes'}, removing {undressing_clothing if undressing_clothing else 'clothes'}, {undressing_clothing if undressing_clothing else 'clothes'} coming off, partially undressed'\n"
            f"   - Если персонаж ЧАСТИЧНО ОБНАЖЕН (топлесс): 'nsfw, explicit, topless, breasts visible, nipples visible, lower body clothed'\n"
            f"   - Если персонаж ПОЛНОСТЬЮ ОБНАЖЕН: 'nsfw, explicit, uncensored, completely nude, fully naked, no clothing, all body parts visible, breasts fully visible, nipples visible, pussy visible, ass visible'\n\n"
            f"ПРАВИЛА:\n"
            f"1. Используй ТОЛЬКО информацию из диалога\n"
            f"2. НЕ перескакивай уровни обнажения! Если только раздевается - НЕ описывай полное обнажение!\n"
            f"3. НЕ описывай позы, действия, предметы, окружение - ТОЛЬКО эмоции и обнажение\n"
            f"4. Если в диалоге НЕТ упоминания обнажения - НЕ добавляй ничего про обнажение\n"
            f"5. При раздевании ОБЯЗАТЕЛЬНО указывай конкретную одежду: '{undressing_clothing if undressing_clothing else 'clothes'}'.\n\n"
            f"ФОРМАТ ОТВЕТА:\n"
            f"Только английский язык, 5-15 слов, через запятую. "
            f"Примеры:\n"
            f"- 'smiling, playful'\n"
            f"- 'blushing, excited, undressing {undressing_clothing if undressing_clothing else 'clothes'}, removing {undressing_clothing if undressing_clothing else 'clothes'}'\n"
            f"- 'nsfw, explicit, topless, breasts visible, nipples visible, seductive'\n"
            f"- 'nsfw, explicit, uncensored, completely nude, fully naked, aroused'\n\n"
            f"Верни ТОЛЬКО эмоции и уровень обнажения, без дополнительных слов."
        )
        
        # Формируем контекст из последних сообщений
        recent_dialogue_context = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in recent_dialogue[-12:]  # Последние 12 сообщений
        ])
        
        # Формируем сообщение пользователя
        clothing_hint = f" '{undressing_clothing}'" if undressing_clothing else " clothes"
        user_message = (
            f"Последние сообщения из диалога:\n\n{recent_dialogue_context}\n\n"
            f"Проанализируй эти сообщения и определи:\n"
            f"1. ЭМОЦИИ персонажа (smiling, blushing, playful, excited, aroused, seductive, shy, confident и т.д.)\n"
            f"2. УРОВЕНЬ ОБНАЖЕНИЯ:\n"
            f"   - Если персонаж ОДЕТ: ничего не добавляй про обнажение\n"
            f"   - Если персонаж РАЗДЕВАЕТСЯ: добавь 'undressing{clothing_hint}, removing{clothing_hint}, {undressing_clothing if undressing_clothing else 'clothes'} coming off, partially undressed'\n"
            f"   - Если персонаж ЧАСТИЧНО ОБНАЖЕН (топлесс): добавь 'nsfw, explicit, topless, breasts visible, nipples visible'\n"
            f"   - Если персонаж ПОЛНОСТЬЮ ОБНАЖЕН: добавь 'nsfw, explicit, uncensored, completely nude, fully naked, all body parts visible, breasts fully visible, nipples visible, pussy visible, ass visible'\n\n"
            f"ВАЖНО: При раздевании ОБЯЗАТЕЛЬНО указывай конкретную одежду: '{undressing_clothing if undressing_clothing else 'clothes'}'.\n\n"
            f"Верни ТОЛЬКО эмоции и уровень обнажения (5-15 слов на английском, через запятую)."
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        payload: dict[str, Any] = {
            "model": settings.venice_model,
            "messages": messages,
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        prompt = data["choices"][0]["message"]["content"].strip()
        
        # Убираем возможные кавычки и форматирование
        prompt = prompt.strip('"').strip("'").strip()
        
        return prompt

    async def close(self) -> None:
        await self._client.aclose()


