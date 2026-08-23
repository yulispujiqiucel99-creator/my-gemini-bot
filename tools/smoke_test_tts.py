import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot


class FakeCompletions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            assert kwargs["temperature"] == 0.2
            assert kwargs["max_tokens"] == 500
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="The user provided a very short prompt."
                        )
                    )
                ]
            )
        assert kwargs["temperature"] == 0.1
        assert kwargs["max_tokens"] == 400
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="Ringkasan singkat AI.\nTidak ada simbol aneh 🤖"
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


async def main() -> None:
    original_client = bot.openrouter_client
    original_client_2 = bot.openrouter_client_2
    fake_client = FakeClient()
    bot.openrouter_client = fake_client
    bot.openrouter_client_2 = None
    try:
        assert bot.is_tts_meta_response(
            "According to my instructions, I cannot summarize nothing."
        )
        rewritten = await bot.prepare_tts_text(
            "Artikel panjang yang harus dipadatkan menjadi naskah audio."
        )
        assert rewritten == "Ringkasan singkat AI. Tidak ada simbol aneh"
        assert len(fake_client.chat.completions.calls) == 2
        assert len(rewritten) <= bot.TTS_MAX_CHARS
        long_text = "kata " * bot.TTS_MAX_CHARS
        assert len(bot.limit_tts_text(long_text)) <= bot.TTS_MAX_CHARS

        normalized = bot.normalize_tts_text("Halo!!! @Pak_Burhan 🤖\nTes suara.")
        assert normalized == "Halo!!! PakBurhan Tes suara.", normalized

        path: Path | None = None
        try:
            path = await bot.synthesize_tts(rewritten)
            assert path.exists(), "File TTS tidak dibuat"
            assert path.stat().st_size > 0, "File TTS kosong"
            print(f"TTS PASS: {path.suffix} {path.stat().st_size} bytes")
        finally:
            if path is not None:
                await bot.remove_tts_file(path)
            assert path is None or not path.exists(), "File sementara belum terhapus"
    finally:
        bot.openrouter_client = original_client
        bot.openrouter_client_2 = original_client_2


if __name__ == "__main__":
    asyncio.run(main())
