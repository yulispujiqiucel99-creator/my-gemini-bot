# Pak Burhan v2.9.4

Discord bot Pak Burhan dengan OpenRouter, memory user/channel, AI Room, slash commands, anti-spam, anti-toxic, web search (Tavily), dan pembaca PDF.

## Perbaikan di v2.9.4

- Web search diganti total: dari scraping HTML DuckDuckGo (gak stabil, kadang
  balikin hasil random/gak nyambung) ke **Tavily API** yang memang didesain
  buat AI agent. Butuh `TAVILY_API_KEY` baru di `.env` (gratis, lihat bawah).

## Perbaikan di v2.9.3

- Tambah command `/searching` — beda dari `/ask`, ini SELALU cari ke internet
  dulu sebelum jawab (gak nebak dari kata kunci di prompt). Cocok buat
  pertanyaan soal kejadian terkini yang gak kepikiran bakal kena kata kunci
  pemicu, misal "siapa pemenang piala dunia 2026?".

## Perbaikan di v2.9.1

- Pencarian web tidak lagi kepicu oleh isi PDF (mis. bagian "Sumber"/"Daftar
  Pustaka" di PDF tugas) — sekarang hanya dicek dari prompt asli user.
- Penulisan `data/memory.json` dan `data/config.json` dipindah ke thread
  terpisah (`asyncio.to_thread`) supaya tidak ngeblok bot saat menyimpan.
- Mention bot (`<@id>`) sekarang selalu dibersihkan dari prompt, termasuk di
  channel AI Room (sebelumnya hanya dibersihkan saat bot di-mention biasa).
- `.replit` dirapikan jadi konfigurasi Python murni, dan deployment target
  diganti ke Reserved VM (`gce`) karena `autoscale` tidak cocok untuk bot
  yang perlu selalu online lewat koneksi gateway Discord.
- Dict pelacak anti-spam sekarang dibersihkan otomatis tiap 30 menit supaya
  tidak menumpuk terus selama bot berjalan lama.

## Menjalankan

1. Install dependency:
   `pip install -r requirements.txt`
2. Salin `.env.example` menjadi `.env`.
3. Isi:
   - `DISCORD_TOKEN`
   - `OPENROUTER_API_KEY`
   - `AI_MODEL` (default: `qwen/qwen3.5-9b`)
   - `TAVILY_API_KEY` — daftar gratis di tavily.com (1.000 pencarian/bulan,
     tanpa kartu kredit). Kalau dikosongkan, fitur web search dilewati
     (bot tetap jalan normal untuk fitur lain).
   - `DATABASE_URL` — opsional, berisi connection string PostgreSQL untuk
     memory permanen. Kalau dikosongkan, `/ingat` dan `/lupakan` memakai
     fallback lokal `data/permanent_memory.json`.
4. Jalankan:
   `python bot.py`

Jangan membagikan file `.env` karena berisi token rahasia.
