# FessBot — Channel Repost Bot

Bot Pyrogram untuk meneruskan postingan channel partner ke channel utama secara otomatis.

---

## Instalasi di Termux

```bash
pkg update && pkg install python git -y
pip install -r requirements.txt
```

## Konfigurasi

Edit file `.env` dan isi semua variabel:

```
API_ID            = dari https://my.telegram.org
API_HASH          = dari https://my.telegram.org
BOT_TOKEN         = dari @BotFather
MONGO_URI         = connection string MongoDB Atlas
MAIN_CHANNEL_ID   = ID channel utama (format: -100xxxxxxxxxx)
MAIN_CHANNEL_USERNAME = username channel utama (tanpa @)
OWNER_ID          = user ID Telegram kamu (cek via @userinfobot)
BOT_USERNAME      = username bot (tanpa @)
```

## Jalankan Bot

```bash
python main.py
```

## Persiapan Penting

1. **Bot harus dijadikan admin di channel utama** dengan hak:
   - Post Messages
   - Delete Messages
   - Read Messages (agar bisa cek membership)

2. **MongoDB Atlas** — buat cluster gratis di https://mongodb.com/atlas

---

## Struktur File

```
fessbot/
├── main.py              # Entry point
├── config.py            # Load .env
├── utils.py             # Helper: cek membership, pagination
├── .env                 # Konfigurasi (jangan di-share!)
├── requirements.txt
├── db/
│   ├── mongo.py         # Koneksi MongoDB
│   └── helpers.py       # CRUD functions
└── plugins/
    ├── start.py         # /start — welcome owner & user
    ├── membership.py    # Cek join, notif member baru
    ├── repost.py        # Auto-repost + deteksi bot dijadikan admin
    ├── mychannel.py     # Tombol My Channel untuk user
    ├── owner.py         # Panel owner: /pause /run /stats /listpartner
    └── guard.py         # Blokir user yang belum join
```

## Perintah Owner

| Perintah | Fungsi |
|---|---|
| `/pause <ID> <alasan>` | Hentikan forward dari channel partner |
| `/run <ID> <alasan>` | Aktifkan kembali forward |
| `/stats` | Statistik bot |
| `/listpartner` | Daftar semua channel partner |
