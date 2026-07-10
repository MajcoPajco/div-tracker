import streamlit as st
import yfinance as yf
import pytz
from datetime import datetime, time, timedelta

st.set_page_config(page_title="Dividend tracker", layout="wide")

# CSS - kompaktná tabuľka bez medzier medzi riadkami
st.markdown("""
<style>
.main-title { font-size:12px; font-weight:600; margin-bottom:6px; }
.compact-table { background: white; border-collapse: collapse; width: 100%; font-size:13px; }
.compact-table th, .compact-table td { padding:6px 8px; border-bottom: 1px solid #eee; text-align:left; white-space: nowrap; }
.compact-table tr { height: 28px; }
.compact-table tbody tr { margin: 0; }
input[placeholder="Ticker"] { max-width:190px !important; width:190px !important; height:30px !important; }
input[placeholder="Množstvo"] { max-width:190px !important; width:190px !important; height:30px !important; }
.stButton>button { margin-top: 0.2rem; padding: .35rem .6rem; font-size:13px; }
</style>
""", unsafe_allow_html=True)

# Exchanges mapping for suffix fallback and common names -> (symbol, city, country)
SUFFIX_MAP = {
    "L": ("LSE","London","UK"),
    "PA": ("Euronext (Paris)","Paris","France"),
    "DE": ("XETRA (Frankfurt)","Frankfurt","Germany"),
    "F": ("XETRA (Frankfurt)","Frankfurt","Germany"),
    "HK": ("HKEX","Hong Kong","Hong Kong"),
    "SS": ("SSE (Shanghai)","Shanghai","China"),
    "SZ": ("SSE (Shenzhen)","Shenzhen","China"),
    "TO": ("TSX","Toronto","Canada"),
    "T": ("TSE (Tokyo)","Tokyo","Japan"),
    "AX": ("ASX","Sydney","Australia"),
    "KS": ("KRX","Seoul","South Korea"),
    "SI": ("SIX","Zurich","Switzerland")
}

EXCHANGES = [
    {"name":"NYSE","city":"New York","country":"USA","tz":"America/New_York","open":time(9,30),"close":time(16,0)},
    {"name":"NASDAQ","city":"New York","country":"USA","tz":"America/New_York","open":time(9,30),"close":time(16,0)},
    {"name":"LSE","city":"London","country":"UK","tz":"Europe/London","open":time(8,0),"close":time(16,30)},
    {"name":"Euronext (Paris)","city":"Paris","country":"France","tz":"Europe/Paris","open":time(9,0),"close":time(17,30)},
    {"name":"XETRA (Frankfurt)","city":"Frankfurt","country":"Germany","tz":"Europe/Berlin","open":time(9,0),"close":time(17,30)},
    {"name":"TSE (Tokyo)","city":"Tokyo","country":"Japan","tz":"Asia/Tokyo","open":time(9,0),"close":time(15,0)},
    {"name":"HKEX","city":"Hong Kong","country":"Hong Kong","tz":"Asia/Hong_Kong","open":time(9,30),"close":time(16,0)},
    {"name":"SSE (Shanghai)","city":"Shanghai","country":"China","tz":"Asia/Shanghai","open":time(9,30),"close":time(15,0)}
]
BRATISLAVA_TZ = pytz.timezone("Europe/Bratislava")

def format_timedelta(td):
    if not td:
        return ""
    if td.total_seconds() < 0:
        td = -td
    total = int(td.total_seconds())
    hrs = total // 3600
    mins = (total % 3600) // 60
    return f"{hrs}h {mins}min"

def get_exchange_rows():
    rows=[]
    for ex in EXCHANGES:
        tzloc = pytz.timezone(ex["tz"])
        now_local = datetime.now(tzloc)
        today = now_local.date()
        if now_local.weekday() >= 5:
            nxt = today
            while nxt.weekday() >= 5:
                nxt += timedelta(days=1)
            next_open = tzloc.localize(datetime.combine(nxt, ex["open"]))
            diff = next_open.astimezone(BRATISLAVA_TZ) - datetime.now(BRATISLAVA_TZ)
            display = f"Opens in {format_timedelta(diff)}"
            color="red"
        else:
            open_dt = tzloc.localize(datetime.combine(today, ex["open"]))
            close_dt = tzloc.localize(datetime.combine(today, ex["close"]))
            if open_dt <= now_local <= close_dt:
                display = f"Open {format_timedelta(now_local - open_dt)}"
                color="green"
            else:
                if now_local < open_dt:
                    next_open = open_dt
                else:
                    nxt = today + timedelta(days=1)
                    while nxt.weekday() >= 5:
                        nxt += timedelta(days=1)
                    next_open = tzloc.localize(datetime.combine(nxt, ex["open"]))
                diff = next_open.astimezone(BRATISLAVA_TZ) - datetime.now(BRATISLAVA_TZ)
                display = f"Opens in {format_timedelta(diff)}"
                color="red"
        local_now = datetime.now(tzloc).strftime("%H:%M")
        rows.append({"Burza": ex["name"], "Mesto": ex["city"], "Stat": ex["country"], "Miestny cas": local_now, "Stav": display, "color": color})
    return rows

st.markdown('<div class="main-title">Dividend tracker</div>', unsafe_allow_html=True)

# Exchanges table
exchange_rows = get_exchange_rows()
cols_ex = ["Burza","Mesto","Stat","Miestny cas","Stav"]
html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_ex) + '</tr>'
for r in exchange_rows:
    html += f"<tr style='color:{r.get('color','black')};'>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_ex) + "</tr>"
html += "</table>"
st.markdown(html, unsafe_allow_html=True)
st.write("")

# Session holdings
if "holdings" not in st.session_state:
    st.session_state.holdings = []

# messages
if "add_error" not in st.session_state:
    st.session_state.add_error = ""
if "add_success" not in st.session_state:
    st.session_state.add_success = ""

@st.cache_data(ttl=300)
def fetch_ticker_info(ticker):
    ticker = ticker.upper()
    tk = yf.Ticker(ticker)
    info = {}
    try:
        info = tk.info or {}
    except:
        info = {}
    # validity check
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
    # exDividendDate
    exDate = info.get("exDividendDate")
    ex_dt = None
    if exDate:
        try:
            ex_dt = datetime.fromtimestamp(int(exDate)).date()
        except:
            ex_dt = None
    # exchange info
    exch = info.get("exchange") or info.get("exchangeShortName") or info.get("market")
    country = info.get("country")
    exch_symbol = exch if exch else None
    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "price": price,
        "currency": info.get("currency",""),
        "dividendRate": info.get("dividendRate") or info.get("trailingAnnualDividendRate"),
        "dividendYield": info.get("dividendYield"),
        "exDividendDate": ex_dt,
        "dividends_series": (tk.dividends if hasattr(tk, "dividends") else None),
        "valid": valid,
        "exchange": exch_symbol,
        "country": country
    }

def infer_exchange_info(ticker, info):
    # prefer explicit info from yfinance
    exch = info.get("exchange")
    country = info.get("country")
    if exch:
        ex_l = exch.lower()
        if "nasdaq" in ex_l or "nms" in ex_l:
            return ("NASDAQ","New York","USA")
        if "nyse" in ex_l or "new york" in ex_l:
            return ("NYSE","New York","USA")
        if "lse" in ex_l or "london" in ex_l:
            return ("LSE","London","UK")
        if "paris" in ex_l or "euronext" in ex_l:
            return ("Euronext (Paris)","Paris","France")
        if "xetra" in ex_l or "frankfurt" in ex_l or "de" in ex_l:
            return ("XETRA (Frankfurt)","Frankfurt","Germany")
        if "hkex" in ex_l or "hong kong" in ex_l:
            return ("HKEX","Hong Kong","Hong Kong")
        if "jpx" in ex_l or "tse" in ex_l or "tokyo" in ex_l:
            return ("TSE (Tokyo)","Tokyo","Japan")
        # fallback using country if present
        if country:
            return (exch if exch else "-", "-", country)
    # fallback: use ticker suffix
    if "." in ticker:
        suf = ticker.split(".")[-1].upper()
        if suf in SUFFIX_MAP:
            return SUFFIX_MAP[suf]
    # unknown
    return ("","", "")

def format_qty(q):
    try:
        qf = float(q)
    except:
        return str(q)
    s = f"{qf:.4f}"
    s = s.rstrip('0').rstrip('.')
    return s

# add handler (enter in Množstvo)
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
    # merge or append
    found = False
    for h in st.session_state.holdings:
        if h["ticker"] == info["ticker"]:
            h["quantity"] = float(h.get("quantity",0.0)) + float(qty)
            # update meta
            h["name"] = info.get("name") or h.get("name")
            h["price"] = info.get("price") or h.get("price")
            h["currency"] = info.get("currency") or h.get("currency")
            h["dividendRate"] = info.get("dividendRate")
            h["dividendYield"] = info.get("dividendYield")
            if info.get("exDividendDate"):
                h["exDividendDate"] = info.get("exDividendDate")
            found = True
            break
    if not found:
        exch_sym, exch_city, exch_country = infer_exchange_info(t, info)
        st.session_state.holdings.append({
            "ticker": info["ticker"],
            "name": info["name"],
            "exchange": exch_sym,
            "exchange_city": exch_city,
            "exchange_country": exch_country,
            "price": info["price"],
            "currency": info["currency"],
            "quantity": float(qty),
            "dividendRate": info["dividendRate"],
            "dividendYield": info["dividendYield"],
            "exDividendDate": info["exDividendDate"],
            "declared": False,
            "next_div": None,
            "auto_declared": False
        })
    # if merged, ensure exchange info present/updated
    for h in st.session_state.holdings:
        if h["ticker"] == t and ("exchange" not in h or not h.get("exchange")):
            exch_sym, exch_city, exch_country = infer_exchange_info(t, info)
            h["exchange"] = exch_sym
            h["exchange_city"] = exch_city
            h["exchange_country"] = exch_country
    st.session_state.add_success = f"Pridané: {t} ({format_qty(qty)})"
    st.session_state["add_ticker"] = ""
    st.session_state["add_qty"] = ""
    try:
        st.experimental_rerun()
    except:
        pass

# layout: left add inputs only
left_col, right_col = st.columns([0.5, 0.5])
with left_col:
    add_row_cols = st.columns([0.3,0.3,0.4])
    with add_row_cols[0]:
        st.text_input("", placeholder="Ticker", key="add_ticker", max_chars=10)
    with add_row_cols[1]:
        st.text_input("", placeholder="Množstvo", key="add_qty", max_chars=10, on_change=handle_add)
    with add_row_cols[2]:
        st.write("")
    if st.session_state.add_error:
        st.error(st.session_state.add_error)
    if st.session_state.add_success:
        st.success(st.session_state.add_success)
        st.session_state.add_success = ""

with right_col:
    st.write("")

# refresh metadata and set exchange info where possible
today = datetime.now().date()
for i,h in enumerate(st.session_state.holdings):
    try:
        info = fetch_ticker_info(h["ticker"])
        st.session_state.holdings[i]["price"] = info.get("price") or h.get("price")
        st.session_state.holdings[i]["currency"] = info.get("currency") or h.get("currency")
        st.session_state.holdings[i]["name"] = info.get("name") or h.get("name")
        st.session_state.holdings[i]["dividendRate"] = info.get("dividendRate")
        st.session_state.holdings[i]["dividendYield"] = info.get("dividendYield")
        exinfo = info.get("exDividendDate")
        if exinfo and exinfo > today:
            st.session_state.holdings[i]["exDividendDate"] = exinfo
            st.session_state.holdings[i]["auto_declared"] = True
            st.session_state.holdings[i]["declared"] = True
        else:
            if exinfo:
                st.session_state.holdings[i]["exDividendDate"] = exinfo
        # ensure exchange info
        exch_sym, exch_city, exch_country = infer_exchange_info(h["ticker"], info)
        if exch_sym:
            st.session_state.holdings[i]["exchange"] = exch_sym
            st.session_state.holdings[i]["exchange_city"] = exch_city
            st.session_state.holdings[i]["exchange_country"] = exch_country
        # infer next div simple
        try:
            divs = info.get("dividends_series")
            if divs is not None and len(divs) > 0:
                last_div = float(divs.tail(1).iloc[0])
                st.session_state.holdings[i]["_next_div_auto"] = last_div
                st.session_state.holdings[i]["_freq_label"] = "From history"
            else:
                st.session_state.holdings[i]["_next_div_auto"] = None
                st.session_state.holdings[i]["_freq_label"] = "Unknown"
        except:
            st.session_state.holdings[i]["_next_div_auto"] = None
            st.session_state.holdings[i]["_freq_label"] = "Unknown"
    except:
        pass

# Build holdings HTML table: Ticker | Meno | Exchange | Mesto | Stat | Akt.Cena | Roc.Div[%] | Mnozstvo
hdr_cols = ["Ticker","Meno","Burza","Mesto","Štát","Akt.Cena","Roc.Div[%]","Množstvo"]
holdings_html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in hdr_cols) + '</tr>'
for h in st.session_state.holdings:
    ticker = h["ticker"]
    name = h.get("name","")
    exch = h.get("exchange","") or ""
    exch_city = h.get("exchange_city","") or ""
    exch_country = h.get("exchange_country","") or ""
    price = h.get("price")
    currency = h.get("currency","")
    # compute annual dividend percent
    annual_div = h.get("dividendRate")
    if annual_div is None and h.get("dividendYield") and price:
        try:
            annual_div = float(h.get("dividendYield")) * float(price)
        except:
            annual_div = None
    annual_pct = "-"
    if annual_div is not None and price:
        try:
            annual_pct = f"{(float(annual_div)/float(price))*100:.2f} %"
        except:
            annual_pct = "-"
    price_disp = f"{price} {currency}" if price is not None else f"- {currency}"
    qty_disp = format_qty(h.get("quantity",0))
    holdings_html += "<tr>"
    holdings_html += f"<td>{ticker}</td>"
    holdings_html += f"<td>{name}</td>"
    holdings_html += f"<td>{exch}</td>"
    holdings_html += f"<td>{exch_city}</td>"
    holdings_html += f"<td>{exch_country}</td>"
    holdings_html += f"<td>{price_disp}</td>"
    holdings_html += f"<td>{annual_pct}</td>"
    holdings_html += f"<td>{qty_disp}</td>"
    holdings_html += "</tr>"
holdings_html += "</table>"
st.markdown(holdings_html, unsafe_allow_html=True)

# Ex-Dividend table (same behavior as before)
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
    if not ex_date: continue
    if ex_date <= today:
        continue
    qty = h.get("quantity", 0)
    price = h.get("price")
    currency = h.get("currency","")
    annual_div = h.get("dividendRate")
    if annual_div is None and h.get("dividendYield") and price:
        try:
            annual_div = float(h.get("dividendYield")) * float(price)
        except:
            annual_div = None
    annual_pct = "-"
    if annual_div is not None and price:
        try:
            annual_pct = f"{(float(annual_div)/float(price))*100:.2f} %"
        except:
            annual_pct = "-"
    annual_disp = f"{float(annual_div):.4g} {currency}" if annual_div is not None else "-"
    nasl_val = h.get("next_div")
    if nasl_val is None and h.get("_next_div_auto") is not None:
        nasl_val = h.get("_next_div_auto")
    nasl_disp = f"{float(nasl_val):.4g} {currency}" if nasl_val is not None else "-"
    nasl_pct = "-"
    if nasl_val is not None and price:
        try:
            nasl_pct = f"{(float(nasl_val)/float(price))*100:.4f} %"
        except:
            nasl_pct = "-"
    freq_label = h.get("_freq_label", "Unknown")
    act_price = f"{price} {currency}" if price is not None else f"- {currency}"
    ex_rows.append({
        "Ticker": h["ticker"],
        "Meno": h.get("name",""),
        "Mnozstvo": f"{float(qty):.4g}",
        "Ex Div Date": ex_date.strftime("%d/%m/%y"),
        "Roc.Div[%]": annual_pct,
        "Roc.Div": annual_disp,
        "Div.Frek": freq_label,
        "Nasl.Div": nasl_disp,
        "Nasl.Div[%]": nasl_pct,
        "Akt.Cena": act_price
    })

ex_rows = sorted(ex_rows, key=lambda r: parse_date_safe(r["Ex Div Date"]))

if len(ex_rows) == 0:
    st.info("Žiadne ohlásené (Declared) nasledujúce dividendy pre tvoje akcie.")
else:
    cols_exdiv = ["Ticker","Meno","Mnozstvo","Ex Div Date","Roc.Div[%]","Roc.Div","Div.Frek","Nasl.Div","Nasl.Div[%]","Akt.Cena"]
    html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_exdiv) + '</tr>'
    for r in ex_rows:
        html += "<tr>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_exdiv) + "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

st.markdown('<div style="font-size:11px;color:#999">Poznámka: Burzu a miesto sa pokúšame zistiť z yfinance; ak chýba, použije sa dovetok tickera (napr. .L → London).</div>', unsafe_allow_html=True)
