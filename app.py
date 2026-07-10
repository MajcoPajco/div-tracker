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

# Exchanges
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

# Header
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

# Messages
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
    # validate by market price/history
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
    return {
        "ticker": ticker,
        "name": info.get("shortName") or info.get("longName") or ticker,
        "price": price,
        "currency": info.get("currency",""),
        "dividendRate": info.get("dividendRate") or info.get("trailingAnnualDividendRate"),
        "dividendYield": info.get("dividendYield"),
        "exDividendDate": ex_dt,
        "dividends_series": (tk.dividends if hasattr(tk, "dividends") else None),
        "valid": valid
    }

# Add handler (Enter in Množstvo triggers)
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
    st.session_state.add_success = f"Pridané: {t} ({qty})"
    st.session_state["add_ticker"] = ""
    st.session_state["add_qty"] = ""
    try:
        st.experimental_rerun()
    except:
        pass

# Layout: left block for add and edit, right block empty
left_col, right_col = st.columns([0.5, 0.5])

# Add inputs (no button) - Enter in Množstvo triggers handle_add
with left_col:
    add_row_cols = st.columns([0.3, 0.3, 0.4])
    with add_row_cols[0]:
        st.text_input("", placeholder="Ticker", key="add_ticker", max_chars=10)
    with add_row_cols[1]:
        st.text_input("", placeholder="Množstvo", key="add_qty", max_chars=10, on_change=handle_add)
    with add_row_cols[2]:
        st.write("")  # empty space

    # messages
    if st.session_state.add_error:
        st.error(st.session_state.add_error)
    if st.session_state.add_success:
        st.success(st.session_state.add_success)
        st.session_state.add_success = ""

    # EDIT form: select a ticker and set new quantity (pressed Enter or Submit saves)
    if len(st.session_state.holdings) > 0:
        st.markdown("**Upraviť množstvo (vyber ticker)**")
        edit_form = st.form("edit_qty_form")
        tickers = [h["ticker"] for h in st.session_state.holdings]
        sel = edit_form.selectbox("Ticker", options=tickers, key="edit_ticker_select")
        # find current quantity
        cur_qty = 0.0
        for h in st.session_state.holdings:
            if h["ticker"] == sel:
                cur_qty = h.get("quantity", 0.0)
                break
        edit_qty_input = edit_form.text_input("Nové množstvo", value=str(cur_qty), key="edit_qty_text", placeholder="napr. 1.2")
        edit_submitted = edit_form.form_submit_button("Uložiť")
        if edit_submitted:
            raw = edit_qty_input.strip()
            try:
                newq = float(raw.replace(',', '.'))
                # update holding
                for h in st.session_state.holdings:
                    if h["ticker"] == sel:
                        h["quantity"] = newq
                        break
                try:
                    st.experimental_rerun()
                except:
                    pass
            except:
                st.error("Neplatné množstvo pre úpravu")

with right_col:
    st.write("")  # keep empty as requested

# Refresh metadata for holdings (keeps auto-declare logic)
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
        # infer simple next div
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

# HOLDINGS - render compact HTML table (one row per ticker, no extra gaps)
holdings_html = '<table class="compact-table"><tr><th>Ticker</th><th>Meno</th><th>Akt.Cena</th><th>Množstvo</th></tr>'
for h in st.session_state.holdings:
    ticker = h["ticker"]
    name = h.get("name","")
    price = h.get("price")
    currency = h.get("currency","")
    price_disp = f"{price} {currency}" if price is not None else f"- {currency}"
    qty_disp = f"{h.get('quantity',0)}"
    holdings_html += f"<tr><td>{ticker}</td><td>{name}</td><td>{price_disp}</td><td>{qty_disp}</td></tr>"
holdings_html += "</table>"
st.markdown(holdings_html, unsafe_allow_html=True)

# Ex-Dividend table (unchanged behaviour)
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
    if ex_date <= today: continue
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

st.markdown('<div style="font-size:11px;color:#999">Poznámka: Držené akcie sú zobrazené kompaktne v tabuľke. Upraviť množstvo môžeš v ľavom bloku (vyber ticker a zadaj nové množstvo).</div>', unsafe_allow_html=True)
