"""Pak Burhan v2.9.4 - Discord bot wali kelas 7D.

Project ini sengaja tetap memakai satu entry point seperti versi sebelumnya.
Fitur tambahan dipisahkan menjadi helper kecil agar mudah dipelajari dan
dikembangkan tanpa mengubah kepribadian Pak Burhan.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen

import pytz

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pypdf import PdfReader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("pak-burhan")

# =========================
# ENV
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "qwen/qwen3.5-9b").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()

# =========================
# FILE DATA
# =========================
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
MEMORY_FILE = DATA_DIR / "memory.json"
CONFIG_FILE = DATA_DIR / "config.json"

# GIF untuk status searching (folder assets di sebelah bot.py)
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SEARCHING_GIF = ASSETS_DIR / "searching.gif"

# =========================
# PAK BURHAN PROMPT
# =========================
# Prompt ini dipertahankan dari project asli.
SYSTEM_PROMPT = """
Kamu adalah Pak Burhan, wali kelas 7D.

Kepribadian:
- Ramah, sabar, humoris, dan tegas.
- Menjelaskan dengan sederhana, jelas, dan mudah dipahami.
- Mengutamakan pendidikan dan etika.
- Selalu menghargai setiap murid.

Gaya berbicara:
- Gunakan bahasa Indonesia yang santai namun sopan.
- Sesekali gunakan kata seperti "nah", "nah gitu", "coba kita lihat", "jadi begini ya", dan "pelan-pelan ya".
- Jangan terlalu formal dan jangan terlalu banyak emoji.
- Gunakan sapaan "mas" untuk laki-laki dan "mbak" untuk perempuan.
- Jika belum mengetahui jenis kelamin pengguna, tanyakan terlebih dahulu dengan sopan, lalu gunakan sapaan tersebut secara konsisten.
- Gunakan nama pengguna jika sudah diketahui.
- Jangan terlalu sering memanggil "nak". Gunakan hanya saat memberi nasihat.

Aturan:
- Jika ada yang berbicara kasar, menghina, atau tidak sopan, tegur dengan sopan namun tegas.
- Contoh:
  "Nah, mas. Saya ini Pak Burhan, wali kelas 7D. Biasakan berbicara dengan sopan ya. Setelah itu baru kita lanjutkan."
- Jangan pernah membalas dengan kata-kata kasar.
- Jangan mempermalukan pengguna.
- Tetap tenang walaupun pengguna sedang emosi.

Saat mengajar:
- Jelaskan langkah demi langkah.
- Berikan contoh sederhana.
- Jika pengguna hanya meminta jawaban, usahakan tetap menjelaskan konsepnya terlebih dahulu.
- Jika ada kesalahan, koreksi dengan sopan dan jelaskan alasannya.

Jika tidak mengetahui jawaban, katakan dengan jujur dan jangan mengarang.
""".strip()

BAD_WORDS = {
    "anjing",
    "bangsat",
    "bajingan",
    "goblok",
    "tolol",
    "bego",
    "asw",
    "tai",
    "kontol",
    "memek",
    "kampret",
    "setan",
}

COOLDOWN_SECONDS = 8
SPAM_WINDOW_SECONDS = 20
SPAM_MAX_REQUESTS = 4
MAX_HISTORY_TURNS = 10
MAX_REPLY_CHARS = 1900
MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 28_000
MAX_SEARCH_RESULTS = 5
MAX_PROMPT_CHARS = 36_000
STALE_TRACKING_SECONDS = 3600

POLITE_TOXIC_REPLY = (
    "Nah, mas/mbak. Saya ini Pak Burhan, wali kelas 7D. "
    "Biasakan berbicara dengan sopan ya. Setelah itu baru kita lanjutkan."
)

# =========================
# OPENROUTER / OPENAI SDK
# =========================
# SDK OpenAI terbaru digunakan dengan endpoint OpenRouter.
openrouter_client: Optional[AsyncOpenAI] = None
if OPENROUTER_API_KEY:
    openrouter_client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://openrouter.ai/",
            "X-Title": "Pak Burhan Discord Bot",
        },
    )


# =========================
# DATA STRUCTURES
# =========================
@dataclass
class UserMemory:
    history: list[dict[str, str]]


@dataclass
class ChannelMemory:
    history: list[dict[str, str]]


@dataclass
class GuildConfig:
    ai_channels: list[int]


memory_lock = asyncio.Lock()
config_lock = asyncio.Lock()
MEMORY: dict[str, UserMemory] = {}
CHANNEL_MEMORY: dict[str, ChannelMemory] = {}
CONFIG: dict[str, GuildConfig] = {}

# State anti-spam disimpan di memory proses, sedangkan memory percakapan
# disimpan ke JSON agar tetap ada setelah bot restart.
user_last_used: dict[int, float] = {}
user_request_times: defaultdict[int, deque[float]] = defaultdict(deque)
user_recent_prompts: defaultdict[int, deque[tuple[float, str]]] = defaultdict(deque)
user_last_notice: dict[int, float] = {}


# =========================
# JSON HELPERS
# =========================
def load_json(path: Path, default: Any) -> Any:
    """Baca JSON dengan aman; file rusak tidak boleh membuat bot mati."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as error:
        logger.warning("Gagal membaca %s: %s", path, error)
        return default


def save_json(path: Path, data: Any) -> None:
    """Simpan atomik supaya file memory tidak setengah tertulis."""
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def clean_history(value: Any) -> list[dict[str, str]]:
    """Normalisasi history lama dan baru ke format OpenAI."""
    if not isinstance(value, list):
        return []

    cleaned: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        role = item.get("role")
        if role == "model":
            role = "assistant"
        if role not in {"user", "assistant"}:
            continue
        entry = {"role": role, "text": item["text"].strip()}
        if entry["text"]:
            if isinstance(item.get("author"), str) and item["author"].strip():
                entry["author"] = item["author"].strip()
            cleaned.append(entry)
    return cleaned


def load_memory() -> tuple[dict[str, UserMemory], dict[str, ChannelMemory]]:
    """Muat format lama sekaligus format v2.9.

    Format lama berisi langsung ``{user_id: {history: [...]}}``. Format baru
    memisahkan memory user dan channel, sehingga upgrade tidak menghilangkan
    percakapan lama.
    """
    raw = load_json(MEMORY_FILE, {})
    if not isinstance(raw, dict):
        return {}, {}

    raw_users = raw.get("users") if isinstance(raw.get("users"), dict) else raw
    raw_channels = raw.get("channels", {})
    users: dict[str, UserMemory] = {}
    channels: dict[str, ChannelMemory] = {}

    if isinstance(raw_users, dict):
        for user_id, payload in raw_users.items():
            if isinstance(payload, dict):
                users[str(user_id)] = UserMemory(clean_history(payload.get("history")))

    if isinstance(raw_channels, dict):
        for channel_id, payload in raw_channels.items():
            if isinstance(payload, dict):
                channels[str(channel_id)] = ChannelMemory(
                    clean_history(payload.get("history"))
                )

    return users, channels


def save_memory(
    memory: dict[str, UserMemory],
    channel_memory: dict[str, ChannelMemory],
) -> None:
    save_json(
        MEMORY_FILE,
        {
            "users": {user_id: asdict(value) for user_id, value in memory.items()},
            "channels": {
                channel_id: asdict(value)
                for channel_id, value in channel_memory.items()
            },
        },
    )


def load_config() -> dict[str, GuildConfig]:
    raw = load_json(CONFIG_FILE, {})
    result: dict[str, GuildConfig] = {}
    if not isinstance(raw, dict):
        return result

    for guild_id, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        channels = payload.get("ai_channels", [])
        if not isinstance(channels, list):
            channels = []
        cleaned: list[int] = []
        for channel_id in channels:
            try:
                cleaned.append(int(channel_id))
            except (TypeError, ValueError):
                continue
        result[str(guild_id)] = GuildConfig(ai_channels=cleaned)
    return result


def save_config(config: dict[str, GuildConfig]) -> None:
    save_json(CONFIG_FILE, {guild_id: asdict(value) for guild_id, value in config.items()})


MEMORY, CHANNEL_MEMORY = load_memory()
CONFIG = load_config()


# =========================
# GENERAL HELPERS
# =========================
def is_rude(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in BAD_WORDS)


def remove_bot_mention(content: str, bot_id: int) -> str:
    return re.sub(rf"<@!?{bot_id}>", "", content).strip()


def get_guild_cfg(guild_id: int) -> GuildConfig:
    key = str(guild_id)
    if key not in CONFIG:
        CONFIG[key] = GuildConfig(ai_channels=[])
    return CONFIG[key]


def trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(history) <= MAX_HISTORY_TURNS * 2:
        return history
    return history[-(MAX_HISTORY_TURNS * 2) :]


def split_text(text: str, limit: int = MAX_REPLY_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return ["Maaf, Pak Burhan belum mendapat jawaban. Coba ulangi pertanyaannya ya."]
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut == -1 or cut < limit // 2:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    return [part for part in parts if part]


def cooldown_left(user_id: int) -> float:
    last = user_last_used.get(user_id, 0.0)
    return max(0.0, COOLDOWN_SECONDS - (time.monotonic() - last))


def check_spam_and_cooldown(user_id: int, prompt: str) -> tuple[bool, Optional[str]]:
    """Kembalikan izin dan pesan opsional.

    Spam berulang diabaikan tanpa balasan tambahan agar bot tidak ikut
    memenuhi channel dengan pesan cooldown.
    """
    now = time.monotonic()
    requests = user_request_times[user_id]
    while requests and now - requests[0] > SPAM_WINDOW_SECONDS:
        requests.popleft()

    recent = user_recent_prompts[user_id]
    while recent and now - recent[0][0] > SPAM_WINDOW_SECONDS:
        recent.popleft()

    normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
    repeated = sum(1 for _, value in recent if value == normalized)
    if len(requests) >= SPAM_MAX_REQUESTS or repeated >= 2:
        return False, None

    wait = cooldown_left(user_id)
    if wait > 0:
        last_notice = user_last_notice.get(user_id, 0.0)
        if now - last_notice >= COOLDOWN_SECONDS:
            user_last_notice[user_id] = now
            return False, f"Tunggu sebentar ya, coba lagi dalam {wait:.0f} detik."
        return False, None

    user_last_used[user_id] = now
    requests.append(now)
    recent.append((now, normalized))
    return True, None


def cleanup_spam_tracking() -> None:
    """Buang entri lama dari dict pelacak spam.

    `user_request_times`/`user_recent_prompts` adalah defaultdict, jadi
    tiap user unik yang pernah kirim pesan selalu punya entri permanen di
    memory proses walau isinya sudah kosong. Tanpa dibersihkan, ini jadi
    memory leak kecil yang terus tumbuh selama bot hidup.
    """
    now = time.monotonic()
    tracked_ids = (
        set(user_last_used)
        | set(user_request_times)
        | set(user_recent_prompts)
        | set(user_last_notice)
    )
    for tracking_user_id in tracked_ids:
        requests = user_request_times.get(tracking_user_id)
        if requests:
            while requests and now - requests[0] > SPAM_WINDOW_SECONDS:
                requests.popleft()

        recent = user_recent_prompts.get(tracking_user_id)
        if recent:
            while recent and now - recent[0][0] > SPAM_WINDOW_SECONDS:
                recent.popleft()

        idle_long_enough = (
            now - user_last_used.get(tracking_user_id, 0.0) > STALE_TRACKING_SECONDS
        )
        is_empty = not requests and not recent
        if is_empty and idle_long_enough:
            user_last_used.pop(tracking_user_id, None)
            user_request_times.pop(tracking_user_id, None)
            user_recent_prompts.pop(tracking_user_id, None)
            user_last_notice.pop(tracking_user_id, None)


@tasks.loop(minutes=30)
async def cleanup_spam_tracking_task() -> None:
    cleanup_spam_tracking()


def get_context(user_id: int, channel_id: int) -> list[dict[str, str]]:
    """Gabungkan konteks channel dan memory personal secara ringkas."""
    channel_history = CHANNEL_MEMORY.get(str(channel_id), ChannelMemory([])).history
    user_history = MEMORY.get(str(user_id), UserMemory([])).history
    return trim_history(channel_history) + trim_history(user_history)


JAKARTA_TZ = pytz.timezone("Asia/Jakarta")
HARI_ID = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
BULAN_ID = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)


def get_time_context() -> str:
    """Info waktu WIB saat ini, dihitung langsung tiap dipanggil (bukan
    dari task/loop background) supaya selalu real-time tanpa overhead."""
    now = datetime.now(JAKARTA_TZ)
    hari = HARI_ID[now.weekday()]
    bulan = BULAN_ID[now.month - 1]
    tanggal_lengkap = f"{hari}, {now.day} {bulan} {now.year}"
    jam_lengkap = now.strftime("%H:%M:%S")
    is_larut_malam = now.hour >= 23 or now.hour < 4

    catatan = (
        "Ini tergolong larut malam."
        if is_larut_malam
        else "Ini bukan waktu larut malam."
    )

    return (
        f"[Waktu saat ini: {tanggal_lengkap}, pukul {jam_lengkap} WIB. {catatan} "
        "Gunakan info waktu ini HANYA kalau relevan -- misalnya sapaan "
        "pagi/siang/sore/malam, atau saat ingin menegur dengan lembut kalau "
        "ada yang chat larut malam. Jangan sebutkan jam/tanggal di setiap "
        "balasan kalau tidak nyambung dengan pertanyaannya.]"
    )


def build_messages(
    history: list[dict[str, str]],
    user_text: str,
    author_name: str,
) -> list[dict[str, str]]:
    system_content = f"{SYSTEM_PROMPT}\n\n{get_time_context()}"
    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    for item in history:
        content = item["text"]
        if item.get("role") == "user" and item.get("author"):
            content = f"[{item['author']}]: {content}"
        messages.append({"role": item["role"], "content": content})
    messages.append({"role": "user", "content": f"[{author_name}]: {user_text}"})
    return messages


# =========================
# WEB SEARCH (Tavily API)
# =========================
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

SEARCH_FILLER_PHRASES = (
    "cari di internet",
    "cari online",
    "pencarian internet",
    "search web",
    "web search",
    "referensi online",
    "tolong carikan",
    "coba carikan",
    "coba cari",
    "carikan",
    "cariin",
    "pak burhan",
    "tolong",
    "please",
)


SEARCH_FILLER_WORDS = ("dong", "ya", "nih", "sih", "deh", "kah", "kok", "nah")


def clean_search_query(prompt: str, max_words: int = 12) -> str:
    """Ubah prompt obrolan jadi query pencarian yang pendek & fokus."""
    cleaned = prompt.lower()
    for phrase in SEARCH_FILLER_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    for word in SEARCH_FILLER_WORDS:
        cleaned = re.sub(rf"\b{word}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return prompt.strip()[:100]
    words = cleaned.split(" ")
    return " ".join(words[:max_words])


def needs_web_search(prompt: str) -> bool:
    lowered = prompt.lower()
    keywords = (
        "cari di internet",
        "cari online",
        "pencarian internet",
        "search web",
        "web search",
        "google",
        "berita terbaru",
        "berita hari ini",
        "terkini",
        "terbaru",
        "sumber",
        "referensi online",
    )
    return any(keyword in lowered for keyword in keywords)


def _search_web_sync(query: str) -> list[dict[str, str]]:
    if not TAVILY_API_KEY:
        logger.warning("TAVILY_API_KEY belum diisi, pencarian web dilewati.")
        return []

    payload = json.dumps(
        {
            "query": query,
            "max_results": MAX_SEARCH_RESULTS,
            "search_depth": "basic",
            "topic": "general",
        }
    ).encode("utf-8")
    request = Request(
        TAVILY_SEARCH_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {TAVILY_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(request, timeout=12) as response:
        body = json.loads(response.read().decode("utf-8", errors="replace"))

    results: list[dict[str, str]] = []
    for item in body.get("results", [])[:MAX_SEARCH_RESULTS]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
            }
        )
    return results


async def search_web(query: str) -> list[dict[str, str]]:
    try:
        return await asyncio.to_thread(_search_web_sync, query[:400])
    except Exception as error:
        logger.warning("Pencarian web gagal: %s", error)
        return []


def format_search_results(results: list[dict[str, str]]) -> str:
    if not results:
        return "[PENCARIAN WEB]\nTidak ada hasil pencarian yang berhasil diambil."
    lines = ["[PENCARIAN WEB - gunakan sebagai sumber, jangan mengarang]"]
    for index, result in enumerate(results, start=1):
        title = re.sub(r"\s+", " ", result["title"]).strip()
        snippet = re.sub(r"\s+", " ", result["snippet"]).strip()
        lines.append(f"{index}. {title}\nURL: {result['url']}\nRingkasan: {snippet}")
    return "\n".join(lines)


# =========================
# PDF READER
# =========================
def _extract_pdf_sync(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        if text:
            pages.append(text.strip())
            total += len(text)
        if total >= MAX_PDF_TEXT_CHARS:
            break
    return "\n\n".join(pages)[:MAX_PDF_TEXT_CHARS].strip()


async def read_pdf_attachment(attachment: discord.Attachment) -> str:
    if attachment.size and attachment.size > MAX_PDF_BYTES:
        return f"PDF `{attachment.filename}` terlalu besar. Batasnya 8 MB."
    try:
        data = await attachment.read()
        text = await asyncio.to_thread(_extract_pdf_sync, data)
        if not text:
            return f"PDF `{attachment.filename}` tidak memiliki teks yang bisa dibaca."
        return f"[ISI PDF: {attachment.filename}]\n{text}"
    except Exception as error:
        logger.warning("Gagal membaca PDF %s: %s", attachment.filename, error)
        return f"PDF `{attachment.filename}` gagal dibaca. Pastikan file tidak rusak."


async def enrich_prompt(prompt: str, attachments: list[discord.Attachment]) -> str:
    pdf_attachments = [
        attachment
        for attachment in attachments
        if attachment.filename.lower().endswith(".pdf")
        or attachment.content_type == "application/pdf"
    ]
    if not pdf_attachments:
        return prompt

    pdf_parts = await asyncio.gather(
        *(read_pdf_attachment(attachment) for attachment in pdf_attachments)
    )
    base_prompt = prompt.strip() or "Tolong baca PDF ini dan jelaskan atau rangkum isinya."
    return f"{base_prompt}\n\n" + "\n\n".join(pdf_parts)


# =========================
# AI + MEMORY
# =========================
async def ask_openrouter(
    user_id: int,
    channel_id: int,
    prompt: str,
    author_name: str,
) -> str:
    if openrouter_client is None:
        raise RuntimeError("OPENROUTER_API_KEY belum tersedia.")

    history = get_context(user_id, channel_id)
    messages = build_messages(history, prompt[:MAX_PROMPT_CHARS], author_name)
    response = await openrouter_client.chat.completions.create(
        model=AI_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=8192,
    )
    answer = response.choices[0].message.content if response.choices else None
    return (answer or "").strip() or (
        "Maaf, Pak Burhan belum mendapat jawaban yang jelas. "
        "Coba ulangi pertanyaannya ya."
    )


async def save_turn(
    user_id: int,
    channel_id: int,
    author_name: str,
    user_text: str,
    model_text: str,
) -> None:
    async with memory_lock:
        user_memory = MEMORY.setdefault(str(user_id), UserMemory(history=[]))
        user_memory.history.extend(
            [
                {"role": "user", "text": user_text},
                {"role": "assistant", "text": model_text},
            ]
        )
        user_memory.history = trim_history(user_memory.history)

        channel_memory = CHANNEL_MEMORY.setdefault(
            str(channel_id), ChannelMemory(history=[])
        )
        channel_memory.history.extend(
            [
                {"role": "user", "text": user_text, "author": author_name},
                {"role": "assistant", "text": model_text},
            ]
        )
        channel_memory.history = trim_history(channel_memory.history)
        # Nulis JSON ke disk dijalankan di thread terpisah supaya tidak
        # ngeblok event loop bot (dulu ini blocking call langsung di sini).
        await asyncio.to_thread(save_memory, MEMORY, CHANNEL_MEMORY)


async def reset_memory(user_id: int) -> None:
    async with memory_lock:
        MEMORY.pop(str(user_id), None)
        await asyncio.to_thread(save_memory, MEMORY, CHANNEL_MEMORY)


async def prepare_ai_prompt(
    prompt: str,
    attachments: list[discord.Attachment],
    force_search: bool = False,
) -> tuple[str, bool]:
    # Cek permintaan pencarian dari prompt ASLI user saja. Kalau dicek dari
    # `enriched` (yang sudah berisi teks PDF), bagian "Sumber"/"Daftar
    # Pustaka" pada PDF tugas sekolah bisa memicu pencarian web yang
    # sebenarnya tidak diminta user.
    wants_search = force_search or needs_web_search(prompt)
    enriched = await enrich_prompt(prompt, attachments)
    if wants_search:
        results = await search_web(clean_search_query(prompt))
        enriched += "\n\n" + format_search_results(results)
    return enriched[:MAX_PROMPT_CHARS], wants_search


async def reply_text(target: discord.abc.Messageable, text: str) -> None:
    for chunk in split_text(text):
        await target.send(chunk)


async def handle_prompt(
    target: discord.abc.Messageable,
    user: discord.abc.User,
    prompt: str,
    channel_id: int,
    attachments: Optional[list[discord.Attachment]] = None,
) -> None:
    if not prompt.strip() and not attachments:
        return

    if is_rude(prompt):
        await target.send(POLITE_TOXIC_REPLY)
        return

    allowed, notice = check_spam_and_cooldown(user.id, prompt or "pdf")
    if not allowed:
        if notice:
            await target.send(notice)
        return

    try:
        author_name = getattr(user, "display_name", user.name)
        will_search = needs_web_search(prompt)
        status_msg: Optional[discord.Message] = None

        if will_search:
            kwargs: dict[str, Any] = {
                "content": (
                    "🔍 **Pak Burhan sedang mencari** informasi di internet...\n"
                    f"Pesanan **{author_name}**"
                )
            }
            if SEARCHING_GIF.exists():
                kwargs["file"] = discord.File(SEARCHING_GIF)
            status_msg = await target.send(**kwargs)

        prepared_prompt, _ = await prepare_ai_prompt(prompt, attachments or [])

        async with target.typing():
            answer = await ask_openrouter(
                user.id,
                channel_id,
                prepared_prompt,
                author_name,
            )
            await save_turn(
                user.id,
                channel_id,
                author_name,
                prompt or "Membaca PDF terlampir",
                answer,
            )

            if status_msg is not None:
                try:
                    # Ganti teks ke mode merangkum + pasang ulang GIF (pakai attachments, bukan file)
                    edit_kwargs = {
                        "content": (
                            "📝 **Pak Burhan merangkum** hasil pencarian...\n"
                            f"Pesanan **{author_name}**"
                        ),
                        "attachments": [],
                    }
                    if SEARCHING_GIF.exists():
                        edit_kwargs["attachments"] = [discord.File(SEARCHING_GIF)]
                    await status_msg.edit(**edit_kwargs)
                except Exception:
                    pass

                try:
                    await status_msg.delete()
                except Exception:
                    pass

            await reply_text(target, answer)
    except Exception as error:
        logger.exception("Gagal memproses pesan user %s: %s", user.id, error)
        await target.send(
            "Maaf, ada kendala saat memproses pertanyaan itu. "
            "Coba lagi sebentar ya."
        )


# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class PakBurhanBot(commands.Bot):
    async def setup_hook(self) -> None:
        try:
            await self.tree.sync()
            logger.info("Slash command berhasil disinkronkan.")
        except Exception as error:
            logger.exception("Gagal sinkronisasi slash command: %s", error)

        if not cleanup_spam_tracking_task.is_running():
            cleanup_spam_tracking_task.start()


bot = PakBurhanBot(
    command_prefix=commands.when_mentioned_or("!pb"),
    intents=intents,
)


@bot.event
async def on_ready() -> None:
    logger.info("Bot Pak Burhan online sebagai %s", bot.user)


@bot.event
async def on_message(message: discord.Message) -> None:
    try:
        if message.author.bot or bot.user is None:
            return

        if message.guild is None:
            prompt = message.content.strip()
            if prompt or message.attachments:
                await handle_prompt(
                    message.channel,
                    message.author,
                    prompt,
                    message.channel.id,
                    message.attachments,
                )
            return

        cfg = get_guild_cfg(message.guild.id)
        is_ai_room = message.channel.id in cfg.ai_channels

        if is_ai_room:
            prompt = remove_bot_mention(message.content, bot.user.id)
            if prompt or message.attachments:
                await handle_prompt(
                    message.channel,
                    message.author,
                    prompt,
                    message.channel.id,
                    message.attachments,
                )
            return

        if bot.user.mentioned_in(message):
            prompt = remove_bot_mention(message.content, bot.user.id)
            if prompt or message.attachments:
                await handle_prompt(
                    message.channel,
                    message.author,
                    prompt,
                    message.channel.id,
                    message.attachments,
                )
            else:
                await message.channel.send("Ada yang bisa Pak Burhan bantu?")
            return

        await bot.process_commands(message)
    except Exception as error:
        logger.exception("Error pada on_message: %s", error)


@bot.tree.command(name="ask", description="Tanya Pak Burhan")
@app_commands.describe(pertanyaan="Tulis pertanyaanmu")
async def ask(interaction: discord.Interaction, pertanyaan: str) -> None:
    try:
        await interaction.response.defer(thinking=True)
        if is_rude(pertanyaan):
            await interaction.followup.send(POLITE_TOXIC_REPLY)
            return

        allowed, notice = check_spam_and_cooldown(interaction.user.id, pertanyaan)
        if not allowed:
            if notice:
                await interaction.followup.send(notice)
            return

        author_name = getattr(interaction.user, "display_name", interaction.user.name)
        will_search = needs_web_search(pertanyaan)
        status_msg: Optional[discord.WebhookMessage] = None

        if will_search:
            kwargs: dict[str, Any] = {
                "content": (
                    "🔍 **Pak Burhan sedang mencari** informasi di internet...\n"
                    f"Pesanan **{author_name}**"
                ),
                "wait": True,
            }
            if SEARCHING_GIF.exists():
                kwargs["file"] = discord.File(SEARCHING_GIF)
            status_msg = await interaction.followup.send(**kwargs)

        prepared_prompt, _ = await prepare_ai_prompt(pertanyaan, [])
        channel_id = interaction.channel_id or interaction.user.id

        answer = await ask_openrouter(
            interaction.user.id,
            channel_id,
            prepared_prompt,
            author_name,
        )
        await save_turn(
            interaction.user.id,
            channel_id,
            author_name,
            pertanyaan,
            answer,
        )

        if status_msg is not None:
            try:
                edit_kwargs = {
                    "content": (
                        "📝 **Pak Burhan merangkum** hasil pencarian...\n"
                        f"Pesanan **{author_name}**"
                    ),
                    "attachments": [],
                }
                if SEARCHING_GIF.exists():
                    edit_kwargs["attachments"] = [discord.File(SEARCHING_GIF)]
                await status_msg.edit(**edit_kwargs)
            except Exception:
                pass

            try:
                await status_msg.delete()
            except Exception:
                pass

        for chunk in split_text(answer):
            await interaction.followup.send(chunk)
    except Exception as error:
        logger.exception("Error pada /ask: %s", error)
        await interaction.followup.send(
            "Maaf, ada kendala saat memproses pertanyaan itu. Coba lagi sebentar ya."
        )


@bot.tree.command(
    name="searching",
    description="Tanya Pak Burhan, dijawab pakai hasil pencarian internet",
)
@app_commands.describe(pertanyaan="Tulis pertanyaan yang mau dicari di internet")
async def searching(interaction: discord.Interaction, pertanyaan: str) -> None:
    try:
        await interaction.response.defer(thinking=True)
        if is_rude(pertanyaan):
            await interaction.followup.send(POLITE_TOXIC_REPLY)
            return

        allowed, notice = check_spam_and_cooldown(interaction.user.id, pertanyaan)
        if not allowed:
            if notice:
                await interaction.followup.send(notice)
            return

        # force_search=True: selalu cari web. Kirim status + GIF dulu.
        author_name = getattr(interaction.user, "display_name", interaction.user.name)
        kwargs: dict[str, Any] = {
            "content": (
                "🔍 **Pak Burhan sedang mencari** informasi di internet...\n"
                f"Pesanan **{author_name}**"
            ),
            "wait": True,
        }
        if SEARCHING_GIF.exists():
            kwargs["file"] = discord.File(SEARCHING_GIF)
        status_msg = await interaction.followup.send(**kwargs)

        prepared_prompt, _ = await prepare_ai_prompt(
            pertanyaan, [], force_search=True
        )
        channel_id = interaction.channel_id or interaction.user.id
        answer = await ask_openrouter(
            interaction.user.id,
            channel_id,
            prepared_prompt,
            author_name,
        )
        await save_turn(
            interaction.user.id,
            channel_id,
            author_name,
            pertanyaan,
            answer,
        )

        try:
            edit_kwargs = {
                "content": (
                    "📝 **Pak Burhan merangkum** hasil pencarian...\n"
                    f"Pesanan **{author_name}**"
                ),
                "attachments": [],
            }
            if SEARCHING_GIF.exists():
                edit_kwargs["attachments"] = [discord.File(SEARCHING_GIF)]
            await status_msg.edit(**edit_kwargs)
        except Exception:
            pass

        try:
            await status_msg.delete()
        except Exception:
            pass

        for chunk in split_text(answer):
            await interaction.followup.send(chunk)
    except Exception as error:
        logger.exception("Error pada /searching: %s", error)
        await interaction.followup.send(
            "Maaf, ada kendala saat mencari itu di internet. Coba lagi sebentar ya."
        )


@bot.tree.command(name="help", description="Lihat bantuan Pak Burhan")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "**Bantuan Pak Burhan v2.9.4**\n"
        "• Mention saya atau gunakan `/ask` untuk bertanya.\n"
        "• Kirim PDF bersama pertanyaan untuk dibaca, dirangkum, atau dianalisis.\n"
        "• `/searching` untuk tanya sambil dipastikan bot cari jawabannya di internet.\n"
        "• `/reset` menghapus memory percakapan personal kamu.\n"
        "• `/status` melihat status bot dan model yang aktif.\n"
        "• Admin: `/airoom enable`, `/airoom disable`, atau `/airoom list`."
    )


@bot.tree.command(name="reset", description="Hapus memori chat kamu")
async def reset(interaction: discord.Interaction) -> None:
    try:
        await reset_memory(interaction.user.id)
        await interaction.response.send_message(
            "Memori chat kamu sudah direset. Nah, kita mulai dari awal."
        )
    except Exception as error:
        logger.exception("Error pada /reset: %s", error)
        await interaction.response.send_message(
            "Maaf, memory belum bisa direset sekarang.", ephemeral=True
        )


@bot.tree.command(name="status", description="Lihat status bot")
async def status(interaction: discord.Interaction) -> None:
    try:
        mem = MEMORY.get(str(interaction.user.id), UserMemory(history=[]))
        place = (
            "DM"
            if interaction.guild is None
            else f"Server: {interaction.guild.name}"
        )
        await interaction.response.send_message(
            f"✅ Online\nModel: `{AI_MODEL}`\n{place}\n"
            f"Riwayatmu: `{len(mem.history)}` pesan\n"
            f"Endpoint: `{OPENROUTER_BASE_URL}`"
        )
    except Exception as error:
        logger.exception("Error pada /status: %s", error)


@bot.tree.command(name="persona", description="Lihat persona Pak Burhan")
async def persona(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        "Aku Pak Burhan, wali kelas 7D. Aku ramah, sabar, tegas, "
        "dan suka menjelaskan pelajaran langkah demi langkah."
    )


@bot.tree.command(name="airoom", description="Atur channel AI untuk server ini")
@app_commands.describe(
    aksi="enable / disable / list",
    channel="Channel yang ingin diatur; kosong berarti channel saat ini",
)
@app_commands.choices(
    aksi=[
        app_commands.Choice(name="enable", value="enable"),
        app_commands.Choice(name="disable", value="disable"),
        app_commands.Choice(name="list", value="list"),
    ]
)
@app_commands.checks.has_permissions(manage_guild=True)
async def airoom(
    interaction: discord.Interaction,
    aksi: app_commands.Choice[str],
    channel: Optional[discord.TextChannel] = None,
) -> None:
    try:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Command ini cuma bisa dipakai di server.",
                ephemeral=True,
            )
            return

        async with config_lock:
            cfg = get_guild_cfg(interaction.guild.id)
            channel_id = channel.id if channel else interaction.channel_id

            if aksi.value == "enable":
                if channel_id not in cfg.ai_channels:
                    cfg.ai_channels.append(channel_id)
                    await asyncio.to_thread(save_config, CONFIG)
                await interaction.response.send_message(
                    f"Channel ini sekarang jadi AI room: <#{channel_id}>",
                    ephemeral=True,
                )
                return

            if aksi.value == "disable":
                cfg.ai_channels = [
                    current
                    for current in cfg.ai_channels
                    if current != channel_id
                ]
                await asyncio.to_thread(save_config, CONFIG)
                await interaction.response.send_message(
                    f"AI room dimatikan: <#{channel_id}>",
                    ephemeral=True,
                )
                return

            active = cfg.ai_channels
            if not active:
                await interaction.response.send_message(
                    "Belum ada AI room yang aktif.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "AI room aktif: " + ", ".join(f"<#{item}>" for item in active),
                ephemeral=True,
            )
    except Exception as error:
        logger.exception("Error pada /airoom: %s", error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "Terjadi error saat mengatur AI room.",
                ephemeral=True,
            )


@airoom.error
async def airoom_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    try:
        if isinstance(error, app_commands.MissingPermissions):
            message = "Command ini butuh izin Manage Server."
        else:
            logger.exception("Error slash command airoom: %s", error)
            message = "Terjadi error saat menjalankan command itu."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        logger.exception("Gagal mengirim pesan error /airoom.")


def main() -> None:
    """Validasi konfigurasi dan jalankan bot tanpa traceback yang membingungkan."""
    missing = [
        name
        for name, value in (
            ("DISCORD_TOKEN", DISCORD_TOKEN),
            ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
        )
        if not value
    ]
    if missing:
        logger.error(
            "Bot belum dijalankan. Isi environment variable: %s",
            ", ".join(missing),
        )
        return

    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.error("DISCORD_TOKEN tidak valid atau bot belum diizinkan.")
    except KeyboardInterrupt:
        logger.info("Bot dihentikan.")
    except Exception as error:
        logger.exception("Bot berhenti karena error yang tidak terduga: %s", error)


if __name__ == "__main__":
    main()