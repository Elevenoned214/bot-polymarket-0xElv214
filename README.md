# Polymarket Trading Bot

Bot trading otomatis untuk Polymarket menggunakan strategi entry Window 1 (W1) dengan sistem Martingale.

---

## Cara Kerja Bot

Bot memantau market Polymarket setiap detik dan mencari peluang entry berdasarkan kondisi berikut:

- **Waktu entry:** Detik ke-30 sampai ke-80 dari market berjalan
- **Range harga:** 53¢ sampai 58¢ (YES atau NO)
- **Sistem taruhan:** Martingale — kalau kalah, taruhan berikutnya dinaikkan untuk menutup total kerugian sebelumnya
- **Order type:** Market order (langsung tereksekusi, bukan limit)
- **Auto-redeem:** Setelah market resolve, bot otomatis redeem posisi yang menang

### Alur Singkat

```
Bot nyala → Tunggu market baru → Cek harga di detik 30-80
→ Harga masuk range 53-58¢ → Entry → Tunggu resolve → Catat hasil
→ Kalau kalah → Naikkan taruhan (Martingale) → Ulangi
→ Kalau streak kalah > batas → Bot berhenti otomatis
```

---

## Komponen Bot

| File | Fungsi |
|------|--------|
| `bot_real.py` | Bot utama, eksekusi trading real |
| `bot_paper.py` | Bot simulasi (paper trading), tidak pakai uang asli |
| `telegram_bot.py` | Controller bot via Telegram |
| `dashboard.py` | Dashboard web untuk monitoring |
| `config_real.py` | Konfigurasi strategi (range harga, timing) |

---

## Fitur

- **Real Trading** — eksekusi order langsung ke Polymarket
- **Paper Trading** — simulasi tanpa modal, berjalan paralel untuk perbandingan
- **Telegram Controller** — kontrol bot dari HP via Telegram
- **Auto-redeem** — otomatis klaim hasil setelah market selesai
- **Martingale Recovery** — taruhan naik otomatis untuk recover kerugian
- **Auto-stop** — bot berhenti sendiri kalau losestreak mencapai batas
- **Dashboard Web** — pantau PNL, winrate, dan status bot secara real-time
- **Daily Summary** — laporan otomatis tiap jam 00:00 via Telegram
- **Crash Detection** — notifikasi Telegram kalau bot crash/mati mendadak
- **State Persistence** — posisi tersimpan, aman kalau bot restart

---

## Command Telegram

| Command | Fungsi |
|---------|--------|
| `/start` | Nyalain real bot (input base amount & max streak) |
| `/stop` | Matiin real bot |
| `/status` | Cek status bot saat ini |
| `/pnl` | Lihat PNL hari ini dan total |
| `/balance` | Cek saldo wallet |
| `/resetreal` | Reset semua data real trading |

---

## Cara Setup

### 1. Clone Repository

```bash
git clone https://github.com/USERNAME/polymarket-bot.git
cd polymarket-bot
```

### 2. Buat Virtual Environment & Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Buat File `.env`

Buat file `.env` di folder project:

```bash
nano .env
```

Isi dengan data berikut:

```
PRIVATE_KEY=your_wallet_private_key
FUNDER_ADDRESS=your_wallet_address
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
```

> **Cara dapat Telegram Token:** Buka [@BotFather](https://t.me/BotFather) di Telegram → `/newbot` → ikuti instruksi → copy token-nya.
>
> **Cara dapat Chat ID:** Buka [@userinfobot](https://t.me/userinfobot) di Telegram → `/start` → ambil angka ID-nya.

### 4. Sesuaikan Konfigurasi (Opsional)

Edit `config_real.py` untuk mengubah parameter strategi:

```python
W1_MIN = 53   # Harga minimum entry (cents)
W1_MAX = 58   # Harga maksimum entry (cents)
```

### 5. Jalankan Bot

```bash
# Jalankan Telegram Bot (controller utama)
source venv/bin/activate
python telegram_bot.py
```

Setelah itu kontrol bot dari Telegram dengan command `/start`.

### 6. Jalankan Dashboard (Opsional)

```bash
source venv/bin/activate
python dashboard.py
```

Buka browser: `http://IP_VPS:5000`

---

## Menjalankan sebagai Service (Agar Jalan Terus di Background)

Copy file service yang sudah tersedia:

```bash
cp polymarket-telegram.service /etc/systemd/system/
systemctl enable polymarket-telegram
systemctl start polymarket-telegram
```

Cek status:

```bash
systemctl status polymarket-telegram
```

---

## Catatan Penting

- File `.env` berisi private key wallet — **jangan pernah share atau upload ke GitHub**
- Martingale bisa memperbesar kerugian kalau streak kalah panjang — set `max streak` sesuai kemampuan modal
- Bot paper dan real berjalan terpisah — paper tidak bisa dikontrol via Telegram
