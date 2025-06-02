from dotenv import load_dotenv
import os
import time
import requests
import json
from datetime import datetime, timedelta
import zoneinfo
from binance.client import Client

# Load .env
load_dotenv()

# Binance API
client = Client(
    os.getenv("BINANCE_API_KEY"),
    os.getenv("BINANCE_API_SECRET")
)

# คู่เทรดที่ต้องการตรวจสอบ
TRADING_PAIRS = [
    "AUSDT", "AAVEUSDT", "ADAUSDT", "AIXBTUSDT", "ALGOUSDT", "APTUSDT", "ARBUSDT",
    "ARKMUSDT", "ATOMUSDT", "AXSUSDT", "AVAXUSDT", "BCHUSDT", "BERAUSDT", "BIOUSDT", "BNBUSDT",
    "BONKUSDT", "BTCUSDT", "BTTCUSDT", "CAKEUSDT", "CETUSUSDT", "COOKIEUSDT", "CRVUSDT", "CVXUSDT",
    "DEXEUSDT", "DOGEUSDT", "DOTUSDT", "EIGENUSDT", "ENAUSDT", "ENSUSDT", "ETCUSDT", "ETHUSDT",
    "ETHFIUSDT", "FETUSDT", "FLOKIUSDT", "FLOWUSDT", "FORMUSDT", "GALAUSDT", "GRTUSDT",
    "HBARUSDT", "HUMAUSDT", "ICPUSDT", "IMXUSDT", "INITUSDT", "INJUSDT", "IOTAUSDT",
    "JASMYUSDT", "JTOUSDT", "JUPUSDT", "KAIAUSDT", "KAITOUSDT", "KERNELUSDT", "LDOUSDT", "LTCUSDT",
    "LINKUSDT", "MASKUSDT", "MKRUSDT", "MEUSDT", "MOVEUSDT", "NEARUSDT", "NEIROUSDT",
    "NEOUSDT", "NEXOUSDT", "NILUSDT", "NOTUSDT", "ONDOUSDT", "OPUSDT", "ORCAUSDT", "PAXGUSDT",
    "PENDLEUSDT", "PENGUUSDT", "PEPEUSDT", "POLUSDT", "PNUTUSDT", "PYTHUSDT", "QNTUSDT",
    "RAYUSDT", "RENDERUSDT", "RUNEUSDT", "SUSDT", "SANDUSDT", "SEIUSDT", "SHIBUSDT", "SOLUSDT",
    "SOPHUSDT", "SSVUSDT", "STORJUSDT", "STXUSDT", "SUIUSDT", "TAOUSDT", "THETAUSDT", "TIAUSDT", "TONUSDT",
    "TNSRUSDT", "TRBUSDT", "TRUMPUSDT", "TRXUSDT", "UNIUSDT", "VETUSDT", "VIRTUALUSDT", "WCTUSDT",
    "WIFUSDT", "WLDUSDT", "XLMUSDT", "XRPUSDT", "ZECUSDT", "ZKUSDT", "ZROUSDT"
]

WEBHOOK_URL_EMA = os.getenv("WEBHOOK_URL_EMA")
WEBHOOK_URL_RSI = os.getenv("WEBHOOK_URL_RSI")
STATE_FILE = 'ema_state.json'
TIMEFRAME = '4h'
ALLOWED_HOURS = [3, 7, 11, 15, 19, 23]

# --- Utility Functions ---
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def fetch_price_data(symbol):
    klines = client.get_klines(symbol=symbol, interval=TIMEFRAME, limit=100)
    return [float(kline[4]) for kline in klines]

def calculate_ema(prices, period):
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price * k) + (ema * (1 - k))
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [delta if delta > 0 else 0 for delta in deltas]
    losses = [-delta if delta < 0 else 0 for delta in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def send_discord_alert(strategy, pair, price, event, timestamp, signal_type):
    color = 0x00FF00 if signal_type == "BUY" else 0xFF0000
    emoji = "🟢" if signal_type == "BUY" else "🔴"
    webhook_url = WEBHOOK_URL_EMA if strategy == "ema" else WEBHOOK_URL_RSI
    display_pair = pair.replace("USDT", "/USDT")

    if price >= 100:
        formatted_price = f"{price:,.2f}"
    elif price >= 10:
        formatted_price = f"{price:,.3f}"
    elif price >= 1:
        formatted_price = f"{price:,.4f}"
    elif price >= 0.01:
        formatted_price = f"{price:,.5f}"
    else:
        formatted_price = f"{price:,.6f}"

    label_width = 12
    description = (
        f"```\n"
        f"{'SIGNAL'.ljust(label_width)}: {signal_type} {emoji}\n"
        f"{'PAIR'.ljust(label_width)}: {display_pair}\n"
        f"{'PRICE'.ljust(label_width)}: {formatted_price} USDT\n"
        f"{'EVENT'.ljust(label_width)}: {event}\n"
        f"{'TIMESTAMP'.ljust(label_width)}: {timestamp}\n"
        f"```"
    )
    embed = {
        "title": "📈 EMA Crossover Signal" if strategy == "ema" else "📉 RSI Strategy Signal",
        "description": description,
        "color": color,
        "footer": {"text": "Signal by Sota"}
    }
    try:
        response = requests.post(webhook_url, json={"embeds": [embed]})
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to send alert for {pair} ({strategy}): {e}")

# --- Core Signal Logic ---
def check_signals():
    state = load_state()
    tz = zoneinfo.ZoneInfo("Asia/Bangkok")
    now = datetime.now(tz)
    now_str = now.strftime('%Y-%m-%d %H:%M GMT+7')

    for pair in TRADING_PAIRS:
        try:
            prices = fetch_price_data(pair)
            ema12 = calculate_ema(prices[-26:], 12)
            ema26 = calculate_ema(prices[-26:], 26)
            last_price = prices[-1]

            prev_state = state.get(pair, {}) if isinstance(state.get(pair), dict) else {}
            prev_signal = prev_state.get("signal")

            # เพิ่มเงื่อนไข confirm ด้วยราคาปิดล่าสุด
            if ema12 > ema26 and last_price > ema12 and last_price > ema26:
                current_signal = "buy"
            elif ema12 < ema26 and last_price < ema12 and last_price < ema26:
                current_signal = "sell"
            else:
                current_signal = prev_signal  # ไม่เปลี่ยนสัญญาณถ้าไม่ผ่านเงื่อนไข

            if current_signal != prev_signal:
                signal_type = "BUY" if current_signal == "buy" else "SELL"
                event = f"EMA12 {'>' if signal_type == 'BUY' else '<'} EMA26 (TF: 4H) + Confirm by Close Price"
                send_discord_alert("ema", pair, last_price, event, now_str, signal_type)
                time.sleep(1)
                state[pair] = {"signal": current_signal, "last_sent_at": now.isoformat()}
            elif pair not in state:
                state[pair] = {"signal": current_signal, "last_sent_at": None}

            # RSI logic ไม่เปลี่ยน
            rsi = calculate_rsi(prices)
            if rsi is not None and rsi <= 30:
                send_discord_alert("rsi", pair, last_price, f"RSI = {rsi:.2f} (TF: 4H)", now_str, "BUY")
                time.sleep(1)

        except Exception as e:
            print(f"❌ Error checking {pair}: {e}")

    save_state(state)

# --- Scheduling ---
def get_next_run_time(now):
    today_runs = [
        datetime(now.year, now.month, now.day, h, 0, 0, tzinfo=now.tzinfo)
        for h in ALLOWED_HOURS
    ]
    future_runs = [t for t in today_runs if t > now]
    if future_runs:
        return future_runs[0]
    tomorrow = now + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, 3, 0, 0, tzinfo=now.tzinfo)

# --- Entry Point ---
if __name__ == "__main__":
    print("🚀 Starting trading signal bot...")
    tz = zoneinfo.ZoneInfo("Asia/Bangkok")
    check_signals()

    while True:
        now = datetime.now(tz)
        next_run = get_next_run_time(now)
        wait_seconds = (next_run - now).total_seconds()
        print(f"🕒 Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}, sleeping for {int(wait_seconds)} seconds...")
        time.sleep(wait_seconds)
        check_signals()
