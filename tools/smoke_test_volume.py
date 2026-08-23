import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="pak-burhan-volume-") as temp_dir:
    os.environ["DATA_DIR"] = temp_dir
    import bot

    assert bot.DATA_DIR == Path(temp_dir)
    bot.save_memory(
        {"user-1": bot.UserMemory([{"role": "user", "text": "pizza"}])},
        {
            "channel-1": bot.ChannelMemory(
                [{"role": "assistant", "text": "Sejarah pizza singkat."}]
            )
        },
    )
    users, channels = bot.load_memory()
    assert users["user-1"].history[0]["text"] == "pizza"
    assert channels["channel-1"].history[0]["text"] == "Sejarah pizza singkat."
    assert bot.MEMORY_FILE.parent == Path(temp_dir)
    print("VOLUME PASS: memory JSON tersimpan dan terbaca dari DATA_DIR")
