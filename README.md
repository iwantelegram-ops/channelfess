# FessBot — Advanced Telegram Repost Bot

Bot Telegram untuk auto-repost foto/video dari channel partner ke channel utama.

## Fitur

### User
- `/start` — Mulai & lihat panduan
- `📂 My Channel` — Kelola channel terdaftar
- `📊 Statistik Channel` — Lihat total repost per channel
- `ℹ️ Info Bot` — Info global bot
- Toggle pause/aktif channel sendiri

### Owner
- `📊 Dashboard` — Statistik real-time + bar chart
- `📋 Channel Partner` — Daftar semua partner + detail
- `🔎 Cari Channel` — Search partner by nama/username
- `📣 Broadcast` — Blast pesan ke semua user / owner partner
- `🚫 Blacklist` — Blokir kata tertentu dari repost
- `🔧 Maintenance` — Aktifkan/nonaktifkan maintenance mode

### Fitur Otomatis
- Repost real-time foto & video
- Notifikasi ke owner setiap postingan berhasil di-repost
- Filter blacklist kata otomatis
- Notifikasi jika bot dicopot dari admin
- Counter repost per channel
- Auto-hapus repost jika post asli dihapus

## Commands Owner
| Command | Fungsi |
|---|---|
| `/stats` | Lihat statistik |
| `/listpartner` | Daftar partner |
| `/pause <ID> <alasan>` | Jeda channel |
| `/run <ID> <alasan>` | Aktifkan channel |
| `/broadcast <pesan>` | Blast ke semua user |
| `/broadcastpartner <pesan>` | Blast ke owner partner |
| `/addbl <kata>` | Tambah blacklist |
| `/rmbl <kata>` | Hapus blacklist |
| `/listbl` | Lihat daftar blacklist |
| `/maintenance <alasan>` | Aktifkan maintenance |
| `/unmaintenance` | Nonaktifkan maintenance |

## Setup

1. Clone repo & install dependencies
```bash
pip install -r requirements.txt
```

2. Copy `.env` dan isi konfigurasi:
```
API_ID=
API_HASH=
BOT_TOKEN=
MONGO_URI=
MAIN_CHANNEL_ID=
MAIN_CHANNEL_USERNAME=
OWNER_ID=
BOT_USERNAME=
```

3. Jalankan:
```bash
python main.py
```
