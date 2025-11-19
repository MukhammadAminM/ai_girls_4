from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    venice_api_key: str
    venice_api_base_url: str = "https://api.venice.ai/api/v1"
    venice_model: str = "venice-uncensored"
    image_api_url: str = "http://127.0.0.1:8000"
    image_default_width: int = 832
    image_default_height: int = 1216
    image_default_steps: int = 28
    image_default_cfg: float = 5.0
    image_default_seed: int = -1
    image_default_negative_prompt: str = "(worst quality, low quality:1.4), (greyscale, monochrome:1.1), cropped, lowres , username, blurry, trademark, watermark, title, strabismus, clothing cutout, side slit,worst hand, (ugly face:1.2), extra leg, extra arm, bad foot, text, name, badhandv4, easynegative, EasyNegativeV2, negative_hand, ng_deepnegative_v1_75t"
    image_default_lora_name: str | None = None
    image_default_lora_strength_model: float = 0.80
    image_default_lora_strength_clip: float = 0.90
    
    # Replicate настройки
    replicate_api_token: str | None = None
    replicate_model: str = "black-forest-labs/flux-dev"  # Модель по умолчанию
    # Альтернативные модели для NSFW:
    # "cjwbw/animagine-xl-3.1:6afe2e6b27dad2d6f480b59195c221884b6acc589ff4d05ff0e5fc058690fbb9" - Animagine XL 3.1
    # "aisha-ai-official/wai-nsfw-illustrious-v11:c1d5b02687df6081c7953c74bcc527858702e8c153c9382012ccc3906752d3ec" - WAI NSFW Illustrious v11 (специально для NSFW)
    use_replicate: bool = False  # Переключатель между локальным API и Replicate
    
    # Live3D настройки
    live3d_api_token: str | None = None  # Bearer токен для Live3D API
    live3d_model_id: int = 135  # ID модели для генерации
    live3d_consume_points: int = 20  # Количество очков для одной генерации
    live3d_default_width: int = 512  # Ширина по умолчанию для Live3D (как в test_live3d_api.py)
    live3d_default_height: int = 768  # Высота по умолчанию для Live3D (как в test_live3d_api.py)
    live3d_default_cfg: float = 7.0  # CFG scale по умолчанию для Live3D (как в test_live3d_api.py)
    live3d_default_steps: int = 25  # Количество шагов по умолчанию для Live3D (как в test_live3d_api.py)
    use_live3d: bool = False  # Переключатель для использования Live3D вместо локального API/Replicate
    
    # Redis настройки
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_prefix: str = "ai_girls:queue:"
    redis_result_prefix: str = "ai_girls:result:"
    redis_result_ttl: int = 3600  # Время жизни результатов в секундах (1 час)
    
    # Админ настройки
    admin_user_ids: str = ""  # Список ID админов через запятую (например: "123456789,987654321")
    
    # Настройки ресурсов
    image_generation_cost: int = 5  # Стоимость генерации изображения в алмазах
    message_energy_cost: int = 1  # Стоимость сообщения в энергии
    energy_regen_amount: int = 1  # Количество энергии, восстанавливаемой за раз
    energy_regen_interval: int = 60  # Интервал регенерации энергии в секундах

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # type: ignore[arg-type]


