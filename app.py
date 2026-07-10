import streamlit as st
import yfinance as yf
import pytz
from datetime import datetime, time, timedelta, date
from dateutil import tz
import math

st.set_page_config(page_title="Dividend tracker", layout="wide")

# --- CSS for compact white table and styles ---
st.markdown(
    """
    <style>
    .main-title {
        font-size:12px;
        font-weight:600;
        margin-bottom:6px;
    }
    .compact-table {
        background: white;
        border-collapse: collapse;
        width: 100%;
        font-size:13px;
    }
    .compact-table th, .compact-table td {
        padding:6px 8px;
        border-bottom: 1px solid #eee;
        text-align:left;
        white-space: nowrap;
    }
    .compact-table tr { height: 26px; }
    .no-gap > div { padding: 0; margin: 0; }
    .small-note { font-size:11px; color:#666; margin-bottom:6px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Exchange definitions ---
EXCHANGES = [
    {"name": "NYSE", "city": "New York", "country": "USA", "tz": "America/New_York", "open": time(9,30), "close": time(16,0)},
    {"name": "NASDAQ", "city": "New York", "country": "USA", "tz": "America/New_York", "open": time(9,30), "close": time(16,0)},
    {"name": "LSE", "city": "London", "country": "UK", "tz": "Europe/London", "open": time(8,0), "close": time(16,30)},
    {"name": "Euronext (Paris)", "city": "Paris", "country": "France", "tz": "Europe/Paris", "open": time(9,0), "close": time(17,30)},
    {"name": "XETRA (Frankfurt)", "city": "Frankfurt", "country": "Germany", "tz": "Europe/Berlin", "open": time(9,0), "close": time(17,30)},
    {"name": "TSE (Tokyo)", "city": "Tokyo", "country": "Japan", "tz": "Asia/Tokyo", "open": time(9,0), "close": time(15,0)},
    {"name": "HKEX", "city": "Hong Kong", "country": "Hong Kong", "tz": "Asia/Hong_Kong", "open": time(9,30), "close": time(16,0)},
    {"name": "SSE (Shanghai)", "city": "Shanghai", "country": "China", "tz": "Asia/Shanghai", "open": time(9,30), "close": time(15,0)},
]

BRATISLAVA_TZ = pytz.timezone("Europe/Bratislava")

def local_dt_for_day(tzname, d, t):
    tzloc = pytz.timezone(tzname)
    return tzloc.localize(datetime.combine(d, t))

def is_weekend_local(dt_local):
    return dt_local.weekday() >= 5  # 5=Saturday,6=Sunday

def next_open_datetime(tzname, open_time):
    tzloc = pytz.timezone(tzname)
    today_local = datetime.now(tzloc).date()
    candidate = today_local
    while True:
        if candidate.weekday() < 5:
            return tzloc.localize(datetime.combine(candidate, open_time))
        candidate = candidate + timedelta(days=1)

def format_timedelta(td):
    # return "Xh Ymin" (no leading zeros)
    if td is None:
        return ""
    # normalize negative to positive
    if td.total_seconds() < 0:
        td = -td
    total_seconds = int(td.total_seconds())
    hrs = total_seconds // 3600
    mins = (total_seconds % 3600) // 60
    return f"{hrs}h {mins}min"

def get_exchange_rows():
    rows = []
    for ex in EXCHANGES:
        tzname = ex["tz"]
        tzloc = pytz.timezone(tzname)
        now_local = datetime.now(tzloc)
        today = now_local.date()
        if is_weekend_local(now_local):
            next_open = next_open_datetime(tzname, ex["open"])
            next_open_bratislava = next_open.astimezone(BRATISLAVA_TZ)
            diff = next_open_bratislava - datetime.now(BRATISLAVA_TZ)
            status = "closed"
            display_time = f"Opens in {format_timedelta(diff)}"
            color = "red"
        else:
            open_dt = local_dt_for_day(tzname, today, ex["open"])
            close_dt = local_dt_for_day(tzname, today, ex["close"])
            if open_dt <= now_local <= close_dt:
                opened_since = now_local - open_dt
                display_time = f"Open {format_timedelta(opened_since)}"
                status = "open"
                color = "green"
            else:
                if now_local < open_dt:
                    next_open = open_dt
                else:
                    nxt = today + timedelta(days=1)
                    while nxt.weekday() >= 5:
                        nxt += timedelta(days=1)
                    next_open = local_dt_for_day(tzname, nxt, ex["open"])
                next_open_bratislava = next_open.astimezone(BRATISLAVA_TZ)
                diff = next_open_bratislava - datetime.now(BRATISLAVA_TZ)
                display_time = f"Opens in {format_timedelta(diff)}"
                status = "closed"
                color = "red"
        local_now_for_display = datetime.now(tzloc).strftime("%H:%M")
        rows.append({
            "Burza": ex["name"],
            "Mesto": ex["city"],
            "Stat": ex["country"],
            "Miestny cas": local_now_for_display,
            "Stav": display_time,
            "color": color
        })
    return rows

# --- Header ---
st.markdown('<div class="main-title">Dividend tracker</div>', unsafe_allow_html=True)

# Exchanges section (topmost)
exchange_rows = get_exchange_rows()

# Build HTML table for exchanges
def render_table(rows, columns, compact=True):
    html = '<table class="compact-table">'
    html += "<tr>"
    for c in columns:
        html += f"<th>{c}</th>"
    html += "</tr>"
    for r in rows:
        color = r.get("color", "black")
        row_color = "color:%s;" % color
        html += f"<tr style='{row_color}'>"
        for c in columns:
            val = r.get(c, "")
            html += f"<td>{val}</td>"
        html += "</tr>"
    html += "</table>"
    return html

cols_ex = ["Burza", "Mesto", "Stat", "Miestny cas", "Stav"]
st.markdown(render_table(exchange_rows, cols_ex), unsafe_allow_html=True)

st.write("")

# --- Holdings management in session state ---
if "holdings" not in st.session_state:
    st.session_state.holdings = []

@st.cache_data(ttl=60)
def fetch_ticker_info(ticker):
    ticker = ticker.upper()
    tk = yf.Ticker(ticker)
    info = {}
    try:
        data = tk.info
    except Exception:
        data = {}
    name = data.get("shortName") or data.get("longName") or ticker
    price = data.get("regularMarketPrice")
    currency = data.get("currency", "")
    dividendRate = data.get("dividendRate") or data.get("trailingAnnualDividendRate")
    dividendYield = data.get("dividendYield")
    exDividendDate = data.get("exDividendDate")
    ex_date = None
    if exDividendDate:
        try:
            ex_date = datetime.fromtimestamp(int(exDividendDate)).date()
        except Exception:
            ex_date = None
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "currency": currency,
        "dividendRate": dividendRate,
        "dividendYield": dividendYield,
        "exDividendDate": ex_date
    }

# Section 1: input for adding stock
st.markdown('<div class="small-note">Pridať akciu</div>', unsafe_allow_html=True)
col1, col2, col3, col4 = st.columns([2,1,1,1])
with col1:
    new_ticker = st.text_input("Ticker", value="", key="input_ticker")
with col2:
    new_qty = st.number_input("Množstvo", min_value=0.0, value=0.0, step=1.0, format="%.0f", key="input_qty")
with col3:
    add_button = st.button("Pridať")

if add_button:
    t = new_ticker.strip().upper()
    if t == "" or new_qty <= 0:
        st.warning("Zadaj platný ticker a množstvo > 0")
    else:
        info = fetch_ticker_info(t)
        st.session_state.holdings.append({
            "ticker": info["ticker"],
            "name": info["name"],
            "price": info["price"],
            "quantity": float(new_qty),
            "currency": info["currency"],
            "dividendRate": info["dividendRate"],
            "dividendYield": info["dividendYield"],
            "exDividendDate": info["exDividendDate"]
        })
        # pokus o rerun, ale necháme to bezpečne (ak st.experimental_rerun nie je dostupné, pokračujeme)
        try:
            st.experimental_rerun()
        except Exception:
            # fallback: lenient behavior - zobrazíme potvrdenie a vyčistíme inputy
            st.success(f"Pridané: {t}")
            st.session_state["input_ticker"] = ""
            st.session_state["input_qty"] = 0.0

# Section 2: held stocks
st.markdown('<div class="small-note">Držené akcie</div>', unsafe_allow_html=True)

if len(st.session_state.holdings) == 0:
    st.info("Žiadne držené akcie. Pridaj cez formulár vyššie.")
else:
    # Refresh prices for displayed holdings
    for i, h in enumerate(st.session_state.holdings):
        try:
            info = fetch_ticker_info(h["ticker"])
            st.session_state.holdings[i]["price"] = info["price"] or h.get("price")
            st.session_state.holdings[i]["currency"] = info["currency"] or h.get("currency")
            st.session_state.holdings[i]["name"] = info["name"] or h.get("name")
            st.session_state.holdings[i]["dividendRate"] = info["dividendRate"]
            st.session_state.holdings[i]["dividendYield"] = info["dividendYield"]
            st.session_state.holdings[i]["exDividendDate"] = info["exDividendDate"]
        except Exception:
            pass

    st.markdown('<table class="compact-table"><tr><th>Ticker</th><th>Meno Firmy</th><th>Aktuálna cena</th><th>Množstvo vlastnených akcií</th></tr></table>', unsafe_allow_html=True)
    for i, h in enumerate(st.session_state.holdings):
        ticker = h["ticker"]
        name = h.get("name", "")
        price = h.get("price")
        currency = h.get("currency", "")
        display_price = f"{price} {currency}" if price is not None else f"- {currency}"
        rcols = st.columns([1,4,2,2])
        rcols[0].markdown(f"<div style='padding:6px 8px'>{ticker}</div>", unsafe_allow_html=True)
        rcols[1].markdown(f"<div style='padding:6px 8px'>{name}</div>", unsafe_allow_html=True)
        rcols[2].markdown(f"<div style='padding:6px 8px'>{display_price}</div>", unsafe_allow_html=True)
        key = f"qty_{i}_{ticker}"
        new_q = rcols[3].number_input("", min_value=0.0, value=float(h.get("quantity", 0.0)), step=1.0, format="%.0f", key=key)
        if rcols[3].button("Vymazať", key=f"del_{i}"):
            st.session_state.holdings.pop(i)
            try:
                st.experimental_rerun()
            except Exception:
                pass

    if st.button("Uložiť množstvá"):
        for i in range(len(st.session_state.holdings)):
            k = f"qty_{i}_{st.session_state.holdings[i]['ticker']}"
            if k in st.session_state:
                st.session_state.holdings[i]["quantity"] = float(st.session_state[k])
        st.success("Uložené")
        try:
            st.experimental_rerun()
        except Exception:
            pass

# Section 3: upcoming ex-dividend dates
st.markdown('<div class="small-note">Najbližšie Ex-Dividend dátumy (pre moje akcie)</div>', unsafe_allow_html=True)

ex_rows = []
for h in st.session_state.holdings:
    ex_date = h.get("exDividendDate")
    if ex_date:
        qty = h.get("quantity", 0)
        price = h.get("price")
        div_per_share = h.get("dividendRate")
        div_yield = h.get("dividendYield")
        currency = h.get("currency", "")
        if div_per_share is None and div_yield and price:
            try:
                div_per_share = float(div_yield) * float(price)
            except Exception:
                div_per_share = None
        pct_announced = ""
        if div_per_share and price:
            try:
                pct_announced = f"{(float(div_per_share)/float(price))*100:.2f} %"
            except Exception:
                pct_announced = ""
        pct_annual = f"{(float(div_yield)*100):.2f} %" if div_yield else ""
        expected = f"{(float(div_per_share)*qty):.2f} {currency}" if div_per_share is not None else ""
        ex_rows.append({
            "Ticker": h["ticker"],
            "Meno": h.get("name",""),
            "Mnozstvo": f"{int(qty)} {currency}",
            "Ex Div Date": ex_date.strftime("%d/%m/%y"),
            "Ohlasena dividenda na akciu": f"{div_per_share:.4g} {currency}" if div_per_share is not None else "-",
            "% Ohlasena dividenda k aktualnej cene akcie": pct_announced,
            "% Rocnej dividendy": pct_annual,
            "Ocakavany vynos pre moje akcie": expected
        })

ex_rows = sorted(ex_rows, key=lambda r: datetime.strptime(r["Ex Div Date"], "%d/%m/%y") if r else datetime.max)

if len(ex_rows) == 0:
    st.info("Žiadne nadchádzajúce ex-dividend dátumy pre tvoje akcie.")
else:
    cols_exdiv = ["Ticker","Meno","Mnozstvo","Ex Div Date","Ohlasena dividenda na akciu","% Ohlasena dividenda k aktualnej cene akcie","% Rocnej dividendy","Ocakavany vynos pre moje akcie"]
    html = '<table class="compact-table"><tr>'
    for c in cols_exdiv:
        html += f"<th>{c}</th>"
    html += "</tr>"
    for r in ex_rows:
        html += "<tr>"
        for c in cols_exdiv:
            html += f"<td>{r.get(c,'')}</td>"
        html += "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

st.write("")
st.markdown('<div style="font-size:11px;color:#999">Poznámka: údaje sú načítané cez yfinance. Časy burz sú orientačné (bez zohľadnenia špeciálnych dní a sviatkov).</div>', unsafe_allow_html=True)
