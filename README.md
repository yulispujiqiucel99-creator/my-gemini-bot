# Pak Burhan v2.9.1

Discord bot Pak Burhan dengan OpenRouter, memory user/channel, AI Room, slash commands, anti-spam, anti-toxic, web search, dan pembaca PDF.

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
4. Jalankan:
   `python bot.py`

Jangan membagikan file `.env` karena berisi token rahasia.
