"""Скрипт для запуска воркера обработки задач из очереди Redis."""
import asyncio
import logging

from app.workers.queue_worker import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    asyncio.run(main())

