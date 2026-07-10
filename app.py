import streamlit as st
import yfinance as yf
import pytz
from datetime import datetime, time, timedelta

st.set_page_config(page_title="Dividend tracker", layout="wide")

# CSS: kompaktné tabuľky + úzke add polia (približne 5cm = ~190px)
st.markdown("""
<style>
.main-title { font-size:12px; font-weight:600; margin-bottom:6px; }
.compact-table { background: white; border-collapse: collapse; width: 100%; font-size:13px; }
.compact-table th, .compact-table td { padding:6px 8px; border-bottom: 1px solid #eee; text-align:left; white-space: nowrap; }
.compact-table tr { height: 28px; }

/* cieľame polia podľa placeholderu - tieto sú krátke ~190px (~5cm) */
input[placeholder="AddTicker"] {
  max-width: 190px !important;
  width: 190px !important;
  height: 30px !important;
  padding: 6px 8px !important;
}
input[placeholder="AddQty"] {
  max-width: 190px !important;
  width: 190px !important;
  height: 30px !important;
  padding: 6px 8px !important;
}

/* zmenšenie tlačidla a zarovnanie do riadku */
.stButton>button { margin-top: 0.2rem; padding: .35rem .6rem; font-size:13px; }
</style>
""", unsafe_allow_html=True)

# --- Exchanges (základ) ---
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
    if not td: return ""
    if td.total_seconds() < 0: td = -td
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
        rows.append({
            "Burza": ex["name"],
            "Mesto": ex["city"],
            "Stat": ex["country"],
            "Miestny cas": datetime.now(tzloc).strftime("%H:%M"),
            "Stav": display,
            "color": color
        })
    return rows

# Header small
st.markdown('<div class="main-title">Dividend tracker</div>', unsafe_allow_html=True)

# Exchanges section (top)
exchange_rows = get_exchange_rows()
cols_ex = ["Burza","Mesto","Stat","Miestny cas","Stav"]
html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_ex) + '</tr>'
for r in exchange_rows:
    html += f"<tr style='color:{r.get('color','black')};'>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_ex) + "</tr>"
html += "</table>"
st.markdown(html, unsafe_allow_html=True)
st.write("")

# --- Session state holdings ---
if "holdings" not in st.session_state:
    # holdings: list of dicts with ticker,name,price,currency,quantity,dividendRate,dividendYield,exDividendDate,declared,next_div,auto_declared,_next_div_auto,_freq_label
    st.session_state.holdings = []

@st.cache_data(ttl=300)
def fetch_ticker_info(ticker):
    ticker = ticker.upper()
    tk = yf.Ticker(ticker)
    try:
        info = tk.info or {}
    except:
        info = {}
    try:
        divs = tk.dividends
    except:
        divs = None
    name = info.get("shortName") or info.get("longName") or ticker
    price = info.get("regularMarketPrice")
    currency = info.get("currency","")
    dividendRate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
    dividendYield = info.get("dividendYield")
    exDate = info.get("exDividendDate")
    ex_dt = None
    if exDate:
        try:
            ex_dt = datetime.fromtimestamp(int(exDate)).date()
        except:
            ex_dt = None
    return {"ticker": ticker, "name": name, "price": price, "currency": currency,
            "dividendRate": dividendRate, "dividendYield": dividendYield,
            "exDividendDate": ex_dt, "dividends_series": divs}

# -------------------
# NEW: Redesigned add section (left-aligned, narrow fields ~5cm, button same row)
# -------------------
st.markdown("<div style='margin-top:6px; margin-bottom:6px;'></div>", unsafe_allow_html=True)

# container row: left part contains two narrow inputs side by side, right part the button
row_cols = st.columns([0.6, 0.2])  # left area for inputs, small right area for button
left = row_cols[0]
right = row_cols[1]

# inside left, make two small columns for the two inputs so they are on the same row and left-aligned
left_inputs = left.columns([0.5, 0.5])

# Use unique placeholders to target CSS widths above: "AddTicker" and "AddQty"
# Limit max_chars=10 as requested
add_ticker = left_inputs[0].text_input(label="", placeholder="AddTicker", key="add_ticker", max_chars=10)
add_qty = left_inputs[1].text_input(label="", placeholder="AddQty", key="add_qty", max_chars=10)

# Button placed in the right column but vertically aligned with inputs via CSS tweaks above
if right.button("Pridať"):
    t = (add_ticker or "").strip().upper()
    raw_qty = (add_qty or "").strip()
    # replace comma with dot for decimals
    try:
        qty = float(raw_qty.replace(',', '.')) if raw_qty != "" else None
    except:
        qty = None
    if t == "" or qty is None or qty <= 0:
        st.warning("Zadaj platný ticker a množstvo > 0")
    else:
        info = fetch_ticker_info(t)
        found = False
        for h in st.session_state.holdings:
            if h["ticker"] == info["ticker"]:
                h["quantity"] = float(h.get("quantity", 0.0)) + float(qty)
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
            st.session_state.holdings.append({
                "ticker": info["ticker"],
                "name": info["name"],
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
        # clear the add fields after successful addition
        st.session_state["add_ticker"] = ""
        st.session_state["add_qty"] = ""
        # rerun to update visible UI immediately
        try:
            st.experimental_rerun()
        except:
            pass

# -------------------
# Refresh metadata and auto-declared detection (kept)
# -------------------
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
        # infer simple _next_div_auto and _freq_label (best-effort) for use in ex table
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

# -------------------
# Callback to save inline edits (quantities, declared, next_div)
# -------------------
def save_all():
    for idx, hh in enumerate(st.session_state.holdings):
        qk = f"qty_input_{idx}_{hh['ticker']}"
        dk = f"decl_{idx}_{hh['ticker']}"
        nk = f"nextdiv_{idx}_{hh['ticker']}"
        if qk in st.session_state:
            raw = str(st.session_state[qk]).strip()
            try:
                val = float(raw.replace(',', '.'))
                st.session_state.holdings[idx]["quantity"] = val
            except:
                pass
        if dk in st.session_state:
            st.session_state.holdings[idx]["declared"] = bool(st.session_state[dk])
        if nk in st.session_state:
            rawn = str(st.session_state[nk]).strip()
            if rawn == "":
                st.session_state.holdings[idx]["next_div"] = None
            else:
                try:
                    st.session_state.holdings[idx]["next_div"] = float(rawn.replace(',', '.'))
                except:
                    pass

# -------------------
# Render holdings in aligned table form (one row per ticker)
# -------------------
col_widths = [1,5,2,1,1,2,1]
hdr = st.columns(col_widths)
hdr[0].markdown("**Ticker**")
hdr[1].markdown("**Meno**")
hdr[2].markdown("**Akt.Cena**")
hdr[3].markdown("**Množstvo**")
hdr[4].markdown("**Declared**")
hdr[5].markdown("**Nasl.Div (user)**")
hdr[6].markdown("")

for i, h in enumerate(st.session_state.holdings):
    ticker = h["ticker"]
    name = h.get("name","")
    price = h.get("price")
    currency = h.get("currency","")
    price_display = f"{price} {currency}" if price is not None else f"- {currency}"
    cols = st.columns(col_widths)
    cols[0].markdown(f"<div style='padding:6px 8px'>{ticker}</div>", unsafe_allow_html=True)
    cols[1].markdown(f"<div style='padding:6px 8px'>{name}</div>", unsafe_allow_html=True)
    cols[2].markdown(f"<div style='padding:6px 8px'>{price_display}</div>", unsafe_allow_html=True)
    qkey = f"qty_input_{i}_{ticker}"
    dkey = f"decl_{i}_{ticker}"
    nkey = f"nextdiv_{i}_{ticker}"
    cols[3].text_input("", value=str(h.get("quantity", 0)), key=qkey, on_change=save_all, max_chars=10)
    cols[4].checkbox("", value=bool(h.get("declared", False)), key=dkey, on_change=save_all)
    cols[5].text_input("", value=(str(h.get("next_div")) if h.get("next_div") is not None else ""), key=nkey, on_change=save_all, max_chars=10)
    if cols[6].button("Vymazať", key=f"del_{i}"):
        st.session_state
