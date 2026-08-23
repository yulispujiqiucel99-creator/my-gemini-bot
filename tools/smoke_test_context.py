import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot


history = [
    {
        "role": "user",
        "text": "Ceritakan sejarah singkat tentang pizza.",
        "author": "Naufal",
    },
    {
        "role": "assistant",
        "text": "Pizza bermula dari roti pipih dengan topping sederhana di kawasan Mediterania, lalu berkembang di Napoli hingga menjadi pizza modern yang dikenal dunia.",
    },
]

messages = bot.build_messages(history, "Wah, enak banget 😋🤤", "Naufal")

assert messages[-1]["role"] == "user"
assert "Wah" in messages[-1]["content"]
assert any("kesinambungan" in item["content"] for item in messages if item["role"] == "system")
assert not any(
    item["role"] == "user" and item["content"].count("sejarah singkat") > 1
    for item in messages
)
print("CONTEXT PASS: balasan pendek tetap membawa konteks pizza")
