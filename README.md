# Polymarket Trading Bot

Bot trading otomatis untuk Polymarket menggunakan strategi entry Window 1 (W1) dengan pilihan mode Martingale atau Flat.

> **Disclaimer:** Ini bukan bot AI/pintar. Bot ini hanya mengeksekusi strategi yang sudah ditentukan sendiri — entry di window waktu tertentu, range harga tertentu, dengan manajemen taruhan manual (Flat atau Martingale). Semua keputusan strategi ada di tangan pemilik bot. Bot hanya mengotomasi eksekusinya.

---

## Support / Referral

Kalau repo ini berguna buat lo, boleh pakai referral Polymarket gue atau kirim tip ke address EVM gue. Siapa tau ada rejeki nomplok wkwk.

- **Daftar Polymarket via referral gue:** [polymarket.com/?r=Elevenoned](https://polymarket.com/?r=Elevenoned)
- **EVM Address (tip jar):** `0xc2b1945fb01112d6ced2c1f873c9ef7453e1491b`

---

## Cara Kerja Bot

Bot real **tidak entry sendiri** — ia mengikuti sinyal dari bot paper. Bot paper harus jalan lebih dulu.

### Alur Sinyal

1. **Bot paper** memantau market dan entry saat harga masuk range W1
2. **Bot real** baca `state_paper.json` — kalau paper sudah entry di slot market yang sama, bot real ikut entry
3. Bot real ikut sisi (YES/NO) yang sama dengan paper, asalkan harga di sisi itu masih dalam range `W1_MIN–W1_MAX`
4. Order dieksekusi sebagai market order (langsung tereksekusi)
5. Setelah market resolve, bot catat WIN/LOSE dan otomatis redeem posisi menang

### Kondisi Entry Real Bot

- **Syarat utama:** Paper bot sudah entry di slot market yang sama
- **Range harga:** Dipilih saat `/start` — `≤58¢` atau `≤47¢`
- **Mode taruhan:** Dipilih saat `/start` — Martingale Recovery atau Flat
- **Order type:** Market order

### Alur Singkat

```
Paper bot nyala → Entry saat harga masuk range
       ↓
Real bot nyala → Deteksi paper sudah entry → Cek harga saat ini
→ Harga masuk range → Entry → Tunggu resolve → Catat hasil
→ Kalau kalah (Martingale) → Naikkan taruhan untuk recover → Ulangi
→ Kalau streak kalah > batas → Bot berhenti otomatis
```

> **Penting:** Jalankan `bot_paper.py` (atau via service) **sebelum** menjalankan real bot. Jalankan paper dulu minimal beberapa hari untuk ngebaca **pola** (winrate per jam, streak kalah, range yang lagi jalan) dan **momentum waktu** (jam-jam volatile vs kalem) — dari situ lo bisa tentuin kapan real bot sebaiknya nyala, pilih range mana, dan seberapa agresif base amount / martingale. Tanpa paper bot aktif, real bot juga tidak akan pernah entry karena sinyal entry real diambil dari paper.

---

## Komponen Bot

| File | Fungsi |
|------|--------|
| `bot_real.py` | Bot utama, eksekusi trading real |
| `bot_paper.py` | Bot simulasi (paper trading), tidak pakai uang asli |
| `telegram_bot.py` | Controller bot via Telegram |
| `dashboard.py` | Dashboard web untuk monitoring |
| `config_real.py` | Konfigurasi default strategi (timing, range harga) |

---

## Fitur

- **Real Trading** — eksekusi order langsung ke Polymarket
- **Paper Trading** — simulasi tanpa modal, berjalan paralel untuk perbandingan
- **Telegram Controller** — kontrol bot dari HP via Telegram
- **Auto-redeem** — otomatis klaim hasil setelah market selesai
- **Martingale Recovery** — taruhan naik otomatis untuk recover kerugian, dengan threshold aktivasi
- **Flat Mode** — taruhan tetap BASE_AMOUNT setiap entry, tanpa martingale
- **Price Range Selection** — pilih range entry `≤58¢` atau `≤47¢` saat `/start`
- **Martingale Start** — delay sebelum martingale aktif (misal: aktif baru di losestreak ke-4)
- **Auto-stop** — bot berhenti sendiri kalau losestreak mencapai batas
- **Dashboard Web** — pantau winrate, mode, dan status bot secara real-time
- **Daily Summary** — laporan otomatis tiap jam 00:00 via Telegram
- **Crash Detection** — notifikasi Telegram kalau bot crash/mati mendadak
- **State Persistence** — posisi tersimpan, aman kalau bot restart

---

## Command Telegram

| Command | Fungsi |
|---------|--------|
| `/start` | Nyalain real bot (setup base, range, mode, max streak) |
| `/stop` | Matiin real bot |
| `/status` | Cek status bot saat ini |
| `/pnl` | Lihat PNL hari ini dan total |
| `/balance` | Cek saldo wallet |
| `/resetreal` | Reset semua data real trading |

### Flow `/start`

```
/start
→ "Masukkan base amount ($):"          → contoh: 3
→ "Pilih price range:" [≤58¢][≤47¢]
→ "Pilih mode:" [Martingale Recovery][Flat]
→ (kalau Martingale) "Aktif setelah streak ke berapa?" → contoh: 4
→ "Masukkan max losestreak:"           → contoh: 6
→ ✅ Real bot started
```

---

## Mode Betting

### Martingale Recovery
Taruhan berikutnya dihitung untuk menutup total kerugian yang sudah terakumulasi.

- Formula: `next_bet = cumulative_loss × (price / (1 - price))`
- Parameter `martingale_start`: berapa losestreak sebelum martingale aktif. Loss sebelum threshold dianggap hangus (tidak direcovery).
- Contoh exposure base $3 max 6x: `martingale_start=1` → maks $162, `martingale_start=4` → maks $23.82

### Flat
Setiap entry selalu menggunakan BASE_AMOUNT, tidak peduli losestreak.

---

## Cara Setup

### 1. Clone Repository

```bash
git clone https://github.com/Elevenoned214/polymarket-bot.git
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

### 4. Jalankan Bot

```bash
# Jalankan Telegram Bot (controller utama)
source venv/bin/activate
python telegram_bot.py
```

Setelah itu kontrol bot dari Telegram dengan command `/start`.

### 5. Jalankan Dashboard (Opsional)

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
- Martingale bisa memperbesar kerugian kalau streak kalah panjang — set `max streak` dan `martingale_start` sesuai kemampuan modal
- Bot paper **harus jalan lebih dulu** sebelum real bot — real bot pakai sinyal paper sebagai trigger entry
- Bot paper tidak bisa dikontrol via Telegram, jalankan manual atau via service
- Range harga dan mode betting dipilih setiap kali `/start`, tidak perlu ubah config file
