from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Girl(Base):
    __tablename__ = "girls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    greeting: Mapped[str] = mapped_column(Text, nullable=False)
    clothing_description: Mapped[str | None] = mapped_column(Text, nullable=True)  # Описание постоянной одежды персонажа


class Dialog(Base):
    __tablename__ = "dialogs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    girl_id: Mapped[int] = mapped_column(ForeignKey("girls.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nsfw_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)  # Тумблер для 18+ контента
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id", ondelete="CASCADE"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserSelectedGirl(Base):
    __tablename__ = "user_selected_girls"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    girl_id: Mapped[int] = mapped_column(ForeignKey("girls.id", ondelete="CASCADE"), nullable=False)
    active_dialog_id: Mapped[int | None] = mapped_column(ForeignKey("dialogs.id", ondelete="SET NULL"), nullable=True)
    photos_used: Mapped[int] = mapped_column(default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class UserRetention(Base):
    """Модель для отслеживания retention пользователей."""
    __tablename__ = "user_retention"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    total_sessions: Mapped[int] = mapped_column(default=1, nullable=False)
    total_messages: Mapped[int] = mapped_column(default=0, nullable=False)
    total_photos: Mapped[int] = mapped_column(default=0, nullable=False)
    days_active: Mapped[int] = mapped_column(default=1, nullable=False)  # Количество уникальных дней активности


class UserActivity(Base):
    """Модель для отслеживания ежедневной активности пользователей."""
    __tablename__ = "user_activity"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    activity_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    messages_count: Mapped[int] = mapped_column(default=0, nullable=False)
    photos_generated: Mapped[int] = mapped_column(default=0, nullable=False)
    dialogs_created: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Уникальный индекс на user_id + date
    __table_args__ = (
        UniqueConstraint('user_id', 'activity_date', name='uq_user_activity_date'),
    )


class UserProfile(Base):
    """Модель профиля пользователя с алмазами и энергией."""
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, nullable=False)
    diamonds: Mapped[int] = mapped_column(default=5, nullable=False)  # Начальное количество алмазов
    energy: Mapped[int] = mapped_column(default=25, nullable=False)  # Начальное количество энергии
    max_energy: Mapped[int] = mapped_column(default=25, nullable=False)  # Максимальная энергия
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Payment(Base):
    """Модель для отслеживания платежей (донатов)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    payment_type: Mapped[str] = mapped_column(String(50), nullable=False)  # diamonds, energy, pack, combo
    amount_stars: Mapped[int] = mapped_column(nullable=False)  # Сумма в Telegram Stars
    amount_usd: Mapped[float | None] = mapped_column(nullable=True)  # Сумма в USD (если известна)
    diamonds_received: Mapped[int] = mapped_column(default=0, nullable=False)  # Получено алмазов
    energy_received: Mapped[int] = mapped_column(default=0, nullable=False)  # Получено энергии
    pack_name: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Название пакета (если применимо)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # ID платежа от Telegram
    telegram_provider_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # ID платежа от провайдера
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


