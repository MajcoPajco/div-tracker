import streamlit as st
import yfinance as yf
import pytz
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, time, timedelta
import re

st.set_page_config(page_title="Dividend tracker", layout="wide")

# Config
HOLDINGS_FILE = Path("holdings.json")
FETCH_TTL = 60
DIVIDENDMAX_TIMEOUT = 8

# CSS
st.markdown("""
<style>
.main-title { font-size:12px; font-weight:600; margin-bottom:6px; }
.compact-table { background: white; border-collapse: collapse; width: 100%; font-size:13px; }
.compact-table th, .compact-table td { padding:6px 8px; border-bottom: 1px solid #eee; text-align:left; white-space: nowrap; }
.compact-table tr { height: 28px; }
input[placeholder="Ticker"] { max-width:190px !important; width:190px !important; height:30px !important; }
input[placeholder="Množstvo"] { max-width:190px !important; width:190px !important; height:30px !important; }
.stButton>button { margin-top: 0.2rem; padding: .35rem .6rem; font-size:13px; }
</style>
""", unsafe_allow_html=True)

# Exchanges
EXCHANGES = [
    {"symbol":"NYSE","name": "NYSE", "city": "New York", "country": "USA", "tz": "America/New_York", "open": time(9,30), "close": time(16,0)},
    {"symbol":"NASDAQ","name": "NASDAQ", "city": "New York", "country": "USA", "tz": "America/New_York", "open": time(9,30), "close": time(16,0)},
    {"symbol":"LSE","name": "LSE", "city": "London", "country": "UK", "tz": "Europe/London", "open": time(8,0), "close": time(16,30)},
    {"symbol":"ENX","name": "Euronext (Paris)", "city": "Paris", "country": "France", "tz": "Europe/Paris", "open": time(9,0), "close": time(17,30)},
    {"symbol":"XETRA","name": "XETRA (Frankfurt)", "city": "Frankfurt", "country": "Germany", "tz": "Europe/Berlin", "open": time(9,0), "close": time(17,30)},
    {"symbol":"TSE","name": "TSE (Tokyo)", "city": "Tokyo", "country": "Japan", "tz": "Asia/Tokyo", "open": time(9,0), "close": time(15,0)},
    {"symbol":"HKEX","name": "HKEX", "city": "Hong Kong", "country": "Hong Kong", "tz": "Asia/Hong_Kong", "open": time(9,30), "close": time(16,0)},
    {"symbol":"SSE","name": "SSE (Shanghai)", "city": "Shanghai", "country": "China", "tz": "Asia/Shanghai", "open": time(9,30), "close": time(15,0)},
]

BRATISLAVA_TZ = pytz.timezone("Europe/Bratislava")

# Helpers
def format_timedelta(td):
    if td is None:
        return ""
    if td.total_seconds() < 0:
        td = -td
    total_seconds = int(td.total_seconds())
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    return f"{hrs}h {mins}min"

def next_open_datetime(tzname, open_time):
    tzloc = pytz.timezone(tzname)
    candidate = datetime.now(tzloc).date()
    while True:
        if candidate.weekday() < 5:
            return tzloc.localize(datetime.combine(candidate, open_time))
        candidate = candidate + timedelta(days=1)

def get_exchange_rows():
    rows = []
    for ex in EXCHANGES:
        tzname = ex["tz"]
        tzloc = pytz.timezone(tzname)
        now_local = datetime.now(tzloc)
        today = now_local.date()
        if now_local.weekday() >= 5:
            nxt = next_open_datetime(tzname, ex["open"])
            nxt_br = nxt.astimezone(BRATISLAVA_TZ)
            diff = nxt_br - datetime.now(BRATISLAVA_TZ)
            display = f"Opens in {format_timedelta(diff)}"
            color = "red"
        else:
            open_dt = tzloc.localize(datetime.combine(today, ex["open"]))
            close_dt = tzloc.localize(datetime.combine(today, ex["close"]))
            if open_dt <= now_local <= close_dt:
                opened_since = now_local - open_dt
                display = f"Open {format_timedelta(opened_since)}"
                color = "green"
            else:
                if now_local < open_dt:
                    next_open = open_dt
                else:
                    nxt = today + timedelta(days=1)
                    while nxt.weekday() >= 5:
                        nxt += timedelta(days=1)
                    next_open = tzloc.localize(datetime.combine(nxt, ex["open"]))
                next_open_br = next_open.astimezone(BRATISLAVA_TZ)
                diff = next_open_br - datetime.now(BRATISLAVA_TZ)
                display = f"Opens in {format_timedelta(diff)}"
                color = "red"
        local_now_for_display = datetime.now(tzloc).strftime("%H:%M")
        rows.append({
            "Znacka": ex.get("symbol",""),
            "Burza": ex["name"],
            "Mesto": ex["city"],
            "Stat": ex["country"],
            "Miestny cas": local_now_for_display,
            "Stav": display,
            "color": color
        })
    return rows

# Persistence
def save_holdings_file():
    try:
        to_save = []
        for h in st.session_state.holdings:
            item = {"ticker": h.get("ticker"), "quantity": h.get("quantity", 0)}
            if h.get("declared") is not None:
                item["declared"] = bool(h.get("declared", False))
            if h.get("next_div") is not None:
                item["next_div"] = h.get("next_div")
            to_save.append(item)
        with open(HOLDINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Chyba pri uložení holdings: {e}")

def load_holdings_file():
    if not HOLDINGS_FILE.exists():
        return []
    try:
        with open(HOLDINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        st.error(f"Chyba pri načítaní holdings súboru: {e}")
        return []
    holdings = []
    for item in data:
        holdings.append({
            "ticker": item.get("ticker"),
            "quantity": item.get("quantity", 0),
            "declared": bool(item.get("declared", False)),
            "next_div": item.get("next_div", None),
            # runtime-only fields (filled from internet)
            "name": None,
            "price": None,
            "currency": None,
            "dividendRate": None,
            "dividendYield": None,
            "exDividendDate": None,
            "exchange": None,
            "exchange_city": None,
            "exchange_country": None,
            "_next_div_auto": None,
            "_freq_label": None,
            "_sum_div_12m": None,
            "_nasl_div_announced": None,
            "auto_declared": False
        })
    return holdings

def format_qty(q):
    try:
        qf = float(q)
    except:
        return str(q)
    s = f"{qf:.4f}"
    s = s.rstrip('0').rstrip('.')
    return s

# yfinance fetch
@st.cache_data(ttl=FETCH_TTL)
def fetch_ticker_info(ticker):
    ticker = ticker.upper()
    tk = yf.Ticker(ticker)
    info = {}
    try:
        info = tk.info or {}
    except:
        info = {}
    valid = False
    try:
        hist = tk.history(period="1d")
        if hist is not None and len(hist) > 0:
            valid = True
    except:
        valid = False
    price = info.get("regularMarketPrice")
    if price is not None:
        valid = True
    exDate = info.get("exDividendDate")
    ex_dt = None
    if exDate:
        try:
            ex_dt = datetime.fromtimestamp(int(exDate)).date()
        except:
            ex_dt = None
    exch = info.get("exchange") or info.get("exchangeShortName") or info.get("market")
    country = info.get("country")
    # dividends series
    divs = None
    try:
        divs = tk.dividends
    except:
        divs = None
    raw_info = {}
    try:
        raw_info = tk.info or {}
    except:
        raw_info = {}
    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "price": price,
        "currency": info.get("currency",""),
        "dividendRate": info.get("dividendRate") or info.get("trailingAnnualDividendRate"),
        "dividendYield": info.get("dividendYield"),
        "exDividendDate": ex_dt,
        "dividends_series": divs,
        "valid": valid,
        "exchange": exch,
        "country": country,
        "raw_info": raw_info
    }

# suffix map and exchange inference
SUFFIX_MAP = {
    "L": ("LSE","London","UK"),
    "PA": ("Euronext (Paris)","Paris","France"),
    "F": ("XETRA (Frankfurt)","Frankfurt","Germany"),
    "DE": ("XETRA (Frankfurt)","Frankfurt","Germany"),
    "HK": ("HKEX","Hong Kong","Hong Kong"),
    "SS": ("SSE (Shanghai)","Shanghai","China"),
    "SZ": ("SSE (Shenzhen)","Shenzhen","China"),
    "TO": ("TSX","Toronto","Canada"),
    "T": ("TSE (Tokyo)","Tokyo","Japan"),
    "AX": ("ASX","Sydney","Australia"),
}

def infer_exchange_info(ticker, info):
    exch = info.get("exchange")
    country = info.get("country")
    if exch:
        ex_l = str(exch).lower()
        if "nasdaq" in ex_l or "nms" in ex_l:
            return ("NASDAQ","New York","USA")
        if "nyse" in ex_l or "new york" in ex_l:
            return ("NYSE","New York","USA")
        if "lse" in ex_l or "london" in ex_l:
            return ("LSE","London","UK")
        if "paris" in ex_l or "euronext" in ex_l:
            return ("ENX","Paris","France")
        if "frankfurt" in ex_l or "xetra" in ex_l:
            return ("XETRA","Frankfurt","Germany")
        if "hong" in ex_l or "hkex" in ex_l:
            return ("HKEX","Hong Kong","Hong Kong")
        if "tokyo" in ex_l or "tse" in ex_l or "jpx" in ex_l:
            return ("TSE","Tokyo","Japan")
        if country:
            return (exch, "", country)
    if "." in ticker:
        suf = ticker.split(".")[-1].upper()
        if suf in SUFFIX_MAP:
            return SUFFIX_MAP[suf]
    return ("", "", "")

# Init session
if "holdings" not in st.session_state:
    st.session_state.holdings = load_holdings_file()

if "add_error" not in st.session_state:
    st.session_state.add_error = ""
if "add_success" not in st.session_state:
    st.session_state.add_success = ""

# Add handler
def handle_add():
    t = st.session_state.get("add_ticker","").strip().upper()
    raw_qty = st.session_state.get("add_qty","").strip()
    st.session_state.add_error = ""
    st.session_state.add_success = ""
    if t == "" or raw_qty == "":
        return
    try:
        qty = float(raw_qty.replace(',', '.'))
    except:
        st.session_state.add_error = "Neplatné množstvo"
        return
    info = fetch_ticker_info(t)
    if not info.get("valid", False):
        st.session_state.add_error = f"Unknown ticker: {t}"
        st.session_state["add_ticker"] = ""
        st.session_state["add_qty"] = ""
        return
    found = False
    for h in st.session_state.holdings:
        if h["ticker"] == info["ticker"]:
            h["quantity"] = float(h.get("quantity",0.0)) + float(qty)
            found = True
            break
    if not found:
        exch_sym, exch_city, exch_country = infer_exchange_info(t, info)
        st.session_state.holdings.append({
            "ticker": info["ticker"],
            "quantity": float(qty),
            "declared": False,
            "next_div": None,
            "name": None,
            "price": None,
            "currency": None,
            "dividendRate": None,
            "dividendYield": None,
            "exDividendDate": None,
            "exchange": exch_sym,
            "exchange_city": exch_city,
            "exchange_country": exch_country,
            "_next_div_auto": None,
            "_freq_label": None,
            "_sum_div_12m": None,
            "_nasl_div_announced": None,
            "auto_declared": False
        })
    save_holdings_file()
    st.session_state.add_success = f"Pridané: {t} ({format_qty(qty)})"
    st.session_state["add_ticker"] = ""
    st.session_state["add_qty"] = ""
    try:
        st.experimental_rerun()
    except:
        pass

# Layout / exchanges / add inputs
st.markdown('<div class="main-title">Dividend tracker</div>', unsafe_allow_html=True)

exchange_rows = get_exchange_rows()
cols_ex = ["Burza","Znacka","Mesto","Stat","Miestny cas","Stav"]
rows_render = []
for r in exchange_rows:
    rows_render.append({
        "Burza": r.get("Burza",""),
        "Znacka": r.get("Znacka",""),
        "Mesto": r.get("Mesto",""),
        "Stat": r.get("Stat",""),
        "Miestny cas": r.get("Miestny cas",""),
        "Stav": r.get("Stav",""),
        "color": r.get("color","black")
    })
def render_table(rows, columns):
    html = '<table class="compact-table"><tr>'
    for c in columns:
        html += f"<th>{c}</th>"
    html += "</tr>"
    for r in rows:
        color = r.get("color", "black")
        row_color = f"color:{color};"
        html += f"<tr style='{row_color}'>"
        for c in columns:
            val = r.get(c, "")
            html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</table>"
    return html
st.markdown(render_table(rows_render, cols_ex), unsafe_allow_html=True)
st.write("")

# add inputs
left_col, right_col = st.columns([0.5, 0.5])
with left_col:
    add_cols = st.columns([0.3,0.3,0.4])
    with add_cols[0]:
        st.text_input("", placeholder="Ticker", key="add_ticker", max_chars=20)
    with add_cols[1]:
        st.text_input("", placeholder="Množstvo", key="add_qty", max_chars=20, on_change=handle_add)
    with add_cols[2]:
        st.write("")
    if st.session_state.add_error:
        st.error(st.session_state.add_error)
    if st.session_state.add_success:
        st.success(st.session_state.add_success)
        st.session_state.add_success = ""
with right_col:
    st.write("")

# Helpers for ex-div detection
def extract_announced_from_raw(raw):
    keys = [
        "nextDividend", "nextDividendAmount", "nextDividendDate", "forwardDividendRate",
        "next_dividend", "upcomingDividend", "upcomingDividendAmount", "forwardAnnualDividendRate",
        "nextDividendYield", "trailingAnnualDividendRate"
    ]
    for k in keys:
        v = raw.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except:
            if isinstance(v, dict):
                for subk in ("amount","value","raw"):
                    if subk in v:
                        try:
                            return float(v[subk])
                        except:
                            pass
            s = str(v)
            m = re.search(r"([0-9]+[.,][0-9]+)", s)
            if m:
                try:
                    return float(m.group(1).replace(',','.'))
                except:
                    pass
    return None

def scrape_dividendmax_announced(ticker):
    try:
        url = f"https://www.dividendmax.com/stock/{ticker}"
        resp = requests.get(url, timeout=DIVIDENDMAX_TIMEOUT, headers={"User-Agent":"Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        m = re.search(r"Next\s+Dividend[:\s]*\$?([0-9]+[.,][0-9]+)", text, re.IGNORECASE)
        if not m:
            m = re.search(r"Next[:\s]*\$?([0-9]+[.,][0-9]+)", text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(',','.'))
        m2 = re.search(r"announc(ed|ement).*?([0-9]+[.,][0-9]+)", text, re.IGNORECASE)
        if m2:
            return float(m2.group(2).replace(',','.'))
    except:
        return None
    return None

def infer_frequency_label(divs_series):
    if divs_series is None or len(divs_series) == 0:
        return "Unknown"
    try:
        cutoff = datetime.now().date() - timedelta(days=365)
        try:
            recent = divs_series[divs_series.index.date >= cutoff]
            count = int(recent.count())
        except Exception:
            recent = divs_series[divs_series.index >= cutoff]
            count = int(recent.count())
        if count >= 10:
            return "Monthly"
        if 3 <= count <= 5:
            return "Quarterly"
        if count == 2:
            return "Semiannual"
        if count == 1:
            return "Yearly"
        total = int(divs_series.tail(8).count())
        if total >= 8:
            return "Monthly"
        if 3 <= total <= 5:
            return "Quarterly"
        if total == 2:
            return "Semiannual"
        if total == 1:
            return "Yearly"
        return "Irregular"
    except:
        return "Unknown"

# Refresh and compute announced dividend
today = datetime.now().date()
one_year_ago = today - timedelta(days=365)
for i, h in enumerate(st.session_state.holdings):
    try:
        info = fetch_ticker_info(h["ticker"])
        st.session_state.holdings[i]["name"] = info.get("name") or h.get("name")
        st.session_state.holdings[i]["price"] = info.get("price") or h.get("price")
        st.session_state.holdings[i]["currency"] = info.get("currency") or h.get("currency")
        st.session_state.holdings[i]["dividendRate"] = info.get("dividendRate")
        st.session_state.holdings[i]["dividendYield"] = info.get("dividendYield")
        st.session_state.holdings[i]["exDividendDate"] = info.get("exDividendDate")
        exch = info.get("exchange") or h.get("exchange")
        country = info.get("country") or h.get("exchange_country")
        if exch:
            ex_sym, ex_city, ex_country = infer_exchange_info(h["ticker"], info)
            if ex_sym:
                st.session_state.holdings[i]["exchange"] = ex_sym
                st.session_state.holdings[i]["exchange_city"] = ex_city
                st.session_state.holdings[i]["exchange_country"] = ex_country
            else:
                st.session_state.holdings[i]["exchange"] = exch
                st.session_state.holdings[i]["exchange_country"] = country
        if info.get("exDividendDate") and info.get("exDividendDate") > today:
            st.session_state.holdings[i]["auto_declared"] = True
            st.session_state.holdings[i]["declared"] = True
        divs = info.get("dividends_series")
        sum_last12 = None
        freq_label = "Unknown"
        last_paid = None
        if divs is not None and len(divs) > 0:
            try:
                try:
                    recent = divs[divs.index.date >= one_year_ago]
                except Exception:
                    recent = divs[divs.index >= one_year_ago]
                if recent is None or len(recent) == 0:
                    recent = divs.tail(12)
                sum_last12 = float(recent.sum()) if recent is not None else None
            except:
                sum_last12 = None
            freq_label = infer_frequency_label(divs)
            try:
                last_paid = float(divs.tail(1).iloc[0])
            except:
                last_paid = None
        st.session_state.holdings[i]["_sum_div_12m"] = sum_last12
        st.session_state.holdings[i]["_freq_label"] = freq_label
        st.session_state.holdings[i]["_next_div_auto"] = last_paid

        # announced dividend detection
        nasl = None
        if h.get("next_div") is not None:
            try:
                nasl = float(h.get("next_div"))
            except:
                nasl = None
        if nasl is None:
            raw = info.get("raw_info") or {}
            # try many keys
            nasl = None
            keys = [
                "nextDividend", "nextDividendAmount", "upcomingDividend", "upcomingDividendAmount",
                "forwardDividendRate", "forwardAnnualDividendRate", "next_dividend", "next_dividend_amount",
                "nextDividendYield"
            ]
            for k in keys:
                if nasl is not None:
                    break
                v = raw.get(k)
                if v is None:
                    continue
                try:
                    nasl = float(v)
                    break
                except:
                    s = str(v)
                    m = re.search(r"([0-9]+[.,][0-9]+)", s)
                    if m:
                        try:
                            nasl = float(m.group(1).replace(',','.'))
                            break
                        except:
                            pass
        if nasl is None:
            nasl = scrape_dividendmax_announced(h["ticker"])
        if nasl is None and last_paid is not None:
            nasl = last_paid
        st.session_state.holdings[i]["_nasl_div_announced"] = nasl
    except Exception:
        st.session_state.holdings[i]["_sum_div_12m"] = None
        st.session_state.holdings[i]["_freq_label"] = "Unknown"
        st.session_state.holdings[i]["_nasl_div_announced"] = None
        pass

# Build Ex-Dividend table with Nasl.Div, Nasl.Div[%], Div.Frek and Celk.Div
def parse_date_safe(s):
    try:
        return datetime.strptime(s, "%d/%m/%y")
    except:
        return datetime.max

ex_rows = []
for h in st.session_state.holdings:
    if not h.get("declared", False):
        continue
    ex_date = h.get("exDividendDate")
    if not ex_date:
        continue
    if ex_date <= today:
        continue
    qty = float(h.get("quantity", 0))
    price = h.get("price")
    currency = h.get("currency","")
    sum_div_12m = h.get("_sum_div_12m")
    roc_pct = "-"
    roc_amt = "-"
    if sum_div_12m is not None and price:
        try:
            roc_pct = f"{(float(sum_div_12m)/float(price))*100:.2f} %"
            roc_amt = f"{float(sum_div_12m):.4g} {currency}"
        except:
            roc_pct = "-"
            roc_amt = "-"
    else:
        annual_div = h.get("dividendRate")
        if annual_div is None and h.get("dividendYield") and price:
            try:
                annual_div = float(h.get("dividendYield")) * float(price)
            except:
                annual_div = None
        if annual_div is not None and price:
            try:
                roc_pct = f"{(float(annual_div)/float(price))*100:.2f} %"
                roc_amt = f"{float(annual_div):.4g} {currency}"
            except:
                roc_pct = "-"
                roc_amt = "-"
    nasl_val = None
    if h.get("next_div") is not None:
        try:
            nasl_val = float(h.get("next_div"))
        except:
            nasl_val = None
    if nasl_val is None:
        nasl_val = h.get("_nasl_div_announced")
    nasl_disp = "-"
    nasl_pct = "-"
    celk_disp = "-"
    if nasl_val is not None:
        try:
            nasl_disp = f"{float(nasl_val):.4g} {currency}" if currency else f"{float(nasl_val):.4g}"
        except:
            nasl_disp = str(nasl_val)
        if price:
            try:
                nasl_pct = f"{(float(nasl_val)/float(price))*100:.3f} %"
            except:
                nasl_pct = "-"
        try:
            total = float(nasl_val) * qty
            celk = f"{total:.4f}"
            celk = celk.rstrip('0').rstrip('.')
            celk_disp = f"{celk} {currency}" if currency else f"{celk}"
        except:
            celk_disp = "-"
    freq_label = h.get("_freq_label", "Unknown")
    ex_rows.append({
        "Ticker": h["ticker"],
        "Meno": h.get("name",""),
        "Mnozstvo": format_qty(h.get("quantity",0)),
        "Ex Div Date": ex_date.strftime("%d/%m/%y"),
        "Roc.Div[%]": roc_pct,
        "Roc.Div": roc_amt,
        "Div.Frek": freq_label,
        "Nasl.Div": nasl_disp,
        "Nasl.Div[%]": nasl_pct,
        "Celk.Div": celk_disp
    })

ex_rows = sorted(ex_rows, key=lambda r: parse_date_safe(r["Ex Div Date"]))

if len(ex_rows) == 0:
    st.info("Žiadne ohlásené (Declared) nasledujúce dividendy pre tvoje akcie.")
else:
    cols_exdiv = ["Ticker","Meno","Mnozstvo","Ex Div Date","Roc.Div[%]","Roc.Div","Div.Frek","Nasl.Div","Nasl.Div[%]","Celk.Div"]
    html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_exdiv) + '</tr>'
    for r in ex_rows:
        html += "<tr>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_exdiv) + "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

st.markdown('<div style="font-size:11px;color:#999">Poznámka: Nasl.Div sa hľadá prioritne: user value → yfinance raw_info → DividendMax scrape → fallback last paid. Div.Frek je odhad z histórie.</div>', unsafe_allow_html=True)
