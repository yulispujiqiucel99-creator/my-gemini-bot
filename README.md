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
   - `DATA_DIR` — opsional, folder untuk memory JSON. Untuk Railway Volume yang
     di-mount ke `/app/data`, isi `DATA_DIR=/app/data`.
   - `TTS_VOICE` — opsional, default `id-ID-ArdiNeural` untuk command `/tts`.
   - `TTS_MAX_CHARS` — opsional, batas naskah hasil ringkasan AI; default 800 karakter.
   - `TTS_SOURCE_MAX_CHARS` — opsional, batas teks mentah sebelum diringkas AI; default 12.000 karakter.
   - `TTS_COOLDOWN_SECONDS` — opsional, jeda per user; default 15 detik.
4. Jalankan:
   `python bot.py`

### Text-to-speech

Command `/tts` mengirim teks mentah ke OpenRouter terlebih dahulu. AI akan mengambil
inti informasi dan mengubahnya menjadi naskah bahasa Indonesia yang singkat, padat,
jelas, dan enak didengar; jadi teks tidak dibacakan mentah-mentah. Setelah itu, naskah
hasil edit dibersihkan dari simbol aneh lalu diubah menjadi file MP3 menggunakan Edge
TTS dan dikirim sebagai attachment Discord. Pesan yang sama juga menampilkan naskah
final yang benar-benar dibacakan agar isi audio dapat dicek. Fitur ini hanya berjalan
melalui permintaan manual; bot tidak mengirim audio secara otomatis. Teks mentah dibatasi oleh
`TTS_SOURCE_MAX_CHARS`, sedangkan naskah hasil AI dibatasi default 800 karakter secara
konservatif agar audio sekitar maksimal 1,5 menit; durasi aktual tetap bergantung pada
kecepatan suara. Setiap user memiliki cooldown `TTS_COOLDOWN_SECONDS`, dan file MP3
sementara dihapus setelah Discord selesai mengunggahnya. Edge TTS tidak memerlukan API
key, tetapi tetap dapat mengalami throttling atau perubahan layanan karena bukan API
komersial dengan SLA.

Jangan membagikan file `.env` karena berisi token rahasia.
