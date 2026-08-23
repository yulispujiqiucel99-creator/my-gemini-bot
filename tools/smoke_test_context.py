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

assert bot.is_short_follow_up("Wah 😋🤤")
assert bot.is_short_follow_up("Wah, enak banget")
assert not bot.is_short_follow_up("Buntut lele enak tidak?")

bot.MEMORY = {
    "1": bot.UserMemory(
        [
            {"role": "user", "text": "Buntut lele itu enak tidak?"},
            {"role": "assistant", "text": "Buntut lele gurih jika dimasak dengan bumbu yang tepat."},
        ]
    )
}
bot.CHANNEL_MEMORY = {
    "channel-1": bot.ChannelMemory(
        [{"role": "assistant", "text": "Sop buntut memakai kuah kaldu."}]
    )
}
user_context = bot.get_context(1, 1)
assert any("Buntut lele" in item["text"] for item in user_context)
assert not any("Sop buntut" in item["text"] for item in user_context)

messages = bot.build_messages(history, "Wah, enak banget 😋🤤", "Naufal")
new_topic_messages = bot.build_messages(history, "Buntut lele enak tidak?", "Naufal")

assert messages[-1]["role"] == "user"
assert any(
    "PRIORITAS TERTINGGI" in item["content"]
    for item in new_topic_messages
    if item["role"] == "system"
)
assert "Wah" in messages[-1]["content"]
assert any("kesinambungan" in item["content"] for item in messages if item["role"] == "system")
assert any(
    "Pizza bermula" in item["content"] for item in messages if item["role"] == "system"
)
assert not any(
    item["role"] == "user" and item["content"].count("sejarah singkat") > 1
    for item in messages
)
print("CONTEXT PASS: balasan pendek tetap membawa konteks pizza")
