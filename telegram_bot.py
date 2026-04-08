"""
============================================================
POLYMARKET - Telegram Bot Controller
============================================================
Control real bot via Telegram.
Paper bot jalan terus, tidak bisa dikontrol via Telegram.
============================================================
"""

import os
import json
import subprocess
import signal
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

load_dotenv()

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

logger.add(
    "telegram_bot.log",
    rotation="10 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Conversation states
ASK_BASE, ASK_STREAK = range(2)
CONFIRM_RESET = 2

# Real bot process
real_bot_process = None
real_base_amount = None
real_max_streak  = None

DATA_REAL_FILE  = "data_real.json"
DATA_PAPER_FILE = "data_paper.json"
STATE_REAL_FILE = "state_real.json"
STOPPED_FILE    = "real_bot_stopped.json"

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def is_authorized(update: Update) -> bool:
    return update.effective_chat.id == TELEGRAM_CHAT_ID

def read_json(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except:
        return {}

def is_real_bot_running():
    global real_bot_process
    if real_bot_process is None:
        return False
    return real_bot_process.poll() is None

async def send_msg(context: ContextTypes.DEFAULT_TYPE, text: str):
    await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")

# ─────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    if is_real_bot_running():
        await update.message.reply_text("⚠️ Real bot sudah jalan. Ketik /stop dulu.")
        return

    await update.message.reply_text("💵 Masukkan base amount ($):")
    return ASK_BASE

async def ask_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END

    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
        context.user_data['base_amount'] = amount
        await update.message.reply_text(f"✅ Base: ${amount}\n\n🔢 Masukkan max losestreak:")
        return ASK_STREAK
    except:
        await update.message.reply_text("❌ Input tidak valid. Masukkan angka, contoh: 3")
        return ASK_BASE

async def ask_streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global real_bot_process, real_base_amount, real_max_streak

    if not is_authorized(update):
        return ConversationHandler.END

    try:
        streak = int(update.message.text.strip())
        if streak <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ Input tidak valid. Masukkan angka bulat, contoh: 6")
        return ASK_STREAK

    real_base_amount = context.user_data['base_amount']
    real_max_streak  = streak

    env = os.environ.copy()
    env['REAL_BASE_AMOUNT']    = str(real_base_amount)
    env['REAL_MAX_LOSESTREAK'] = str(real_max_streak)

    # Hapus stopped file kalau ada
    if os.path.exists(STOPPED_FILE):
        os.remove(STOPPED_FILE)

    real_bot_process = subprocess.Popen(
        ["venv/bin/python", "bot_real.py"],
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    logger.info(f"✅ Real bot started. Base=${real_base_amount} | MaxStreak={real_max_streak}")
    await update.message.reply_text(
        f"✅ <b>Real bot started</b>\n"
        f"Base: <b>${real_base_amount}</b>\n"
        f"Max streak: <b>{real_max_streak}x</b>\n"
        f"Martingale: aktif",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global real_bot_process

    if not is_authorized(update):
        return

    if not is_real_bot_running():
        await update.message.reply_text("ℹ️ Real bot tidak sedang jalan.")
        return

    real_bot_process.send_signal(signal.SIGINT)
    real_bot_process.wait(timeout=10)
    logger.info("🔴 Real bot dihentikan via Telegram")
    await update.message.reply_text("🔴 Real bot dihentikan.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    running = is_real_bot_running()
    d       = read_json(DATA_REAL_FILE)
    live    = d.get('live', {})

    status_icon = "🟢" if running else "🔴"
    status_text = "RUNNING" if running else "STOPPED"

    msg = (
        f"{status_icon} <b>Real Bot: {status_text}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
    )

    if running and d:
        msg += (
            f"Market   : #{live.get('market_num', '-')}\n"
            f"Status   : {live.get('status', '-')}\n"
            f"Streak   : {live.get('current_streak', 0)}x / {d.get('max_streak', '-')}x\n"
            f"Balance  : ${live.get('balance', '-')}\n"
            f"Total PNL: ${d.get('total_pnl', 0):.2f}\n"
        )

    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    d = read_json(DATA_REAL_FILE)
    if not d:
        await update.message.reply_text("📊 Belum ada data real trading.")
        return

    today     = datetime.now().strftime('%Y-%m-%d')
    daily     = d.get('daily', [])
    today_row = next((r for r in daily if r['date'] == today), None)

    msg = (
        f"📊 <b>PNL Real Trading</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Total</b>\n"
        f"  Entry  : {d.get('total_entry', 0)}x\n"
        f"  Win    : {d.get('total_win', 0)}x\n"
        f"  Lose   : {d.get('total_lose', 0)}x\n"
        f"  WR     : {d.get('winrate', 0)}%\n"
        f"  PNL    : ${d.get('total_pnl', 0):.2f}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<b>Hari Ini ({today})</b>\n"
    )

    if today_row:
        pnl_sign = "+" if today_row['pnl'] >= 0 else ""
        msg += (
            f"  Entry  : {today_row['entry']}x\n"
            f"  Win    : {today_row['win']}x\n"
            f"  Lose   : {today_row['lose']}x\n"
            f"  WR     : {today_row['winrate']}%\n"
            f"  PNL    : {pnl_sign}${today_row['pnl']:.2f}\n"
        )
    else:
        msg += "  Belum ada trade hari ini.\n"

    await update.message.reply_text(msg, parse_mode="HTML")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return

    d    = read_json(DATA_REAL_FILE)
    live = d.get('live', {})
    bal  = live.get('balance')

    if bal is not None:
        await update.message.reply_text(f"💰 Balance: <b>${bal:.2f} USDC</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ Balance tidak tersedia. Pastikan real bot jalan.")

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

async def cmd_resetreal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END

    if is_real_bot_running():
        await update.message.reply_text("⚠️ Real bot masih jalan. Ketik /stop dulu sebelum reset.")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚠️ <b>RESET DATA REAL</b>\n"
        "Semua history trade, PNL, dan statistik akan dihapus permanen.\n\n"
        "Ketik <b>RESET</b> untuk konfirmasi, atau /cancel untuk batal.",
        parse_mode="HTML"
    )
    return CONFIRM_RESET

async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END

    if update.message.text.strip() != "RESET":
        await update.message.reply_text("❌ Konfirmasi tidak valid. Reset dibatalkan.")
        return ConversationHandler.END

    with open(DATA_REAL_FILE, 'w') as f:
        json.dump({}, f)

    with open(STATE_REAL_FILE, 'w') as f:
        json.dump({}, f)

    if os.path.exists(STOPPED_FILE):
        os.remove(STOPPED_FILE)

    logger.info("🗑️ Data real direset via Telegram")
    await update.message.reply_text(
        "✅ <b>Data real berhasil direset.</b>\n"
        "Semua history trade dan PNL sudah dihapus.\n"
        "Ketik /start untuk mulai trading baru.",
        parse_mode="HTML"
    )
    return ConversationHandler.END

# ─────────────────────────────────────────
# MONITOR TASK (crash detection, daily summary, server restart)
# ─────────────────────────────────────────

async def monitor_loop(app):
    global real_bot_process

    # Cek apakah real bot lagi jalan sebelum restart
    state = read_json(STATE_REAL_FILE)
    if state and not is_real_bot_running():
        try:
            await app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=(
                    "⚠️ <b>SERVER RESTART DETECTED</b>\n"
                    "Real bot was running sebelum restart.\n"
                    "Ketik /start untuk nyalain lagi."
                ),
                parse_mode="HTML"
            )
        except:
            pass

    last_daily_notif = None

    while True:
        await asyncio.sleep(10)

        try:
            # ── CEK CRASH ─────────────────────────────────────
            if real_bot_process is not None and real_bot_process.poll() is not None:
                exit_code = real_bot_process.returncode

                # Exit code 2 = max losestreak
                if exit_code == 2 and os.path.exists(STOPPED_FILE):
                    stopped = read_json(STOPPED_FILE)
                    bal     = stopped.get('balance', '-')
                    pnl     = stopped.get('total_pnl', 0)
                    streak  = stopped.get('streak', '-')
                    pnl_sign = "+" if pnl >= 0 else ""

                    await app.bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=(
                            f"🚨 <b>REAL BOT STOPPED</b>\n"
                            f"Losestreak <b>{streak}x</b> tercapai.\n"
                            f"Total PNL : {pnl_sign}${pnl:.2f}\n"
                            f"Balance   : ${bal}\n\n"
                            f"Ketik /start untuk restart."
                        ),
                        parse_mode="HTML"
                    )
                elif exit_code not in (0, 2):
                    await app.bot.send_message(
                        chat_id=TELEGRAM_CHAT_ID,
                        text=(
                            f"💥 <b>REAL BOT CRASH</b>\n"
                            f"Exit code: {exit_code}\n"
                            f"Cek real_trading.log untuk detail.\n\n"
                            f"Ketik /start untuk restart."
                        ),
                        parse_mode="HTML"
                    )

                real_bot_process = None

            # ── DAILY SUMMARY jam 00:00 ────────────────────────
            now   = datetime.now()
            today = now.strftime('%Y-%m-%d')

            if now.hour == 0 and now.minute == 0 and last_daily_notif != today:
                last_daily_notif = today
                yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')

                d_real  = read_json(DATA_REAL_FILE)
                d_paper = read_json(DATA_PAPER_FILE)

                def get_day_row(data, date):
                    return next((r for r in data.get('daily', []) if r['date'] == date), None)

                r = get_day_row(d_real, yesterday)
                p = get_day_row(d_paper, yesterday)

                msg = f"📊 <b>Daily Summary - {yesterday}</b>\n━━━━━━━━━━━━━━━━\n"

                if r:
                    pnl_sign = "+" if r['pnl'] >= 0 else ""
                    msg += (
                        f"<b>REAL</b>\n"
                        f"  Entry: {r['entry']}x | W: {r['win']} L: {r['lose']} | WR: {r['winrate']}%\n"
                        f"  PNL: {pnl_sign}${r['pnl']:.2f}\n"
                    )
                else:
                    msg += "<b>REAL</b>\n  Tidak ada trade\n"

                if p:
                    msg += (
                        f"<b>PAPER</b>\n"
                        f"  Entry: {p['entry']}x | W: {p['win']} L: {p['lose']} | WR: {p['winrate']}%\n"
                    )
                else:
                    msg += "<b>PAPER</b>\n  Tidak ada data\n"

                await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"❌ monitor_loop error: {e}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN tidak ditemukan di .env")
        return
    if not TELEGRAM_CHAT_ID:
        logger.error("❌ TELEGRAM_CHAT_ID tidak ditemukan di .env")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Conversation handler untuk /start
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            ASK_BASE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_base)],
            ASK_STREAK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_streak)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    reset_conv = ConversationHandler(
        entry_points=[CommandHandler("resetreal", cmd_resetreal)],
        states={
            CONFIRM_RESET: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_reset)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(conv)
    app.add_handler(reset_conv)
    app.add_handler(CommandHandler("stop",      cmd_stop))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("pnl",       cmd_pnl))
    app.add_handler(CommandHandler("balance",   cmd_balance))

    # Jalanin monitor loop sebagai background task
    async def post_init(application):
        asyncio.create_task(monitor_loop(application))

    app.post_init = post_init

    logger.info("✅ Telegram bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
