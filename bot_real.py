"""
============================================================
POLYMARKET BOT - Real Trading
============================================================
Entry W1 saja, detik 30-80, harga 53-58¢
Martingale cumulative recovery
Market order (bukan limit)
Auto-redeem setelah resolve
============================================================
"""

import os
import json
import time
import threading
import requests
import signal
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from web3 import Web3
import config_real as config

# ── CTF REDEEM CONFIG ─────────────────────────────────
POLYGON_RPC  = "https://polygon.publicnode.com"
CTF_ADDRESS  = Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045")
COLLATERAL   = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
CTF_ABI = [{
    "inputs": [
        {"name": "collateralToken",      "type": "address"},
        {"name": "parentCollectionId",   "type": "bytes32"},
        {"name": "conditionId",          "type": "bytes32"},
        {"name": "indexSets",            "type": "uint256[]"}
    ],
    "name": "redeemPositions",
    "outputs": [],
    "stateMutability": "nonpayable",
    "type": "function"
}]

logger.add(
    "real_trading.log",
    rotation="50 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

load_dotenv()
PRIVATE_KEY    = os.getenv("PRIVATE_KEY")
FUNDER_ADDRESS = os.getenv("FUNDER_ADDRESS")

# Diset dari telegram_bot.py sebelum start
BASE_AMOUNT      = float(os.getenv("REAL_BASE_AMOUNT", "1"))
MAX_LOSESTREAK   = int(os.getenv("REAL_MAX_LOSESTREAK", "6"))
BETTING_MODE     = os.getenv("REAL_BETTING_MODE", "martingale").lower()  # flat | martingale | martingale_2x
MARTINGALE_START = int(os.getenv("REAL_MARTINGALE_START", "1"))
W1_MIN           = int(os.getenv("REAL_W1_MIN", str(config.W1_MIN)))
W1_MAX           = int(os.getenv("REAL_W1_MAX", str(config.W1_MAX)))

# Global tracking
market_count      = 0
events            = []
start_time_global = None
cumulative_loss   = 0.0
current_streak    = 0
total_pnl         = 0.0
current_bet       = BASE_AMOUNT  # untuk martingale_2x

# Global pending state (supaya signal_handler bisa akses)
g_pending_slot           = None
g_pending_side           = None
g_pending_price          = None
g_pending_amount         = None
g_pending_market_num     = None
g_pending_balance_before = None

# Global pos1 state (entry aktif yang belum pending, supaya signal_handler bisa akses)
g_pos1_slot           = None
g_pos1_side           = None
g_pos1_price          = None
g_pos1_amount         = None
g_pos1_taking_amount  = None
g_pos1_balance_before = None

# Live state untuk dashboard
live_state = {
    "yes_price":      None,
    "no_price":       None,
    "market_elapsed": 0,
    "market_num":     0,
    "status":         "Menunggu market...",
    "pos_side":       None,
    "pos_price":      None,
    "pos_amount":     None,
    "balance":        None,
    "current_streak": 0,
    "next_bet":       BASE_AMOUNT,
    "running":        True,
}

# ─────────────────────────────────────────
# STATE PERSISTENCE
# ─────────────────────────────────────────

def load_state():
    global market_count, events, start_time_global, cumulative_loss, current_streak, total_pnl, current_bet
    try:
        with open(config.STATE_FILE, 'r') as f:
            state = json.load(f)
        market_count      = state.get("market_count", 0)
        # cumulative_loss & current_streak sengaja TIDAK di-restore
        # supaya setiap restart selalu mulai dari base amount
        cumulative_loss   = 0.0
        current_streak    = 0
        current_bet       = BASE_AMOUNT
        total_pnl         = state.get("total_pnl", 0.0)
        start_str         = state.get("start_time")
        start_time_global = datetime.fromisoformat(start_str) if start_str else datetime.now()
        raw_events        = state.get("events", [])
        events = []
        for e in raw_events:
            e["time"] = datetime.fromisoformat(e["time"])
            events.append(e)
        logger.info(f"✅ State loaded: {len(events)} events, cumLoss=${cumulative_loss:.2f}, streak={current_streak}")
        return (
            state.get("pending_slot"), state.get("pending_side"), state.get("pending_price"),
            state.get("pending_amount"), state.get("pending_market_num"), state.get("pending_balance_before"),
            state.get("pos1_slot"), state.get("pos1_side"), state.get("pos1_price"),
            state.get("pos1_amount"), state.get("pos1_taking_amount"), state.get("pos1_balance_before"),
        )
    except FileNotFoundError:
        start_time_global = datetime.now()
        return None, None, None, None, None, None, None, None, None, None, None, None
    except Exception as e:
        logger.error(f"❌ load_state error: {e}")
        start_time_global = datetime.now()
        return None, None, None, None, None, None, None, None, None, None, None, None

def save_state(pending_slot=None, pending_side=None, pending_price=None, pending_amount=None, pending_market_num=None, pending_balance_before=None,
               pos1_slot=None, pos1_side=None, pos1_price=None, pos1_amount=None, pos1_taking_amount=None, pos1_balance_before=None):
    state = {
        "market_count":           market_count,
        "cumulative_loss":        cumulative_loss,
        "current_streak":         current_streak,
        "total_pnl":              total_pnl,
        "start_time":             start_time_global.isoformat() if start_time_global else None,
        "pending_slot":           pending_slot,
        "pending_side":           pending_side,
        "pending_price":          pending_price,
        "pending_amount":         pending_amount,
        "pending_market_num":     pending_market_num,
        "pending_balance_before": pending_balance_before,
        "pos1_slot":              pos1_slot,
        "pos1_side":              pos1_side,
        "pos1_price":             pos1_price,
        "pos1_amount":            pos1_amount,
        "pos1_taking_amount":     pos1_taking_amount,
        "pos1_balance_before":    pos1_balance_before,
        "events":                 [{**e, "time": e["time"].isoformat()} for e in events],
    }
    with open(config.STATE_FILE, 'w') as f:
        json.dump(state, f)

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def get_time_slot(dt):
    return (dt.hour // 4) * 4

def max_lose_streak(event_list):
    results = [e['type'] for e in event_list if e['type'] in ('win', 'lose')]
    max_streak, current = 0, 0
    for r in results:
        if r == 'lose':
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak

def calc_next_bet(cum_loss, price_cents):
    """Hitung bet berikutnya untuk recover cumulative loss."""
    p = price_cents / 100
    return cum_loss * p / (1 - p)

def get_bet_amount(price_cents):
    """Hitung bet berdasarkan mode dan streak saat ini."""
    if BETTING_MODE == 'flat':
        return BASE_AMOUNT
    if BETTING_MODE == 'martingale_2x':
        return round(current_bet, 2)
    # martingale recovery mode
    if current_streak < MARTINGALE_START or cumulative_loss <= 0:
        return BASE_AMOUNT
    return round(calc_next_bet(cumulative_loss, price_cents), 2)

def get_balance(client):
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        resp   = client.get_balance_allowance(params)
        if isinstance(resp, dict):
            raw = resp.get("balance", 0)
            return round(int(raw) / 1e6, 2)  # USDC.e 6 decimals
        return None
    except Exception as e:
        logger.warning(f"⚠️ get_balance error: {e}")
        return None

def save_data(balance=None):
    global live_state
    total_entry = sum(1 for e in events if e['type'] == 'entry')
    total_win   = sum(1 for e in events if e['type'] == 'win')
    total_lose  = sum(1 for e in events if e['type'] == 'lose')
    winrate     = round(total_win / total_entry * 100, 1) if total_entry > 0 else 0

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
        pnl   = sum(e.get('pnl', 0) for e in se if e['type'] in ('win', 'lose'))
        breakdown.append({
            'label':      f"{slot:02d}:00 - {slot+4:02d}:00",
            'entry':      entry,
            'win':        win,
            'lose':       lose,
            'winrate':    wr,
            'max_streak': max_lose_streak(se),
            'pnl':        round(pnl, 2),
        })

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
        pnl   = sum(e.get('pnl', 0) for e in de if e['type'] in ('win', 'lose'))
        daily.append({
            'date':       day,
            'entry':      entry,
            'win':        win,
            'lose':       lose,
            'winrate':    wr,
            'max_streak': max_lose_streak(de),
            'pnl':        round(pnl, 2),
        })

    entry_events  = [e for e in events if e['type'] == 'entry']
    result_events = [e for e in events if e['type'] in ('win', 'lose')]
    trades = []
    for i, entry_e in enumerate(entry_events):
        next_entry_time = entry_events[i + 1]['time'] if i + 1 < len(entry_events) else None
        result = next(
            (r for r in result_events
             if r['time'] >= entry_e['time'] and (next_entry_time is None or r['time'] < next_entry_time)),
            None
        )
        trades.append({
            'time':   entry_e['time'].strftime('%H:%M:%S'),
            'side':   entry_e.get('side', '-'),
            'price':  entry_e.get('price', 0),
            'amount': entry_e.get('amount', 0),
            'result': result['type'].upper() if result else 'PENDING',
            'pnl':    result.get('pnl', 0) if result else None,
        })
    trades = list(reversed(trades))[:10]

    elapsed = datetime.now() - start_time_global if start_time_global else timedelta(0)
    h, rem  = divmod(int(elapsed.total_seconds()), 3600)
    m       = rem // 60

    if balance is not None:
        live_state['balance'] = round(balance, 2)

    live_state['current_streak'] = current_streak
    live_state['next_bet']       = get_bet_amount(live_state.get('yes_price') or 55)

    # PnL history untuk chart
    result_events_sorted = sorted([e for e in events if e['type'] in ('win', 'lose')], key=lambda x: x['time'])
    pnl_history = []
    cum = 0
    for e in result_events_sorted:
        pnl_val = e.get('pnl') or 0
        cum += pnl_val
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
        'base_amount':     BASE_AMOUNT,
        'max_streak':      MAX_LOSESTREAK,
        'betting_mode':    BETTING_MODE,
        'martingale_start': MARTINGALE_START,
        'w1_range':        f"{W1_MIN}-{W1_MAX}¢",
        'pnl_history':     pnl_history,
    }

    tmp = config.DATA_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f)
    os.replace(tmp, config.DATA_FILE)

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

def get_token_id_for_slot(slot):
    """Fetch token IDs untuk slot tertentu (untuk redeem market lama)."""
    try:
        url = f"https://gamma-api.polymarket.com/markets?slug=btc-updown-5m-{slot}"
        res = requests.get(url, timeout=5).json()
        if res and len(res) > 0:
            token_ids = json.loads(res[0].get("clobTokenIds", "[]"))
            if len(token_ids) >= 2:
                return token_ids[0], token_ids[1]
        return None, None
    except:
        return None, None

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
        sys.exit(1)

def get_paper_entry_for_slot(slot):
    """
    Baca state_paper.json, return side ("YES"/"NO") kalau paper sudah entry
    di slot ini, atau None kalau belum.
    slot = unix timestamp kelipatan 300.
    """
    try:
        paper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_paper.json")
        with open(paper_path, "r") as f:
            data = json.load(f)
        slot_end = slot + 299
        for event in data.get("events", []):
            if event["type"] == "entry":
                t = datetime.fromisoformat(event["time"]).timestamp()
                if slot <= t <= slot_end:
                    return event["side"]
        return None
    except Exception as e:
        logger.warning(f"⚠️ Gagal baca paper state: {e}")
        return None

def place_market_order(client, token_id, amount_usd):
    """Place market order dengan nominal USD. Side selalu BUY (beli token)."""
    try:
        order_args = MarketOrderArgs(
            token_id=token_id,
            amount=amount_usd,
            side="BUY",
        )
        signed_order = client.create_market_order(order_args)
        resp = client.post_order(signed_order, OrderType.FOK)
        logger.info(f"   📤 Order response: {resp}")
        return resp
    except Exception as e:
        logger.error(f"❌ place_market_order error: {e}")
        return None

def get_condition_id_for_slot(slot):
    """Fetch conditionId dari gamma API untuk slot tertentu."""
    try:
        url = f"https://gamma-api.polymarket.com/markets?slug=btc-updown-5m-{slot}"
        res = requests.get(url, timeout=5).json()
        if res and len(res) > 0:
            return res[0].get("conditionId")
        return None
    except Exception as e:
        logger.warning(f"⚠️ get_condition_id error: {e}")
        return None

def _safe_exec_redeem(w3, condition_id):
    """
    Execute redeemPositions via Gnosis Safe (FUNDER_ADDRESS).
    FUNDER_ADDRESS = Safe contract, PRIVATE_KEY = sole owner (threshold=1).
    """
    from eth_abi import encode
    from eth_utils import keccak

    SAFE_TX_TYPEHASH = keccak(
        b"SafeTx(address to,uint256 value,bytes data,uint8 operation,"
        b"uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,"
        b"address gasToken,address refundReceiver,uint256 nonce)"
    )
    DOMAIN_TYPEHASH = keccak(b"EIP712Domain(uint256 chainId,address verifyingContract)")

    safe_addr = Web3.to_checksum_address(FUNDER_ADDRESS)
    account   = w3.eth.account.from_key(PRIVATE_KEY)

    # Build calldata untuk CTF redeemPositions
    ctf      = w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
    cond_b32 = bytes.fromhex(condition_id.removeprefix("0x"))
    raw_cd   = ctf.encode_abi("redeemPositions", [COLLATERAL, bytes(32), cond_b32, [1, 2]])
    calldata = bytes.fromhex(raw_cd[2:]) if isinstance(raw_cd, str) else bytes(raw_cd)

    # Get safe nonce
    SAFE_ABI_NONCE = [{'inputs':[],'name':'nonce','outputs':[{'type':'uint256'}],'stateMutability':'view','type':'function'}]
    safe_nonce = w3.eth.contract(address=safe_addr, abi=SAFE_ABI_NONCE).functions.nonce().call()

    # EIP-712 domain separator
    domain_sep = keccak(encode(
        ['bytes32', 'uint256', 'address'],
        [DOMAIN_TYPEHASH, 137, safe_addr]
    ))

    # Safe tx hash
    to          = CTF_ADDRESS
    value       = 0
    operation   = 0   # CALL
    safe_tx_gas = 0
    base_gas    = 0
    gas_price   = 0
    gas_token   = '0x0000000000000000000000000000000000000000'
    refund_recv = '0x0000000000000000000000000000000000000000'

    safe_tx_hash = keccak(encode(
        ['bytes32','address','uint256','bytes32','uint8',
         'uint256','uint256','uint256','address','address','uint256'],
        [SAFE_TX_TYPEHASH, to, value, keccak(calldata),
         operation, safe_tx_gas, base_gas, gas_price,
         gas_token, refund_recv, safe_nonce]
    ))

    final_hash = keccak(b'\x19\x01' + domain_sep + safe_tx_hash)

    # Sign (web3 v7: unsafe_sign_hash)
    sig        = account.unsafe_sign_hash(final_hash)
    sig_packed = sig.r.to_bytes(32,'big') + sig.s.to_bytes(32,'big') + bytes([sig.v])

    # execTransaction ABI
    EXEC_ABI = [{
        'inputs': [
            {'name':'to',             'type':'address'},
            {'name':'value',          'type':'uint256'},
            {'name':'data',           'type':'bytes'},
            {'name':'operation',      'type':'uint8'},
            {'name':'safeTxGas',      'type':'uint256'},
            {'name':'baseGas',        'type':'uint256'},
            {'name':'gasPrice',       'type':'uint256'},
            {'name':'gasToken',       'type':'address'},
            {'name':'refundReceiver', 'type':'address'},
            {'name':'signatures',     'type':'bytes'},
        ],
        'name': 'execTransaction',
        'outputs': [{'name':'success','type':'bool'}],
        'stateMutability': 'payable',
        'type': 'function',
    }]
    safe_contract = w3.eth.contract(address=safe_addr, abi=EXEC_ABI)

    tx_nonce  = w3.eth.get_transaction_count(account.address)
    tx = safe_contract.functions.execTransaction(
        to, value, calldata, operation,
        safe_tx_gas, base_gas, gas_price,
        gas_token, refund_recv, sig_packed
    ).build_transaction({
        'from':     account.address,
        'nonce':    tx_nonce,
        'gas':      300000,
        'gasPrice': w3.eth.gas_price,
    })

    signed  = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    return tx_hash

def _redeem_worker(slot):
    """Background thread untuk periodic redeem check (missed positions)."""
    try:
        condition_id = get_condition_id_for_slot(slot)
        if not condition_id:
            logger.warning("⚠️ redeem bg: conditionId tidak ditemukan, skip")
            return

        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if not w3.is_connected():
            logger.warning(f"⚠️ redeem bg: gagal connect ke {POLYGON_RPC}")
            return

        time.sleep(60)
        for attempt in range(1, 6):
            try:
                tx_hash = _safe_exec_redeem(w3, condition_id)
                logger.info(f"   💰 Redeem bg tx (attempt {attempt}): {tx_hash.hex()}")
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                if receipt.status == 1:
                    logger.info(f"   ✅ Redeem bg OK: block {receipt.blockNumber}")
                    return
                else:
                    if attempt < 5:
                        time.sleep(30)
            except Exception as e:
                logger.warning(f"   ⚠️ Redeem bg attempt {attempt} error: {e}")
                if attempt < 5:
                    time.sleep(30)
    except Exception as e:
        logger.warning(f"⚠️ redeem_worker error: {e}")

def redeem_positions(slot):
    """Background redeem — untuk periodic missed-position check."""
    t = threading.Thread(target=_redeem_worker, args=(slot,), daemon=True)
    t.start()

def _redeem_worker_by_condition_id(condition_id):
    """Background thread: redeem langsung pakai conditionId (tanpa gamma API lookup)."""
    try:
        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        if not w3.is_connected():
            logger.warning(f"⚠️ redeem cid: gagal connect ke {POLYGON_RPC}")
            return
        time.sleep(5)
        for attempt in range(1, 6):
            try:
                tx_hash = _safe_exec_redeem(w3, condition_id)
                logger.info(f"   💰 Redeem cid tx (attempt {attempt}): {tx_hash.hex()}")
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                if receipt.status == 1:
                    logger.info(f"   ✅ Redeem cid OK: block {receipt.blockNumber}")
                    return
                else:
                    if attempt < 5:
                        time.sleep(30)
            except Exception as e:
                logger.warning(f"   ⚠️ Redeem cid attempt {attempt} error: {e}")
                if attempt < 5:
                    time.sleep(30)
    except Exception as e:
        logger.warning(f"⚠️ _redeem_worker_by_condition_id error: {e}")

def _redeem_and_get_pnl(slot, balance_before, client):
    """Synchronous redeem lalu cek balance. Return actual PnL."""
    try:
        condition_id = get_condition_id_for_slot(slot)
        if not condition_id:
            logger.warning("⚠️ redeem: conditionId tidak ditemukan")
        else:
            from web3.middleware import ExtraDataToPOAMiddleware
            w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            if not w3.is_connected():
                logger.warning(f"⚠️ redeem: gagal connect ke {POLYGON_RPC}")
            else:
                logger.info(f"   ⏳ Tunggu 60s sebelum redeem slot {slot}...")
                time.sleep(60)
                for attempt in range(1, 6):
                    try:
                        tx_hash = _safe_exec_redeem(w3, condition_id)
                        logger.info(f"   💰 Redeem tx (attempt {attempt}): {tx_hash.hex()}")
                        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                        if receipt.status == 1:
                            logger.info(f"   ✅ Redeem OK: block {receipt.blockNumber}")
                            time.sleep(5)  # tunggu balance update
                            break
                        else:
                            logger.warning(f"   ❌ Reverted (attempt {attempt}), retry in 30s...")
                            if attempt < 5:
                                time.sleep(30)
                    except Exception as e:
                        logger.warning(f"   ⚠️ Redeem attempt {attempt} error: {e}")
                        if attempt < 5:
                            time.sleep(30)
                else:
                    logger.warning(f"⚠️ Redeem slot {slot} gagal setelah 5x")
    except Exception as e:
        logger.warning(f"⚠️ _redeem_and_get_pnl error: {e}")

    balance_after = get_balance(client)
    if balance_after is not None and balance_before is not None:
        return round(balance_after - balance_before, 4)
    logger.warning("⚠️ Tidak bisa hitung PnL dari balance, pakai 0")
    return 0.0

# ─────────────────────────────────────────
# RESULT RECORDING
# ─────────────────────────────────────────

def _redeem_bg(slot, client):
    """Background thread: hanya redeem on-chain. PnL sudah dihitung di main thread."""
    try:
        condition_id = get_condition_id_for_slot(slot)
        if not condition_id:
            return
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        if not w3.is_connected():
            return
        logger.info(f"   ⏳ [BG] Tunggu 60s sebelum redeem slot {slot}...")
        time.sleep(60)
        for attempt in range(1, 6):
            try:
                tx_hash = _safe_exec_redeem(w3, condition_id)
                logger.info(f"   💰 [BG] Redeem tx (attempt {attempt}): {tx_hash}")
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                if receipt.status == 1:
                    logger.info(f"   ✅ [BG] Redeem OK: block {receipt.blockNumber}")
                    return
            except Exception as e:
                logger.warning(f"   ⚠️ [BG] Redeem attempt {attempt} gagal: {e}")
                time.sleep(30)
    except Exception as e:
        logger.warning(f"⚠️ _redeem_bg error: {e}")

def record_result(winner, pending_side, pending_price, pending_amount, client, yes_token, no_token, balance_before=None, slot=None, taking_amount=None):
    global cumulative_loss, current_streak, total_pnl, current_bet

    if winner == pending_side:
        cumulative_loss = 0.0
        current_streak  = 0
        if BETTING_MODE == 'martingale_2x':
            current_bet = BASE_AMOUNT
        # Pakai takingAmount dari order response (actual shares) kalau ada,
        # fallback ke teoritis kalau tidak ada (misal restart)
        if taking_amount and taking_amount > 0:
            net = round(taking_amount - pending_amount, 4)
        else:
            net = round(pending_amount * (100.0 / pending_price - 1.0), 4)
        total_pnl += net
        events.append({'time': datetime.now(), 'type': 'win', 'amount': pending_amount, 'pnl': net})
        logger.info(f"   🎉 WIN | {pending_side} @ {pending_price:.1f}¢ | PnL: +${net:.4f}")
        save_data()
        save_state()
        # Redeem on-chain di background — tidak block market berikutnya
        if slot:
            t = threading.Thread(target=_redeem_bg, args=(slot, client), daemon=True)
            t.start()
    else:
        net = round(-pending_amount, 4)
        current_streak += 1
        total_pnl      += net
        # Update bet tracking per mode
        if BETTING_MODE == 'martingale_2x':
            current_bet = round(current_bet * 2, 2)
        elif BETTING_MODE == 'martingale':
            if current_streak == MARTINGALE_START:
                # Martingale baru aktif — reset ke last bet saja (losses sebelumnya hangus)
                cumulative_loss = pending_amount
            elif current_streak > MARTINGALE_START:
                cumulative_loss += pending_amount
            # else: streak < MARTINGALE_START → ignore
        events.append({'time': datetime.now(), 'type': 'lose', 'amount': pending_amount, 'pnl': net})
        logger.info(f"   😢 LOSE | {pending_side} @ {pending_price:.1f}¢ | ${net:.4f} | streak={current_streak}")
        save_data()
        save_state()

# ─────────────────────────────────────────
# SIGNAL HANDLER
# ─────────────────────────────────────────

def signal_handler(sig, frame):
    logger.info("\n🔴 Real bot dihentikan manual")
    save_state(g_pending_slot, g_pending_side, g_pending_price, g_pending_amount, g_pending_market_num, g_pending_balance_before,
               g_pos1_slot, g_pos1_side, g_pos1_price, g_pos1_amount, g_pos1_taking_amount, g_pos1_balance_before)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# ─────────────────────────────────────────
# MAIN BOT LOOP
# ─────────────────────────────────────────

def main():
    global market_count, start_time_global, cumulative_loss, current_streak
    global g_pending_slot, g_pending_side, g_pending_price, g_pending_amount, g_pending_market_num, g_pending_balance_before
    global g_pos1_slot, g_pos1_side, g_pos1_price, g_pos1_amount, g_pos1_taking_amount, g_pos1_balance_before

    (pending_slot, pending_side, pending_price, pending_amount, pending_market_num, pending_balance_before,
     loaded_pos1_slot, loaded_pos1_side, loaded_pos1_price, loaded_pos1_amount, loaded_pos1_taking_amount, loaded_pos1_balance_before) = load_state()
    pending_taking_amount = None

    # Kalau ada pos1 tersimpan (entry aktif waktu bot stop sebelum 295s), promote ke pending
    if loaded_pos1_side and not pending_slot:
        logger.info(f"⚠️ Ditemukan entry aktif dari sesi sebelumnya: {loaded_pos1_side} @ {loaded_pos1_price}¢ ${loaded_pos1_amount} — promote ke pending")
        pending_slot           = loaded_pos1_slot
        pending_side           = loaded_pos1_side
        pending_price          = loaded_pos1_price
        pending_amount         = loaded_pos1_amount
        pending_taking_amount  = loaded_pos1_taking_amount
        pending_market_num     = market_count  # market terakhir yang tercatat
        pending_balance_before = loaded_pos1_balance_before

    logger.info("=" * 70)
    logger.info("💰 REAL TRADING BOT")
    logger.info("=" * 70)
    logger.info(f"   Start      : {start_time_global.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   Base       : ${BASE_AMOUNT}")
    logger.info(f"   Max streak : {MAX_LOSESTREAK}x")
    logger.info(f"   Entry      : Ikuti paper bot, harga {W1_MIN}-{W1_MAX}¢ (bebas waktu)")
    logger.info(f"   Mode       : {BETTING_MODE} (martingale_start={MARTINGALE_START})")
    logger.info("=" * 70)

    client       = setup_client()
    yes_token    = None
    no_token     = None
    current_slot = None
    market_start = None
    pos1_side           = None
    pos1_price          = None
    pos1_amount         = None
    pos1_taking_amount  = None
    pos1_balance_before = None
    entered             = False

    balance = get_balance(client)
    save_data(balance)

    last_redeem_check  = 0
    last_balance_check = 0

    while True:
        try:
            now  = int(time.time())
            slot = (now // 300) * 300

            # ── PERIODIC BALANCE CHECK (tiap 1 menit) ────────────
            if now - last_balance_check >= 60:
                last_balance_check = now
                balance = get_balance(client)
                save_data(balance)

            # ── PERIODIC REDEEM CHECK (tiap 5 menit) ─────────────
            if now - last_redeem_check >= 60:
                last_redeem_check = now
                try:
                    all_positions = []
                    _offset = 0
                    _limit  = 500
                    while True:
                        _resp = requests.get(
                            f"https://data-api.polymarket.com/positions"
                            f"?user={FUNDER_ADDRESS}&sizeThreshold=0.01&limit={_limit}&offset={_offset}",
                            timeout=5
                        ).json()
                        all_positions.extend(_resp)
                        if len(_resp) < _limit:
                            break
                        _offset += _limit
                    pending_redeems = [
                        x for x in all_positions
                        if x.get('redeemable') and x.get('currentValue', 0) > 0
                    ]
                    if pending_redeems:
                        logger.info(f"💰 Ditemukan {len(pending_redeems)} posisi redeemable")
                        for pos in pending_redeems:
                            cid = pos.get('conditionId')
                            logger.info(f"   → Redeem ${pos['currentValue']:.2f} | {pos['title']}")
                            if cid:
                                # Punya conditionId langsung — redeem tanpa gamma API lookup
                                t = threading.Thread(
                                    target=_redeem_worker_by_condition_id,
                                    args=(cid,), daemon=True
                                )
                                t.start()
                            else:
                                s = int(pos['slug'].split('-')[-1])
                                redeem_positions(s)
                except Exception as e:
                    logger.warning(f"⚠️ periodic redeem check error: {e}")

            # ── CEK MAX LOSESTREAK ────────────────────────────
            if current_streak >= MAX_LOSESTREAK:
                balance = get_balance(client)
                logger.warning(f"🚨 MAX LOSESTREAK {MAX_LOSESTREAK}x tercapai! Bot stop.")
                live_state['status'] = f"🚨 STOP - Max losestreak {MAX_LOSESTREAK}x"
                save_data(balance)
                save_state(pending_slot, pending_side, pending_price, pending_amount, pending_market_num, pending_balance_before)
                # Tulis flag untuk telegram_bot baca
                with open("real_bot_stopped.json", "w") as f:
                    json.dump({
                        "reason": "max_losestreak",
                        "streak": current_streak,
                        "total_pnl": round(total_pnl, 2),
                        "balance": balance,
                        "time": datetime.now().isoformat(),
                    }, f)
                sys.exit(2)

            # ── MARKET BARU ──────────────────────────────────────
            if slot != current_slot:
                market_count += 1

                if pending_slot and pending_side:
                    logger.info(f"\n🔍 CEK HASIL MARKET #{pending_market_num}")
                    live_state['status'] = f"Menunggu hasil market #{pending_market_num}..."
                    save_data()

                    # Ambil token untuk market lama (bisa None kalau baru restart)
                    redeem_yes, redeem_no = yes_token, no_token
                    if not redeem_yes:
                        redeem_yes, redeem_no = get_token_id_for_slot(pending_slot)
                        logger.info(f"   🔑 Token lama diambil: {redeem_yes}")

                    by, bn = get_market_price(client, redeem_yes, redeem_no)
                    backup_winner = None
                    if by is not None and bn is not None and by != bn:
                        backup_winner = "YES" if by > bn else "NO"
                    logger.info(f"   💾 Backup: {backup_winner} (YES {by}¢ | NO {bn}¢)")

                    winner = None
                    waited = 0
                    while waited < 25:
                        winner = get_market_result(pending_slot)
                        if winner:
                            logger.info(f"   ✅ Hasil API: {winner}")
                            break
                        logger.info(f"   ⏳ Belum resolved, tunggu 5s... ({waited}s/25s)")
                        time.sleep(5)
                        waited += 5

                    if not winner:
                        if backup_winner:
                            winner = backup_winner
                            logger.info(f"   ⚠️ API timeout, pakai backup: {winner}")
                        else:
                            logger.info(f"   ❌ Hasil tidak didapat, skip")

                    if winner:
                        record_result(winner, pending_side, pending_price, pending_amount, client, redeem_yes, redeem_no, balance_before=pending_balance_before, slot=pending_slot, taking_amount=pending_taking_amount)
                        pending_slot = pending_side = pending_price = pending_amount = pending_market_num = pending_balance_before = None
                        g_pending_slot = g_pending_side = g_pending_price = g_pending_amount = g_pending_market_num = g_pending_balance_before = None

                yes_token, no_token, current_slot = get_current_token_id()

                if yes_token:
                    balance = get_balance(client)
                    logger.info(f"\n{'='*70}")
                    bal_str = f"${balance:.2f}" if balance is not None else "-"
                    logger.info(f"💰 REAL MARKET #{market_count} | Balance: {bal_str} | Streak: {current_streak}x | CumLoss: ${cumulative_loss:.2f}")
                    logger.info(f"{'='*70}")

                    market_start = slot
                    pos1_side           = None
                    pos1_price          = None
                    pos1_amount         = None
                    pos1_taking_amount  = None
                    pos1_balance_before = None
                    g_pos1_slot = g_pos1_side = g_pos1_price = g_pos1_amount = g_pos1_taking_amount = g_pos1_balance_before = None
                    entered             = False
                    locked_entry_side   = None   # sisi yang sudah dicoba (lock setelah FOK gagal)
                    locked_entry_token  = None
                    paper_entry_time    = None   # waktu pertama paper entry terdeteksi

                    next_bet = get_bet_amount(55)

                    live_state['market_num'] = market_count
                    live_state['pos_side']   = None
                    live_state['pos_price']  = None
                    live_state['pos_amount'] = None
                    live_state['status']     = f"Menunggu sinyal paper | harga ≤{W1_MAX}¢ | Next bet: ${next_bet:.2f}"
                    save_data(balance)

            if not yes_token or market_start is None:
                time.sleep(config.LOOP_INTERVAL)
                continue

            market_elapsed = now - market_start
            yes_price, no_price = get_market_price(client, yes_token, no_token)

            if yes_price is None:
                time.sleep(config.LOOP_INTERVAL)
                continue

            live_state['yes_price']      = yes_price
            live_state['no_price']       = no_price
            live_state['market_elapsed'] = market_elapsed

            # ── TANDAI PENDING detik 295 ──────────────────────
            if market_elapsed >= 295 and pos1_side and not pending_slot:
                pending_slot           = current_slot
                pending_side           = pos1_side
                pending_price          = pos1_price
                pending_amount         = pos1_amount
                pending_taking_amount  = pos1_taking_amount
                pending_market_num     = market_count
                pending_balance_before = pos1_balance_before
                live_state['status']   = "🔍 Menunggu hasil..."
                logger.info(f"   📌 Posisi #{market_count} ditandai pending")
                g_pending_slot           = pending_slot
                g_pending_side           = pending_side
                g_pending_price          = pending_price
                g_pending_amount         = pending_amount
                g_pending_market_num     = pending_market_num
                g_pending_balance_before = pending_balance_before
                # pos1 sudah di-promote ke pending, clear dari state
                g_pos1_slot = g_pos1_side = g_pos1_price = g_pos1_amount = g_pos1_taking_amount = g_pos1_balance_before = None
                save_state(pending_slot, pending_side, pending_price, pending_amount, pending_market_num, pending_balance_before)


            # ── PUNYA POSISI ───────────────────────────────────
            if pos1_side:
                live_state['status']    = f"{'🟢' if pos1_side == 'YES' else '🔵'} ENTRY {pos1_side} @ {pos1_price:.1f}¢ | ${pos1_amount:.2f}"
                live_state['pos_side']  = pos1_side
                live_state['pos_price'] = pos1_price
                live_state['pos_amount']= pos1_amount

            # ── CEK W1 (tunggu paper entry dulu, lalu scan harga) ──────
            elif not entered and get_paper_entry_for_slot(current_slot):
                # Catat waktu pertama paper entry terdeteksi
                if paper_entry_time is None:
                    paper_entry_time = now

                entry_side   = None
                entry_price  = None
                entry_token  = None

                # Timeout 60 detik dari paper entry
                if now - paper_entry_time > 180:
                    logger.info(f"   ⏭ [W1] Timeout 180s dari paper entry, skip market ini")
                    entered = True
                elif locked_entry_side:
                    # Sudah pernah FOK gagal sebelumnya — hanya boleh retry di sisi yang sama
                    if locked_entry_side == "YES" and yes_price <= W1_MAX:
                        entry_side, entry_price, entry_token = "YES", yes_price, yes_token
                    elif locked_entry_side == "NO" and no_price <= W1_MAX:
                        entry_side, entry_price, entry_token = "NO", no_price, no_token
                    else:
                        logger.info(f"   ⏭ [W1] Harga {locked_entry_side} keluar range setelah FOK gagal, skip market ini")
                        entered = True  # skip, tidak entry market ini
                else:
                    # Entry pertama — pilih sisi normal
                    if yes_price <= W1_MAX:
                        entry_side, entry_price, entry_token = "YES", yes_price, yes_token
                    elif no_price <= W1_MAX:
                        entry_side, entry_price, entry_token = "NO", no_price, no_token

                if entry_price:
                    # Hitung bet amount berdasarkan mode
                    bet_amount = get_bet_amount(entry_price)

                    logger.info(f"   🟢 [W1] ENTRY {entry_side} @ {entry_price:.1f}¢ | Amount: ${bet_amount:.2f} | Streak: {current_streak}x")

                    bal_before = get_balance(client)
                    resp       = place_market_order(client, entry_token, bet_amount)

                    if resp:
                        entered             = True
                        locked_entry_side   = None  # reset lock
                        locked_entry_token  = None
                        pos1_side           = entry_side
                        pos1_price          = entry_price
                        pos1_amount         = bet_amount
                        pos1_taking_amount  = float(resp.get('takingAmount', 0))
                        pos1_balance_before = bal_before

                        # Sync globals supaya signal_handler bisa simpan pos1 kalau bot dihentikan
                        g_pos1_slot           = current_slot
                        g_pos1_side           = pos1_side
                        g_pos1_price          = pos1_price
                        g_pos1_amount         = pos1_amount
                        g_pos1_taking_amount  = pos1_taking_amount
                        g_pos1_balance_before = pos1_balance_before

                        events.append({
                            'time':   datetime.now(),
                            'type':   'entry',
                            'side':   entry_side,
                            'price':  entry_price,
                            'amount': bet_amount,
                        })

                        live_state['status']     = f"{'🟢' if entry_side == 'YES' else '🔵'} ENTRY {entry_side} @ {entry_price:.1f}¢ | ${bet_amount:.2f}"
                        live_state['pos_side']   = entry_side
                        live_state['pos_price']  = entry_price
                        live_state['pos_amount'] = bet_amount
                        save_data()
                        save_state(pending_slot, pending_side, pending_price, pending_amount, pending_market_num, pending_balance_before,
                                   current_slot, pos1_side, pos1_price, pos1_amount, pos1_taking_amount, pos1_balance_before)
                    else:
                        # FOK gagal — lock sisi ini, retry di loop berikutnya tapi hanya sisi yang sama
                        locked_entry_side  = entry_side
                        locked_entry_token = entry_token
                        logger.warning(f"   ⚠️ Order FOK gagal @ {entry_price:.1f}¢ ({entry_side}), retry hanya di {entry_side} pada loop berikutnya")

            save_data()
            time.sleep(config.LOOP_INTERVAL)

        except Exception as e:
            logger.error(f"❌ Error: {e}")
            save_state(pending_slot, pending_side, pending_price, pending_amount, pending_market_num, pending_balance_before,
                       g_pos1_slot, g_pos1_side, g_pos1_price, g_pos1_amount, g_pos1_taking_amount, g_pos1_balance_before)
            time.sleep(5)

if __name__ == "__main__":
    main()
