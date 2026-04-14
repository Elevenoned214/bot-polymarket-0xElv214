"""
============================================================
POLYMARKET BOT - Paper Trading (Pattern Finder)
============================================================
Entry W1 saja, detik 30-80, harga 53-58¢
Hasil: WIN / LOSE
Dashboard: baca data.json via AJAX
============================================================
"""

import os
import json
import time
import requests
import signal
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger
from py_clob_client.client import ClobClient
import config_paper as config

logger.add(
    "paper_trading.log",
    rotation="50 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

load_dotenv()
PRIVATE_KEY    = os.getenv("PRIVATE_KEY")
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS")

# Global tracking
market_count      = 0
events            = []
start_time_global = None
total_pnl         = 0.0

STATE_FILE = 'state_paper.json'

def load_state():
    global market_count, total_pnl, start_time_global, events
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
        start_time_global = datetime.fromisoformat(state['start_time'])
        market_count      = state.get('market_count', 0)
        total_pnl         = state.get('total_pnl', 0.0)
        events = []
        for e in state.get('events', []):
            ev = dict(e)
            ev['time'] = datetime.fromisoformat(e['time'])
            events.append(ev)
        logger.info(f"📂 State loaded: {len(events)} events, market #{market_count}, PnL={total_pnl:.2f}")
    except Exception as ex:
        logger.warning(f"⚠️ Gagal load state: {ex}, mulai fresh.")

def save_state():
    state = {
        'start_time':   start_time_global.isoformat() if start_time_global else datetime.now().isoformat(),
        'market_count': market_count,
        'total_pnl':    total_pnl,
        'events': [
            {**{k: v for k, v in e.items() if k != 'time'}, 'time': e['time'].isoformat()}
            for e in events
        ],
    }
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)

# Live state untuk dashboard
live_state = {
    "yes_price":      None,
    "no_price":       None,
    "market_elapsed": 0,
    "market_num":     0,
    "status":         "Menunggu market...",
    "pos_side":       None,
    "pos_price":      None,
}

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def get_time_slot(dt):
    return (dt.hour // 4) * 4

def max_lose_streak(event_list):
    """Hitung max lose beruntun dari list events."""
    results = [e['type'] for e in event_list if e['type'] in ('win', 'lose')]
    max_streak = 0
    current    = 0
    for r in results:
        if r == 'lose':
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak

def save_data():
    """Tulis semua data ke data.json untuk dibaca dashboard."""
    total_entry = sum(1 for e in events if e['type'] == 'entry')
    total_win   = sum(1 for e in events if e['type'] == 'win')
    total_lose  = sum(1 for e in events if e['type'] == 'lose')
    winrate     = round(total_win / total_entry * 100, 1) if total_entry > 0 else 0

    # Breakdown per 4 jam (hari ini)
    today = datetime.now().date()
    today_events = [e for e in events if e['time'].date() == today]
    slots = {}
    for event in today_events:
        slot = get_time_slot(event['time'])
        slots.setdefault(slot, []).append(event)

    breakdown = []
    for slot in sorted(slots.keys()):
        se    = slots[slot]
        entry = sum(1 for e in se if e['type'] == 'entry')
        win   = sum(1 for e in se if e['type'] == 'win')
        lose  = sum(1 for e in se if e['type'] == 'lose')
        wr    = round(win / entry * 100, 1) if entry > 0 else 0
        breakdown.append({
            'label':      f"{slot:02d}:00 - {slot+4:02d}:00",
            'entry':      entry,
            'win':        win,
            'lose':       lose,
            'winrate':    wr,
            'max_streak': max_lose_streak(se),
        })

    # Daily results
    days = {}
    for event in events:
        day = event['time'].strftime('%Y-%m-%d')
        days.setdefault(day, []).append(event)

    daily = []
    for day in sorted(days.keys(), reverse=True):
        de    = days[day]
        entry = sum(1 for e in de if e['type'] == 'entry')
        win   = sum(1 for e in de if e['type'] == 'win')
        lose  = sum(1 for e in de if e['type'] == 'lose')
        wr    = round(win / entry * 100, 1) if entry > 0 else 0
        daily.append({
            'date':       day,
            'entry':      entry,
            'win':        win,
            'lose':       lose,
            'winrate':    wr,
            'max_streak': max_lose_streak(de),
        })

    # Trade history 10 terakhir
    entry_events  = [e for e in events if e['type'] == 'entry']
    result_events = [e for e in events if e['type'] in ('win', 'lose')]
    trades = []
    for i, entry_e in enumerate(entry_events):
        result = result_events[i] if i < len(result_events) else None
        trades.append({
            'time':   entry_e['time'].strftime('%H:%M:%S'),
            'side':   entry_e.get('side', '-'),
            'price':  entry_e.get('price', 0),
            'result': result['type'].upper() if result else 'PENDING',
        })
    trades = list(reversed(trades))[:10]

    elapsed = datetime.now() - start_time_global if start_time_global else timedelta(0)
    h, rem  = divmod(int(elapsed.total_seconds()), 3600)
    m       = rem // 60

    # PnL history untuk chart
    result_events_sorted = sorted([e for e in events if e['type'] in ('win', 'lose')], key=lambda x: x['time'])
    pnl_history = []
    cum = 0
    for e in result_events_sorted:
        cum += e.get('pnl') or 0
        pnl_history.append({'t': e['time'].strftime('%m/%d %H:%M'), 'v': round(cum, 2)})
    pnl_history = pnl_history[-100:]

    data = {
        'start_time':   start_time_global.strftime('%Y-%m-%d %H:%M:%S') if start_time_global else '-',
        'running':      f"{h}j {m}m",
        'market_count': market_count,
        'total_entry':  total_entry,
        'total_win':    total_win,
        'total_lose':   total_lose,
        'winrate':      winrate,
        'total_pnl':    round(total_pnl, 2),
        'breakdown':    breakdown,
        'daily':        daily,
        'trades':       trades,
        'live':         live_state,
        'pnl_history':  pnl_history,
    }

    tmp = 'data_paper.json.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, 'data_paper.json')

# ─────────────────────────────────────────
# STATS TERMINAL
# ─────────────────────────────────────────

def get_current_slot_stats():
    now          = datetime.now()
    current_slot = get_time_slot(now)
    slot_events  = [e for e in events if get_time_slot(e['time']) == current_slot]
    return {
        'slot_start': current_slot,
        'slot_end':   current_slot + 4,
        'entry': sum(1 for e in slot_events if e['type'] == 'entry'),
        'win':   sum(1 for e in slot_events if e['type'] == 'win'),
        'lose':  sum(1 for e in slot_events if e['type'] == 'lose'),
    }

def show_live_stats():
    s = get_current_slot_stats()
    logger.info(
        f"\n📊 JAM {s['slot_start']:02d}:00-{s['slot_end']:02d}:00 (LIVE): "
        f"Entry: {s['entry']}x | WIN: {s['win']}x | LOSE: {s['lose']}x"
    )

def show_results():
    total_entry = sum(1 for e in events if e['type'] == 'entry')
    total_win   = sum(1 for e in events if e['type'] == 'win')
    total_lose  = sum(1 for e in events if e['type'] == 'lose')
    winrate     = round(total_win / total_entry * 100, 1) if total_entry > 0 else 0
    logger.info("\n" + "=" * 70)
    logger.info("📊 HASIL PAPER TRADING")
    logger.info("=" * 70)
    logger.info(f"Total market  : {market_count}")
    logger.info(f"Total entry   : {total_entry}x | Shares: {config.SHARES}")
    logger.info(f"WIN           : {total_win}x")
    logger.info(f"LOSE          : {total_lose}x")
    logger.info(f"Win rate      : {winrate:.1f}%")
    logger.info("=" * 70)
    slots = {}
    for event in events:
        slot = get_time_slot(event['time'])
        slots.setdefault(slot, []).append(event)
    logger.info("\n📊 BREAKDOWN PER 4 JAM\n")
    for slot in sorted(slots.keys()):
        se    = slots[slot]
        entry = sum(1 for e in se if e['type'] == 'entry')
        win   = sum(1 for e in se if e['type'] == 'win')
        lose  = sum(1 for e in se if e['type'] == 'lose')
        logger.info(f"Jam {slot:02d}:00-{slot+4:02d}:00: Entry {entry}/48 | WIN {win}x | LOSE {lose}x")
    logger.info("\n✅ Selesai!")

def signal_handler(sig, frame):
    logger.info("\n🔴 Bot dihentikan manual (Ctrl+C)")
    show_results()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ─────────────────────────────────────────
# API FUNCTIONS
# ─────────────────────────────────────────

def get_current_token_id():
    try:
        now  = int(time.time())
        slot = (now // 300) * 300
        url  = f"https://gamma-api.polymarket.com/markets?slug=btc-updown-5m-{slot}"
        res  = requests.get(url, timeout=5).json()
        if res and len(res) > 0:
            token_ids = json.loads(res[0].get("clobTokenIds", "[]"))
            if len(token_ids) >= 2:
                return token_ids[0], token_ids[1], slot
        return None, None, None
    except:
        return None, None, None

def get_market_result(slot):
    try:
        url = f"https://gamma-api.polymarket.com/markets?slug=btc-updown-5m-{slot}"
        res = requests.get(url, timeout=5).json()
        if not res:
            return None
        market = res[0]
        if not market.get("closed") and market.get("umaResolutionStatus") != "resolved":
            return None
        outcomes       = json.loads(market.get("outcomes", "[]"))
        outcome_prices = json.loads(market.get("outcomePrices", "[]"))
        for i, price in enumerate(outcome_prices):
            if float(price) >= 0.99:
                return "YES" if outcomes[i] == "Up" else "NO"
        return None
    except Exception as e:
        logger.warning(f"⚠️ get_market_result error: {e}")
        return None

def get_market_price(client, yes_token, no_token):
    try:
        yes_mid = client.get_midpoint(yes_token)
        if isinstance(yes_mid, dict):
            yes_price = float(yes_mid.get("mid", 0)) * 100
        else:
            yes_price = float(yes_mid) * 100
        no_price = 100 - yes_price
        return round(yes_price, 2), round(no_price, 2)
    except:
        return None, None

def setup_client():
    try:
        client = ClobClient(
            config.HOST,
            key=PRIVATE_KEY,
            chain_id=config.CHAIN_ID,
            signature_type=2,
            funder=FUNDER_ADDRESS
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        logger.info("✅ Koneksi berhasil!")
        return client
    except Exception as e:
        logger.error(f"❌ Gagal koneksi: {e}")
        exit(1)

def record_result(winner, pending_side, pending_price):
    global total_pnl
    p = pending_price / 100
    if winner == pending_side:
        pnl = round(config.SHARES * (1 - p) / p, 4)
        total_pnl += pnl
        events.append({'time': datetime.now(), 'type': 'win', 'shares': config.SHARES, 'pnl': pnl})
        logger.info(f"   🎉 WIN | {pending_side} {pending_price:.1f}¢ | +${pnl:.2f}")
    else:
        pnl = round(-config.SHARES, 4)
        total_pnl += pnl
        events.append({'time': datetime.now(), 'type': 'lose', 'shares': config.SHARES, 'pnl': pnl})
        logger.info(f"   😢 LOSE | {pending_side} {pending_price:.1f}¢ | -${config.SHARES:.2f}")
    save_state()
    save_data()

# ─────────────────────────────────────────
# MAIN BOT LOOP
# ─────────────────────────────────────────

def main():
    global market_count, start_time_global

    load_state()
    if start_time_global is None:
        start_time_global = datetime.now()

    logger.info("=" * 70)
    logger.info("📊 PAPER TRADING - Pattern Finder")
    logger.info("=" * 70)
    logger.info(f"   Start : {start_time_global.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   Shares: {config.SHARES} (tetap)")
    logger.info(f"   Entry : W1 detik {config.W1_START}-{config.W1_END}, harga {config.W1_MIN}-{config.W1_MAX}¢")
    logger.info(f"   Dashboard: jalankan python3 dashboard.py di terminal lain")
    logger.info("=" * 70)

    client       = setup_client()
    yes_token    = None
    no_token     = None
    current_slot = None
    market_start = None
    pos1_side    = None
    pos1_price   = None
    entered      = False

    pending_slot       = None
    pending_side       = None
    pending_price      = None
    pending_market_num = None

    save_data()

    while True:
        try:
            now  = int(time.time())
            slot = (now // 300) * 300

            # ── MARKET BARU ──────────────────────────────────────
            if slot != current_slot:
                market_count += 1

                if pending_slot and pending_side:
                    logger.info(f"\n🔍 CEK HASIL MARKET #{pending_market_num}")
                    live_state['status'] = f"Menunggu hasil market #{pending_market_num}..."
                    save_data()

                    by, bn = get_market_price(client, yes_token, no_token)
                    backup_winner = None
                    if by is not None and bn is not None and by != bn:
                        backup_winner = "YES" if by > bn else "NO"
                    logger.info(f"   💾 Backup detik 300: {backup_winner} (YES {by}¢ | NO {bn}¢)")

                    winner = None
                    waited = 0
                    while waited < 25:
                        winner = get_market_result(pending_slot)
                        if winner:
                            logger.info(f"   ✅ Dapat hasil API: {winner}")
                            break
                        logger.info(f"   ⏳ Belum resolved, tunggu 5 detik... ({waited}s/25s)")
                        time.sleep(5)
                        waited += 5

                    if not winner:
                        if backup_winner:
                            winner = backup_winner
                            logger.info(f"   ⚠️ API timeout, pakai backup: {winner}")
                        else:
                            logger.info(f"   ❌ Hasil tidak didapat, skip")

                    if winner:
                        record_result(winner, pending_side, pending_price)
                        pending_slot = pending_side = pending_price = pending_market_num = None
                    else:
                        logger.info(f"   ⏳ Pending dibawa ke market berikutnya...")

                yes_token, no_token, current_slot = get_current_token_id()

                if yes_token:
                    logger.info(f"\n{'='*70}")
                    logger.info(f"🔄 MARKET #{market_count}")
                    show_live_stats()
                    logger.info(f"{'='*70}")

                    market_start = slot
                    pos1_side    = None
                    pos1_price   = None
                    entered      = False

                    live_state['market_num'] = market_count
                    live_state['pos_side']   = None
                    live_state['pos_price']  = None
                    live_state['status']     = f"Menunggu W1 (detik {config.W1_START}-{config.W1_END})"
                    save_data()

            if not yes_token or market_start is None:
                time.sleep(config.LOOP_INTERVAL)
                continue

            market_elapsed = now - market_start
            yes_price, no_price = get_market_price(client, yes_token, no_token)

            if yes_price is None:
                time.sleep(config.LOOP_INTERVAL)
                continue

            # Update live state
            live_state['yes_price']      = yes_price
            live_state['no_price']       = no_price
            live_state['market_elapsed'] = market_elapsed

            # ── TANDAI PENDING detik 295 ──────────────────────
            if market_elapsed >= 295 and pos1_side and not pending_slot:
                pending_slot       = current_slot
                pending_side       = pos1_side
                pending_price      = pos1_price
                pending_market_num = market_count
                live_state['status'] = "🔍 Menunggu hasil..."
                logger.info(f"   📌 Posisi #{market_count} ditandai pending")

            # ── LOG TIAP 30 DETIK ──────────────────────────────
            if market_elapsed % 30 == 0:
                logger.info(f"⏱ Detik {market_elapsed} | YES: {yes_price:.1f}¢ NO: {no_price:.1f}¢")

            # ── PUNYA POSISI ───────────────────────────────────
            if pos1_side:
                live_state['status']    = f"{'🟢' if pos1_side == 'YES' else '🔵'} ENTRY {pos1_side} @ {pos1_price:.1f}¢"
                live_state['pos_side']  = pos1_side
                live_state['pos_price'] = pos1_price

            # ── CEK W1 ─────────────────────────────────────────
            elif not entered and config.W1_START <= market_elapsed <= config.W1_END:
                entry_side  = None
                entry_price = None

                if config.W1_MIN <= yes_price <= config.W1_MAX:
                    entry_side, entry_price = "YES", yes_price
                elif config.W1_MIN <= no_price <= config.W1_MAX:
                    entry_side, entry_price = "NO", no_price

                if entry_price:
                    pos1_side  = entry_side
                    pos1_price = entry_price
                    entered    = True

                    events.append({
                        'time':   datetime.now(),
                        'type':   'entry',
                        'side':   entry_side,
                        'price':  entry_price,
                        'shares': config.SHARES
                    })

                    live_state['status']    = f"{'🟢' if entry_side == 'YES' else '🔵'} ENTRY {entry_side} @ {entry_price:.1f}¢ (detik {market_elapsed})"
                    live_state['pos_side']  = entry_side
                    live_state['pos_price'] = entry_price

                    logger.info(f"   🟢 [W1] ENTRY {entry_side} @ {entry_price:.1f}¢ | Shares: {config.SHARES}")
                    save_state()
                    save_data()

            save_data()
            time.sleep(config.LOOP_INTERVAL)

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            time.sleep(5)

    show_results()

if __name__ == "__main__":
    main()
