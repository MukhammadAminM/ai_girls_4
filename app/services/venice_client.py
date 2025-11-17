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
        force_nsfw: bool = False,
        nudity_level: str = "none",
        fixed_clothing: str | None = None,
    ) -> str:
        """
        Генерирует промпт для изображения на основе диалога с персонажем.
        
        Args:
            girl_name: Имя персонажа
            girl_description: Описание персонажа
            recent_dialogue: Последние сообщения диалога (для конкретного контекста)
            full_dialogue: Весь диалог (для общего анализа контекста)
            force_nsfw: Принудительный 18+ режим
            nudity_level: Уровень обнажения (none/undressing/partial/full)
        
        Returns:
            str: Промпт для генерации изображения
        """
        # Формируем инструкцию о фиксированной одежде
        clothing_instruction = ""
        if fixed_clothing and nudity_level == "none":
            clothing_instruction = (
                f"\n"
                f"⚠️ КРИТИЧЕСКИ ВАЖНО - ФИКСИРОВАННАЯ ОДЕЖДА:\n"
                f"У персонажа ПОСТОЯННАЯ одежда: '{fixed_clothing}'\n"
                f"ЭТА ОДЕЖДА ДОЛЖНА БЫТЬ НА ВСЕХ ИЗОБРАЖЕНИЯХ, если в диалоге НЕ упомянуто обнажение или раздевание!\n"
                f"НЕ меняй описание одежды, НЕ добавляй другие детали одежды, НЕ описывай другую одежду!\n"
                f"Если в диалоге НЕТ упоминания об изменении одежды или раздевании - используй ТОЛЬКО '{fixed_clothing}'.\n"
                f"НЕ включай описание одежды в свой ответ, если в диалоге не упомянуто обнажение - одежда уже указана в базовом промпте!\n"
            )
        
        system_prompt = (
            f"Ты помощник для генерации ДОПОЛНИТЕЛЬНОГО контекста для промптов изображений. "
            f"Персонаж: {girl_name} - {girl_description}. "
            f"{clothing_instruction}"
            f"\n"
            f"КРИТИЧЕСКИ ВАЖНО - ТВОЯ ГЛАВНАЯ ЗАДАЧА:\n"
            f"Ты ДОЛЖЕН прочитать ВЕСЬ диалог и описать ТОЧНО ТЕКУЩУЮ ситуацию, которая происходит СЕЙЧАС в последних сообщениях.\n"
            f"НЕ придумывай ничего от себя - используй ТОЛЬКО информацию из диалога!\n"
            f"Если в последних сообщениях персонаж РАЗДЕВАЕТСЯ или ОБНАЖЕН - ОБЯЗАТЕЛЬНО опиши это в промпте!\n"
            f"Если в последних сообщениях персонаж ОДЕТ - НЕ описывай одежду (она уже в базовом промпте).\n"
            f"\n"
            f"ПРАВИЛА АНАЛИЗА ДИАЛОГА (УЛУЧШЕНО):\n"
            f"1. Читай ВСЕ последние сообщения диалога ОЧЕНЬ ВНИМАТЕЛЬНО, слово за словом.\n"
            f"2. Обращай внимание на КОНКРЕТНЫЕ действия, которые описаны в диалоге:\n"
            f"   - Что персонаж ДЕЛАЕТ (сидит, стоит, лежит, подходит, касается и т.д.)\n"
            f"   - Что персонаж ГОВОРИТ о своих действиях\n"
            f"   - Какие ЭМОЦИИ выражает (смущена, игрива, возбуждена и т.д.)\n"
            f"   - Где происходит действие (в комнате, на кровати, у окна и т.д.)\n"
            f"   - Что в руках (бокал, предметы и т.д.)\n"
            f"3. Ищи КОНКРЕТНЫЕ слова и фразы из диалога:\n"
            f"   - Раздевание: 'раздеваюсь', 'снимаю', 'расстегиваю', 'сняла', 'разделась'\n"
            f"   - Обнажение: 'голая', 'обнажен', 'топлесс', 'без одежды', 'грудь видна'\n"
            f"   - Позы: 'сижу', 'стою', 'лежу', 'подхожу', 'наклоняюсь'\n"
            f"   - Эмоции: 'улыбаюсь', 'смущена', 'игрива', 'возбуждена'\n"
            f"   - Действия: 'касаюсь', 'обнимаю', 'целую', 'показываю'\n"
            f"4. Если видишь эти слова - ОПИШИ ЭТО ЯВНО в промпте, используя КОНКРЕТНЫЕ детали из диалога!\n"
            f"5. Если НЕ видишь этих слов - персонаж ОДЕТ - НЕ описывай одежду, но опиши позу и эмоции из диалога.\n"
            f"\n"
            f"ЧТО ОПИСЫВАТЬ В ПРОМПТЕ (ИСПОЛЬЗУЙ КОНКРЕТНЫЕ ДЕТАЛИ ИЗ ДИАЛОГА):\n"
            f"- Текущую позу персонажа ИЗ ДИАЛОГА (если сказано 'сижу' - пиши 'sitting', если 'стою' - 'standing', если 'лежу' - 'lying', если 'подхожу' - 'approaching' и т.д.)\n"
            f"- Эмоции ИЗ ДИАЛОГА (если сказано 'улыбаюсь' - пиши 'smiling', если 'смущена' - 'blushing', если 'игрива' - 'playful', если 'возбуждена' - 'aroused' и т.д.)\n"
            f"- КОНКРЕТНЫЕ действия ИЗ ДИАЛОГА (если сказано 'касаюсь' - пиши 'touching', если 'обнимаю' - 'hugging', если 'целую' - 'kissing' и т.д.)\n"
            f"- ОДЕЖДУ/ОБНАЖЕНИЕ ТОЛЬКО ЕСЛИ упомянуто в диалоге:\n"
            f"  * Если упомянуто раздевание - опиши КОНКРЕТНО: 'unbuttoning shirt', 'removing top', 'partially undressed', 'taking off clothes'\n"
            f"  * Если упомянуто частичное обнажение - опиши КОНКРЕТНО: 'topless', 'no top', 'breasts visible', 'nipples visible', 'lower body clothed'\n"
            f"  * Если упомянуто полное обнажение - опиши КОНКРЕТНО: 'completely nude', 'fully naked', 'no clothing', 'all body parts visible'\n"
            f"  * Если НЕ упомянуто - НЕ описывай одежду, но опиши позу и эмоции!\n"
            f"- Предметы в руках ИЗ ДИАЛОГА (если упомянуты: бокал вина, предметы и т.д.)\n"
            f"- Детали окружения ИЗ ДИАЛОГА (если упомянуто: комната, кровать, окно, стол и т.д.)\n"
            f"- ВСЕ детали, которые упомянуты в последних сообщениях диалога!\n"
            f"\n"
            f"КРИТИЧЕСКИ ВАЖНО ДЛЯ 18+ КОНТЕНТА (УЛУЧШЕНО):\n"
            f"- Если персонаж раздевается, снимает одежду, показывает что-то - опиши это ЯВНО и ПОЛНОСТЬЮ: 'nsfw, explicit, topless, nude, breasts fully visible, nipples visible and exposed, no bra, no panties, fully nude, completely naked, pussy visible, ass visible' и т.д.\n"
            f"- ВСЕГДА добавляй теги 'nsfw, explicit, uncensored' если персонаж обнажен или раздевается!\n"
            f"- НЕ используй расплывчатые описания типа 'partially nude' или 'showing' - будь КОНКРЕТНЫМ: 'completely topless, breasts fully exposed, nipples visible', 'fully naked, no clothing at all, all body parts visible', 'pussy visible, vagina exposed', 'ass visible, buttocks exposed' и т.д.\n"
            f"- Если персонаж полностью обнажен - опиши это явно: 'nsfw, explicit, completely nude, fully naked, no clothing at all, all body parts visible and exposed, nothing covering body, spread legs, open pose, breasts fully visible, nipples visible, pussy visible, ass visible'.\n"
            f"- Если персонаж в процессе раздевания - опиши КАКИЕ части уже обнажены: 'topless, bra removed, breasts visible and exposed, nipples visible, panties still on' и т.д.\n"
            f"- ЗАПРЕЩЕНО описывать прикрытия: НЕ пиши 'hands covering', 'arms covering', 'hair covering', 'objects covering', 'censored', 'hidden' - если персонаж обнажен, опиши что ВСЕ части тела ВИДНЫ и ОТКРЫТЫ.\n"
            f"- Если персонаж держит что-то в руках (бокал вина, предметы) - опиши это, но НЕ позволяй предметам закрывать важные части тела в описании. Укажи что предметы НЕ закрывают тело.\n"
            f"- Поза должна быть открытой: 'spread legs', 'arms not covering', 'body fully exposed', 'nothing hiding', 'open pose', 'erotic pose', 'sensual pose' и т.д.\n"
            f"- Используй явные термины: 'pussy', 'vagina', 'breasts', 'nipples', 'ass', 'buttocks', 'nude', 'naked' - НЕ стесняйся!\n"
            f"\n"
            f"КРИТИЧЕСКИ ВАЖНО - ИСПОЛЬЗУЙ ТОЛЬКО ИНФОРМАЦИЮ ИЗ ДИАЛОГА:\n"
            f"- НЕ придумывай ничего, чего НЕТ в диалоге!\n"
            f"- Если в диалоге НЕ упомянута поза - НЕ пиши позу, или используй общую (standing/sitting)\n"
            f"- Если в диалоге НЕ упомянуты эмоции - НЕ пиши эмоции, или используй нейтральную\n"
            f"- Если в диалоге НЕ упомянуты предметы - НЕ пиши предметы\n"
            f"- Опиши ТОЛЬКО то, что РЕАЛЬНО сказано в последних сообщениях!\n"
            f"\n"
            f"Дополнение должно ПЕРЕЗАПИСЫВАТЬ базовое описание одежды, если в диалоге описана другая ситуация. "
            f"Используй английский язык, формат: '[поза ИЗ ДИАЛОГА], [действия ИЗ ДИАЛОГА], [одежда/обнажение ИЗ ДИАЛОГА - ЯВНО И ПОЛНОСТЬЮ], [эмоции ИЗ ДИАЛОГА], [предметы в руках ИЗ ДИАЛОГА], [детали окружения ИЗ ДИАЛОГА]'. "
            f"НЕ включай общие слова качества (masterpiece, best quality и т.д.) - они уже есть в базовом промпте. "
            f"Будь максимально конкретным и детальным, используя ТОЛЬКО информацию из диалога. Если персонаж раздевается - опиши это явно и детально, БЕЗ цензуры и прикрытий. "
            f"Верни ТОЛЬКО дополнение к промпту (20-40 слов), без дополнительных объяснений."
        )
        
        # Формируем контекст из всего диалога для общего анализа
        full_dialogue_context = ""
        if full_dialogue:
            # Берем весь диалог, но ограничиваем длину для экономии токенов
            # Если диалог очень длинный, берем первые сообщения (начало) и последние (текущее состояние)
            if len(full_dialogue) > 50:
                # Берем первые 10 сообщений (начало диалога) и последние 20 (текущее состояние)
                start_messages = full_dialogue[:10]
                end_messages = full_dialogue[-20:]
                full_dialogue_context = "\n".join([
                    f"{msg['role']}: {msg['content']}" 
                    for msg in start_messages
                ]) + "\n... (пропущено сообщений) ...\n" + "\n".join([
                    f"{msg['role']}: {msg['content']}" 
                    for msg in end_messages
                ])
            else:
                # Если диалог не очень длинный, берем все сообщения
                full_dialogue_context = "\n".join([
                    f"{msg['role']}: {msg['content']}" 
                    for msg in full_dialogue
                ])
        
        # Формируем контекст из последних сообщений для конкретного промпта
        # УВЕЛИЧИВАЕМ количество сообщений для лучшего контекста
        recent_dialogue_context = "\n".join([
            f"{msg['role']}: {msg['content']}" 
            for msg in recent_dialogue[-12:]  # Последние 12 сообщений для лучшего контекста
        ])
        
        # Добавляем инструкцию в зависимости от уровня обнажения
        # КРИТИЧЕСКИ ВАЖНО: Добавляем инструкции ТОЛЬКО если nudity_level != "none"
        # Если в диалоге НЕТ упоминания обнажения - НЕ добавляем никаких инструкций об обнажении!
        nudity_instruction = ""
        if nudity_level == "full":
            nudity_instruction = (
                f"\n"
                f"⚠️ ВАЖНО: В диалоге персонаж ПОЛНОСТЬЮ обнажен. Опиши: 'completely nude, fully naked, no clothing at all, all body parts visible and exposed, nothing covering, spread legs, open pose, breasts fully visible, nipples visible, pussy visible, ass visible'.\n"
            )
        elif nudity_level == "partial":
            nudity_instruction = (
                f"\n"
                f"⚠️ ВАЖНО: В диалоге персонаж ЧАСТИЧНО обнажен (топлесс, без верха). Опиши: 'topless, no top, bra removed, breasts visible, nipples visible, partially nude, lower body still clothed'.\n"
                f"НЕ описывай полное обнажение - только частичное, как в диалоге.\n"
            )
        elif nudity_level == "undressing":
            nudity_instruction = (
                f"\n"
                f"⚠️ ВАЖНО: В диалоге персонаж В ПРОЦЕССЕ раздевания. Опиши: 'unbuttoning shirt, removing top, partially undressed, showing some skin, in the process of undressing'.\n"
                f"НЕ описывай полное или даже частичное обнажение - только начало процесса раздевания.\n"
            )
        elif nudity_level == "none":
            # КРИТИЧЕСКИ ВАЖНО: Если в диалоге НЕТ упоминания обнажения - ЗАПРЕЩАЕМ описывать обнажение!
            nudity_instruction = (
                f"\n"
                f"⚠️ КРИТИЧЕСКИ ВАЖНО: В диалоге НЕТ упоминания обнажения или раздевания! "
                f"ЗАПРЕЩЕНО описывать обнажение, раздевание, топлесс, nude, naked и т.д. "
                f"Описывай персонажа ОДЕТЫМ, как указано в базовом промпте. "
                f"НЕ добавляй никаких упоминаний об обнажении, даже частичном!\n"
            )
        
        # Если принудительный 18+ режим включен - добавляем специальную инструкцию
        # ВАЖНО: force_nsfw должен быть True ТОЛЬКО если nudity_level == "full" (проверяется в handlers.py)
        force_nsfw_instruction = ""
        if force_nsfw and nudity_level == "full":
            force_nsfw_instruction = (
                f"\n"
                f"⚠️ ВАЖНО: 18+ РЕЖИМ ВКЛЮЧЕН! Персонаж ДОЛЖЕН быть полностью обнаженным на изображении.\n"
                f"ОБЯЗАТЕЛЬНО опиши: 'completely nude, fully naked, no clothing at all, all body parts visible and exposed, nothing covering, spread legs, open pose, breasts fully visible, nipples visible, pussy visible, ass visible'.\n"
                f"НЕ используй никаких прикрытий или частичного обнажения - только ПОЛНОЕ обнажение.\n"
            )
        
        # Формируем сообщение с упрощенным и более прямым анализом
        if full_dialogue_context:
            user_message = (
                f"Вот ПОСЛЕДНИЕ сообщения из диалога (ВНИМАТЕЛЬНО ПРОЧИТАЙ КАЖДОЕ СЛОВО!):\n\n{recent_dialogue_context}\n\n"
                f"КРИТИЧЕСКИ ВАЖНО: Ты ДОЛЖЕН прочитать ВСЕ сообщения выше и описать ТОЧНО то, что там написано!\n"
                f"НЕ придумывай ничего от себя - используй ТОЛЬКО информацию из диалога выше!\n\n"
                f"ЗАДАЧА: Проанализируй ПОСЛЕДНИЕ сообщения ПОСЛОВНО и определи:\n"
                f"1. РАЗДЕВАЕТСЯ ли персонаж? Ищи слова: 'раздеваюсь', 'снимаю', 'расстегиваю', 'раздевается', 'сняла', 'снимаю'\n"
                f"2. ЧАСТИЧНО ОБНАЖЕН? Ищи слова: 'топлесс', 'без верха', 'сняла блузку', 'грудь видна', 'соски видны'\n"
                f"3. ПОЛНОСТЬЮ ОБНАЖЕН? Ищи слова: 'голая', 'обнажен', 'без одежды', 'все сняла', 'полностью раздета'\n"
                f"4. КАКУЮ ПОЗУ принимает? Ищи слова: 'сижу', 'стою', 'лежу', 'подхожу', 'наклоняюсь', 'сажусь'\n"
                f"5. КАКИЕ ЭМОЦИИ выражает? Ищи слова: 'улыбаюсь', 'смущена', 'игрива', 'возбуждена', 'страстна'\n"
                f"6. ЧТО ДЕЛАЕТ? Ищи слова: 'касаюсь', 'обнимаю', 'целую', 'показываю', 'держу'\n"
                f"7. ГДЕ находится? Ищи слова: 'в комнате', 'на кровати', 'у окна', 'за столом'\n"
                f"8. ЧТО в руках? Ищи слова: 'бокал', 'вино', 'предмет', 'держу'\n"
                f"9. ОДЕТ? Если НЕТ упоминания раздевания/обнажения - персонаж ОДЕТ\n\n"
                f"{nudity_instruction}"
                f"{force_nsfw_instruction}"
                f"\n"
                f"ЕСЛИ В ДИАЛОГЕ УПОМЯНУТО РАЗДЕВАНИЕ/ОБНАЖЕНИЕ:\n"
                f"- ОПИШИ ЭТО ЯВНО в промпте, используя КОНКРЕТНЫЕ слова из диалога!\n"
                f"- ВСЕГДА добавляй 'nsfw, explicit, uncensored' в начало промпта!\n"
                f"- Если раздевается - опиши: 'nsfw, explicit, unbuttoning shirt', 'removing top', 'partially undressed', 'showing skin'\n"
                f"- Если частично обнажен - опиши: 'nsfw, explicit, topless', 'no top', 'breasts fully visible', 'nipples visible', 'lower body clothed'\n"
                f"- Если полностью обнажен - опиши: 'nsfw, explicit, completely nude', 'fully naked', 'no clothing at all', 'all body parts visible', 'pussy visible', 'ass visible', 'breasts fully visible', 'nipples visible'\n"
                f"\n"
                f"ЕСЛИ В ДИАЛОГЕ НЕТ УПОМИНАНИЯ РАЗДЕВАНИЯ/ОБНАЖЕНИЯ:\n"
                f"- НЕ описывай одежду в промпте! Одежда уже указана в базовом промпте.\n"
                f"- Опиши ТОЛЬКО то, что есть в диалоге: позу (если упомянута), эмоции (если упомянуты), предметы в руках (если упомянуты), детали окружения (если упомянуты).\n"
                f"\n"
                f"ПРИМЕРЫ ПРАВИЛЬНОГО АНАЛИЗА:\n"
                f"- Если в диалоге: 'я сижу на кровати и улыбаюсь' → опиши: 'sitting on bed, smiling'\n"
                f"- Если в диалоге: 'я снимаю блузку' → опиши: 'nsfw, explicit, removing blouse, topless, breasts visible'\n"
                f"- Если в диалоге: 'я подхожу к тебе и касаюсь' → опиши: 'approaching, touching'\n"
                f"- Если в диалоге: 'я держу бокал вина' → опиши: 'holding wine glass'\n"
                f"\n"
                f"Создай дополнение к промпту (20-40 слов), которое описывает ТОЧНО ТЕКУЩУЮ ситуацию из ПОСЛЕДНИХ сообщений, используя КОНКРЕТНЫЕ детали из диалога. "
                f"\n"
                f"ФОРМАТ ОТВЕТА:\n"
                f"Используй английский язык. Опиши: [поза ИЗ ДИАЛОГА], [действия ИЗ ДИАЛОГА], [эмоции ИЗ ДИАЛОГА], [одежда/обнажение ЕСЛИ упомянуто в диалоге], [предметы в руках ЕСЛИ упомянуты].\n"
                f"Если упомянуто раздевание/обнажение - ОБЯЗАТЕЛЬНО добавь 'nsfw, explicit, uncensored' в начало!\n"
                f"НЕ включай слова качества (masterpiece, best quality и т.д.) - они уже в базовом промпте.\n"
                f"НЕ придумывай ничего, чего НЕТ в диалоге!\n"
                f"Верни ТОЛЬКО дополнение (20-40 слов), без дополнительных объяснений."
            )
        else:
            # Fallback если нет полного диалога
            user_message = (
                f"Вот последние сообщения из диалога (ВНИМАТЕЛЬНО ПРОЧИТАЙ КАЖДОЕ СЛОВО!):\n\n{recent_dialogue_context}\n\n"
                f"КРИТИЧЕСКИ ВАЖНО: Ты ДОЛЖЕН прочитать ВСЕ сообщения выше и описать ТОЧНО то, что там написано!\n"
                f"НЕ придумывай ничего от себя - используй ТОЛЬКО информацию из диалога выше!\n\n"
                f"ЗАДАЧА: Проанализируй ПОСЛЕДНИЕ сообщения ПОСЛОВНО и определи:\n"
                f"1. РАЗДЕВАЕТСЯ ли персонаж? Ищи слова: 'раздеваюсь', 'снимаю', 'расстегиваю', 'сняла'\n"
                f"2. ЧАСТИЧНО ОБНАЖЕН? Ищи слова: 'топлесс', 'без верха', 'сняла блузку', 'грудь видна'\n"
                f"3. ПОЛНОСТЬЮ ОБНАЖЕН? Ищи слова: 'голая', 'обнажен', 'без одежды', 'все сняла'\n"
                f"4. КАКУЮ ПОЗУ принимает? Ищи слова: 'сижу', 'стою', 'лежу', 'подхожу'\n"
                f"5. КАКИЕ ЭМОЦИИ выражает? Ищи слова: 'улыбаюсь', 'смущена', 'игрива'\n"
                f"6. ЧТО ДЕЛАЕТ? Ищи слова: 'касаюсь', 'обнимаю', 'целую', 'показываю'\n"
                f"7. ОДЕТ? Если НЕТ упоминания раздевания/обнажения - персонаж ОДЕТ\n\n"
                f"{nudity_instruction}"
                f"{force_nsfw_instruction}"
                f"\n"
                f"ЕСЛИ В ДИАЛОГЕ УПОМЯНУТО РАЗДЕВАНИЕ/ОБНАЖЕНИЕ:\n"
                f"- ОПИШИ ЭТО ЯВНО в промпте! Будь конкретным!\n"
                f"- ВСЕГДА добавляй 'nsfw, explicit, uncensored' в начало промпта!\n"
                f"- Если раздевается - опиши: 'nsfw, explicit, unbuttoning shirt', 'removing top', 'partially undressed', 'showing skin'\n"
                f"- Если частично обнажен - опиши: 'nsfw, explicit, topless', 'no top', 'breasts fully visible', 'nipples visible'\n"
                f"- Если полностью обнажен - опиши: 'nsfw, explicit, completely nude', 'fully naked', 'no clothing at all', 'all body parts visible', 'pussy visible', 'ass visible'\n"
                f"\n"
                f"ЕСЛИ В ДИАЛОГЕ НЕТ УПОМИНАНИЯ РАЗДЕВАНИЯ/ОБНАЖЕНИЯ:\n"
                f"- НЕ описывай одежду! Опиши только: позу, эмоции, предметы в руках.\n"
                f"\n"
                f"ПРИМЕРЫ ПРАВИЛЬНОГО АНАЛИЗА:\n"
                f"- Если в диалоге: 'я сижу на кровати и улыбаюсь' → опиши: 'sitting on bed, smiling'\n"
                f"- Если в диалоге: 'я снимаю блузку' → опиши: 'nsfw, explicit, removing blouse, topless, breasts visible'\n"
                f"- Если в диалоге: 'я подхожу к тебе и касаюсь' → опиши: 'approaching, touching'\n"
                f"\n"
                f"Создай дополнение к промпту (20-40 слов), которое описывает ТОЧНО ТЕКУЩУЮ ситуацию из ПОСЛЕДНИХ сообщений, используя КОНКРЕТНЫЕ детали из диалога. "
                f"\n"
                f"ФОРМАТ ОТВЕТА:\n"
                f"Используй английский язык. Опиши: [поза ИЗ ДИАЛОГА], [действия ИЗ ДИАЛОГА], [эмоции ИЗ ДИАЛОГА], [одежда/обнажение ЕСЛИ упомянуто в диалоге], [предметы в руках ЕСЛИ упомянуты].\n"
                f"Если упомянуто раздевание/обнажение - ОБЯЗАТЕЛЬНО добавь 'nsfw, explicit, uncensored' в начало!\n"
                f"НЕ включай слова качества (masterpiece, best quality и т.д.) - они уже в базовом промпте.\n"
                f"НЕ придумывай ничего, чего НЕТ в диалоге!\n"
                f"Верни ТОЛЬКО дополнение (20-40 слов), без дополнительных объяснений."
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
        
        # Если принудительный 18+ режим включен - добавляем nsfw теги
        if force_nsfw:
            # Убеждаемся, что промпт содержит nsfw теги
            if "nsfw" not in prompt.lower() and "explicit" not in prompt.lower():
                prompt = f"nsfw, explicit, uncensored, {prompt}, nsfw, explicit, uncensored"
            elif "nsfw" not in prompt.lower():
                prompt = f"nsfw, uncensored, {prompt}, nsfw, uncensored"
            elif "explicit" not in prompt.lower():
                prompt = f"explicit, uncensored, {prompt}, explicit, uncensored"
            elif "uncensored" not in prompt.lower():
                prompt = f"uncensored, {prompt}, uncensored"
        
        # Также добавляем nsfw теги если nudity_level != "none" (даже если force_nsfw=False)
        if nudity_level != "none" and ("nsfw" not in prompt.lower() or "explicit" not in prompt.lower()):
            if "nsfw" not in prompt.lower() and "explicit" not in prompt.lower():
                prompt = f"nsfw, explicit, uncensored, {prompt}"
            elif "nsfw" not in prompt.lower():
                prompt = f"nsfw, uncensored, {prompt}"
            elif "explicit" not in prompt.lower():
                prompt = f"explicit, uncensored, {prompt}"
        
        return prompt

    async def close(self) -> None:
        await self._client.aclose()


