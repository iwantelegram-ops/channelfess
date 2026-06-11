# FessBot v3 — Panduan Instalasi

## ⚠️ PENTING: Migrasi dari Versi Lama

Jika kamu sebelumnya menjalankan bot lama, ikuti langkah di bawah dengan urutan yang tepat.

---

## Langkah 1 — Hapus plugin LAMA

Plugin-plugin ini sudah **digabung atau diganti**. Wajib dihapus sebelum menggunakan v3:

```bash
# Dari direktori bot kamu
rm -f plugins/mychannel.py
rm -f plugins/info_bot.py
rm -f plugins/owner.py       # ganti dengan versi baru
rm -f plugins/start.py       # ganti dengan versi baru
rm -f plugins/repost.py      # ganti dengan versi baru
rm -f plugins/broadcast.py   # ganti dengan versi baru
rm -f plugins/membership.py  # ganti dengan versi baru
rm -f plugins/guard.py       # ganti dengan versi baru
rm -f plugins/user.py        # jika ada dari versi sebelumnya
```

> `mychannel.py` dan `info_bot.py` sudah **digabung ke `plugins/user.py`**.

---

## Langkah 2 — Salin file dari ZIP ini

Salin **semua** file dari folder `bot-redesigned/` ke direktori botmu:

```
bot-redesigned/
├── config.py              → salin ke root
├── main.py                → salin ke root
├── utils.py               → salin ke root (menggantikan yang lama)
├── Procfile               → salin ke root
├── requirements.txt       → salin ke root
├── .env.example           → jadikan .env dan isi variabelnya
├── db/
│   ├── __init__.py
│   ├── helpers.py
│   ├── mongo.py
│   └── mongo_storage.py
└── plugins/
    ├── __init__.py
    ├── start.py
    ├── owner.py
    ├── user.py            ← BARU (gabungan mychannel + info_bot + notif)
    ├── repost.py
    ├── broadcast.py
    ├── membership.py
    └── guard.py
```

---

## Langkah 3 — Buat / perbarui .env

```env
API_ID=12345678
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/fessbot
MAIN_CHANNEL_ID=-1001234567890
MAIN_CHANNEL_USERNAME=nama_channel_utama
OWNER_ID=123456789
BOT_USERNAME=nama_bot_kamu
OWNER_USERNAME=username_owner
OWNER_NAME=Nama Owner
BOT_NAME=FessBot
BOT_DESC=Auto Repost Bot
```

---

## Langkah 4 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Langkah 5 — Jalankan

```bash
python main.py
```

---

## Daftar plugin yang ada di v3

| Plugin | Fungsi |
|---|---|
| `start.py` | `/start`, menu owner & user (full inline) |
| `owner.py` | Dashboard, partner, blacklist, maintenance, ban, export, caption template |
| `user.py` | My Channel, statistik, notifikasi, info bot, tutorial, bantuan |
| `repost.py` | Auto-repost foto/video/teks, media filter, caption kustom, auto-delete |
| `broadcast.py` | Broadcast ke semua user / owner partner |
| `membership.py` | Verifikasi join + welcome member baru |
| `guard.py` | Rate limit, ban check, `/cancel` global |

---

## ⚡ Fresh Install (tanpa migrasi)

Jika install dari awal (direktori kosong):

```bash
git clone / ekstrak ZIP ke folder baru
cp .env.example .env      # lalu isi variabel
pip install -r requirements.txt
python main.py
```
