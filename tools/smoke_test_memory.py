import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot


async def main() -> None:
    original_file = bot.PERMANENT_MEMORY_FILE
    original_memory = dict(bot.PERMANENT_MEMORY)
    try:
        with tempfile.TemporaryDirectory() as directory:
            bot.PERMANENT_MEMORY_FILE = Path(directory) / 'permanent_memory.json'
            bot.PERMANENT_MEMORY.clear()
            bot.db_pool = None

            assert await bot.save_user_memory(123, 'suka belajar matematika')
            assert await bot.get_user_memories(123) == ['suka belajar matematika']
            assert await bot.save_user_memory(123, 'tinggal di Boyolali')
            assert await bot.get_user_memories(123) == [
                'suka belajar matematika',
                'tinggal di Boyolali',
            ]
            assert bot.PERMANENT_MEMORY_FILE.exists()
            assert await bot.delete_user_memories(123)
            assert await bot.get_user_memories(123) == []
        print('memory fallback smoke test: PASS')
    finally:
        bot.PERMANENT_MEMORY_FILE = original_file
        bot.PERMANENT_MEMORY.clear()
        bot.PERMANENT_MEMORY.update(original_memory)


asyncio.run(main())
