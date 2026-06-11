# FessBot v2 — Advanced Telegram Repost Bot

Bot Telegram canggih untuk auto-repost foto/video dari channel partner ke channel utama.
Navigasi berbasis tombol (halaman berubah, bukan pesan baru). Semua data di MongoDB.

## Perubahan v2

- ✅ Navigasi halaman: layar berubah (edit_text), bukan memunculkan pesan baru
- ✅ Broadcast interaktif: tombol → ketik → preview → kirim (tanpa command)
- ✅ FloodWait fix: exponential backoff + skip jika terlalu lama
- ✅ Fitur user diperluas: Statistik, Notifikasi, Riwayat Repost, Bantuan
- ✅ Fitur owner diperluas: Aktivitas Log, Pengaturan Bot, Top Channel, Blacklist interaktif
- ✅ Repost lebih luas: foto, video, dokumen, audio, teks
- ✅ Notifikasi per-user: bisa toggle tiap jenis notif
- ✅ Log aktivitas sistem di MongoDB
- ✅ Riwayat broadcast tersimpan di MongoDB
- ✅ Semua data 100% MongoDB

## Fitur User

| Fitur | Keterangan |
|---|---|
| 📂 My Channel | Daftar channel terdaftar + manage |
| 📊 Statistik Saya | Stats hari ini / 7 hari / 30 hari / all-time per channel |
| 🔔 Notifikasi | Toggle notif repost, blacklist, status channel |
| ℹ️ Info Bot | Info global bot |
| ❓ Bantuan | Panduan lengkap penggunaan |
| 📋 Riwayat Repost | Link 7 repost terakhir dari tiap channel |
| ❌ Lepas Channel | Lepas channel dari FessBot |

## Fitur Owner

| Fitur | Keterangan |
|---|---|
| 📊 Dashboard | Stats real-time + progress bar + top 5 channel |
| 📋 Partner | Daftar partner + paginasi + detail |
| 🔎 Cari Channel | Search partner by nama/username |
| 🏆 Top Channel | 10 channel dengan repost terbanyak |
| 📣 Broadcast | Interaktif: pilih target → ketik → preview → kirim |
| 📜 Riwayat Broadcast | 5 broadcast terakhir + hasil |
| 🚫 Blacklist | Tambah/hapus via tombol (tidak perlu command) |
| 🔧 Maintenance | Toggle maintenance mode |
| 📝 Aktivitas | Log aktivitas sistem real-time |
| ⚙️ Pengaturan | Toggle fitur bot (notif owner, auto-delete, text repost) |
| ⏸/▶️ Pause/Run | Pause/aktifkan channel dari detail panel |

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Isi `.env`:
```
API_ID=
API_HASH=
BOT_TOKEN=
MONGO_URI=mongodb+srv://...
MAIN_CHANNEL_ID=
MAIN_CHANNEL_USERNAME=
OWNER_ID=
BOT_USERNAME=
```

3. Jalankan:
```bash
python main.py
```

## Struktur File

```
fessbot-v2/
├── main.py              # Entry point
├── config.py            # Konfigurasi env
├── utils.py             # Helper: membership, paginate, safe_send, nav_to
├── requirements.txt
├── .env
├── db/
│   ├── mongo.py         # Koneksi MongoDB + collections
│   └── helpers.py       # Semua operasi database
└── plugins/
    ├── start.py         # /start, Info Bot, Bantuan
    ├── owner.py         # Panel owner lengkap
    ├── broadcast.py     # Broadcast interaktif
    ├── mychannel.py     # Panel user: My Channel, Statistik, Notif
    ├── repost.py        # Auto-repost + deteksi admin
    ├── membership.py    # Cek join + notif member baru
    └── guard.py         # Blokir saat maintenance
```

## Collections MongoDB

| Collection | Isi |
|---|---|
| `partners` | Channel partner terdaftar |
| `posts` | Map partner_msg_id → main_msg_id |
| `users` | User terdaftar |
| `blacklist` | Kata-kata terlarang |
| `settings` | Maintenance mode + setting bot |
| `broadcasts` | Riwayat broadcast |
| `activity` | Log aktivitas sistem |
| `notifications` | Setting notif per user |

## Catatan Penting

- **Tampilan caption channel tidak diubah** — format repost tetap sama
- **Broadcast** sepenuhnya interaktif via tombol, tidak ada command `/broadcast` lagi
- **FloodWait** ditangani otomatis dengan exponential backoff (skip jika >60 detik)
- **Navigasi** menggunakan edit_text — halaman berubah, bukan pesan baru
- Semua data 100% tersimpan di MongoDB
