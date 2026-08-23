import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import remove_tts_file, synthesize_tts


async def main() -> None:
    path: Path | None = None
    try:
        path = await synthesize_tts("Halo, ini tes suara Pak Burhan.")
        assert path.exists(), "File TTS tidak dibuat"
        assert path.stat().st_size > 0, "File TTS kosong"
        print(f"TTS PASS: {path.suffix} {path.stat().st_size} bytes")
    finally:
        if path is not None:
            await remove_tts_file(path)
        assert path is None or not path.exists(), "File sementara belum terhapus"


if __name__ == "__main__":
    asyncio.run(main())
