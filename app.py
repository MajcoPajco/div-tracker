import streamlit as st
import yfinance as yf
import pytz
import pandas as pd
from datetime import datetime, time, timedelta

st.set_page_config(page_title="Dividend tracker", layout="wide")

# CSS kompaktné tabuľky
st.markdown("""
<style>
.main-title { font-size:12px; font-weight:600; margin-bottom:6px; }
.compact-table { background: white; border-collapse: collapse; width: 100%; font-size:13px; }
.compact-table th, .compact-table td { padding:6px 8px; border-bottom: 1px solid #eee; text-align:left; white-space: nowrap; }
.compact-table tr { height: 26px; }
</style>
""", unsafe_allow_html=True)

# Exchanges (konštanty)
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
    if td is None: return ""
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

# Header
st.markdown('<div class="main-title">Dividend tracker</div>', unsafe_allow_html=True)

# Exchanges table (hore)
ex_rows = get_exchange_rows()
cols_ex = ["Burza","Mesto","Stat","Miestny cas","Stav"]
html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_ex) + '</tr>'
for r in ex_rows:
    html += f"<tr style='color:{r.get('color','black')};'>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_ex) + "</tr>"
html += "</table>"
st.markdown(html, unsafe_allow_html=True)

st.write("")

# Session holdings
if "holdings" not in st.session_state:
    # each holding: ticker,name,price,currency,quantity,dividendRate,dividendYield,exDividendDate,declared(bool),next_div(user or auto),auto_declared(bool)
    st.session_state.holdings = []

# fetch info (cache short TTL so app refreshuje údaje automaticky)
@st.cache_data(ttl=300)
def fetch_ticker_info(ticker):
    ticker = ticker.upper()
    tk = yf.Ticker(ticker)
    info = {}
    try:
        info = tk.info or {}
    except Exception:
        info = {}
    # dividends series (may be empty)
    try:
        divs = tk.dividends  # pandas Series
    except Exception:
        divs = None
    # normalize fields
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
        except Exception:
            ex_dt = None
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "currency": currency,
        "dividendRate": dividendRate,
        "dividendYield": dividendYield,
        "exDividendDate": ex_dt,
        "dividends_series": divs
    }

# pomocné: odhad frekvencie a poslednej dividendy z histórie
def infer_freq_and_last(divs_series):
    if divs_series is None or len(divs_series) == 0:
        return None, None, "Unknown"
    # ensure index is DatetimeIndex
    try:
        idx_dates = divs_series.index
    except:
        return None, None, "Unknown"
    cutoff = datetime.now().date() - timedelta(days=365)
    recent = divs_series[divs_series.index.date >= cutoff]
    count = int(recent.count())
    if count == 0:
        # fallback to count last 8
        count = int(divs_series.tail(8).count())
        recent = divs_series.tail(8)
    last_div = float(divs_series.tail(1).iloc[0]) if len(divs_series) > 0 else None
    # label
    if count >= 10:
        label = "Monthly"
    elif 3 <= count <= 5:
        label = "Quarterly"
    elif count == 2:
        label = "Semiannual"
    elif count == 1:
        label = "Annual"
    elif count == 0:
        label = "Unknown"
    else:
        label = "Irregular"
    return count if count>0 else None, last_div, label

# Add form (single-line): ticker, qty (empty), button
c1,c2,c3 = st.columns([3,2,1])
with c1:
    new_ticker = st.text_input("Ticker", value="", key="input_ticker_small")
with c2:
    new_qty_text = st.text_input("Množstvo", value="", key="input_qty_small")
with c3:
    add_button = st.button("Pridať")

if add_button:
    t = new_ticker.strip().upper()
    try:
        qty = float(new_qty_text.strip()) if new_qty_text.strip() != "" else 0.0
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
                # update metadata
                h["name"] = info["name"] or h.get("name")
                h["price"] = info["price"] or h.get("price")
                h["currency"] = info["currency"] or h.get("currency")
                h["dividendRate"] = info["dividendRate"]
                h["dividendYield"] = info["dividendYield"]
                # update exDate if provided by info
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
                "declared": False,          # user-declared override
                "next_div": None,           # user provided next declared dividend
                "auto_declared": False      # auto flag set by system when yfinance exDate found
            })
        # clear inputs
        st.session_state["input_ticker_small"] = ""
        st.session_state["input_qty_small"] = ""
        try:
            st.experimental_rerun()
        except:
            pass

# Refresh metadata and apply automatic declared detection
today = datetime.now().date()
for i,h in enumerate(st.session_state.holdings):
    try:
        info = fetch_ticker_info(h["ticker"])
        st.session_state.holdings[i]["price"] = info.get("price") or h.get("price")
        st.session_state.holdings[i]["currency"] = info.get("currency") or h.get("currency")
        st.session_state.holdings[i]["name"] = info.get("name") or h.get("name")
        st.session_state.holdings[i]["dividendRate"] = info.get("dividendRate")
        st.session_state.holdings[i]["dividendYield"] = info.get("dividendYield")
        # update exDividendDate if yfinance provides future date
        exinfo = info.get("exDividendDate")
        if exinfo:
            # if exinfo in future, auto mark declared and set exDividendDate
            if exinfo > today:
                st.session_state.holdings[i]["exDividendDate"] = exinfo
                st.session_state.holdings[i]["auto_declared"] = True
                st.session_state.holdings[i]["declared"] = True
            else:
                # past ex dates aren't interesting for upcoming table: keep value but not declared auto
                st.session_state.holdings[i]["exDividendDate"] = exinfo
        # attempt to infer next_div_auto if user hasn't set next_div
        divs = info.get("dividends_series")
        freq_count, last_div, freq_label = infer_freq_and_last(divs)
        # compute next_div_auto
        next_div_auto = None
        if last_div is not None:
            next_div_auto = last_div
        else:
            annual = info.get("dividendRate")
            if annual is not None and freq_count:
                try:
                    next_div_auto = float(annual) / float(freq_count)
                except:
                    next_div_auto = None
        # store inferred metadata to holding (but do not overwrite user next_div)
        st.session_state.holdings[i]["_next_div_auto"] = next_div_auto
        st.session_state.holdings[i]["_freq_label"] = freq_label
    except Exception:
        pass

# Callback to save inline edits
def save_all():
    for idx, hh in enumerate(st.session_state.holdings):
        qk = f"qty_input_{idx}_{hh['ticker']}"
        dk = f"decl_{idx}_{hh['ticker']}"
        nk = f"nextdiv_{idx}_{hh['ticker']}"
        # quantity
        if qk in st.session_state:
            raw = st.session_state[qk]
            try:
                st.session_state.holdings[idx]["quantity"] = float(raw)
            except:
                pass
        # declared checkbox
        if dk in st.session_state:
            st.session_state.holdings[idx]["declared"] = bool(st.session_state[dk])
            # if user unchecks declared, do not clear auto_declared flag but excluded from ex-table until declared True
        # next declared dividend amount (user input)
        if nk in st.session_state:
            rawn = st.session_state[nk].strip()
            if rawn == "":
                st.session_state.holdings[idx]["next_div"] = None
            else:
                try:
                    st.session_state.holdings[idx]["next_div"] = float(rawn)
                except:
                    pass

# Render holdings compact table (editable inline)
st.markdown('<table class="compact-table"><tr><th>Ticker</th><th>Meno</th><th>Akt.Cena</th><th>Množstvo</th><th>Declared</th><th>Nasl.Div (user)</th><th></th></tr></table>', unsafe_allow_html=True)
for i,h in enumerate(st.session_state.holdings):
    ticker = h["ticker"]
    name = h.get("name","")
    price = h.get("price")
    currency = h.get("currency","")
    price_disp = f"{price} {currency}" if price is not None else f"- {currency}"
    cols = st.columns([1,5,2,1,1,1,1])
    cols[0].markdown(f"<div style='padding:6px 8px'>{ticker}</div>", unsafe_allow_html=True)
    cols[1].markdown(f"<div style='padding:6px 8px'>{name}</div>", unsafe_allow_html=True)
    cols[2].markdown(f"<div style='padding:6px 8px'>{price_disp}</div>", unsafe_allow_html=True)
    qkey = f"qty_input_{i}_{ticker}"
    dkey = f"decl_{i}_{ticker}"
    nkey = f"nextdiv_{i}_{ticker}"
    cols[3].text_input("", value=str(h.get("quantity",0)), key=qkey, on_change=save_all)
    cols[4].checkbox("", value=bool(h.get("declared",False)), key=dkey, on_change=save_all)
    # Nasl.Div user input (number in currency)
    cols[5].text_input("", value=(str(h.get("next_div")) if h.get("next_div") is not None else ""), key=nkey, on_change=save_all)
    if cols[6].button("Vymazať", key=f"del_{i}"):
        st.session_state.holdings.pop(i)
        try:
            st.experimental_rerun()
        except:
            pass

# Build Ex-Dividend table: include only holdings with declared True (user or auto) AND ex date in future
ex_rows = []
for h in st.session_state.holdings:
    # require declared True (either user or auto)
    if not h.get("declared", False):
        continue
    # pick ex date: prefer automatic exDividendDate known from yfinance, else the stored h['exDividendDate'] (could be None)
    ex_date = h.get("exDividendDate")
    if not ex_date:
        # no ex date known -> skip (we show only holdings that have ex date announced)
        continue
    # skip past dates (we only want future)
    if ex_date <= today:
        continue
    qty = h.get("quantity", 0)
    price = h.get("price")
    currency = h.get("currency","")
    # Nasl.Div precedence: user-provided next_div, else auto inferred _next_div_auto
    nasl_val = None
    if h.get("next_div") is not None:
        try:
            nasl_val = float(h.get("next_div"))
            source = "user"
        except:
            nasl_val = None
    if nasl_val is None and h.get("_next_div_auto") is not None:
        try:
            nasl_val = float(h.get("_next_div_auto"))
            source = "auto"
        except:
            nasl_val = None
    # Roc.Div (annual) prefer dividendRate
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

# sort by date ascending (closest/ex nearest first)
def parse_date_safe(s):
    try:
        return datetime.strptime(s, "%d/%m/%y")
    except:
        return datetime.max

ex_rows = sorted(ex_rows, key=lambda r: parse_date_safe(r["Ex Div Date"]))

# render ex-div table
if len(ex_rows) == 0:
    st.info("Žiadne ohlásené (Declared) nasledujúce dividendy pre tvoje akcie.")
else:
    cols_exdiv = ["Ticker","Meno","Mnozstvo","Ex Div Date","Roc.Div[%]","Roc.Div","Div.Frek","Nasl.Div","Nasl.Div[%]","Akt.Cena"]
    html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_exdiv) + '</tr>'
    for r in ex_rows:
        html += "<tr>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_exdiv) + "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

st.markdown('<div style="font-size:11px;color:#999">Poznámka: Aplikácia automaticky označí ako "Declared" tituly, pre ktoré yfinance poskytne budúci Ex‑Div dátum. Nasledujúca dividenda (Nasl.Div) je pokus o odhad z histórie (alebo môžeš zadať manuálne). Pre 100% spoľahlivosť "Declared" statusu a oficiálnych sum je potrebné zdroj s oficiálnymi oznámeniami (externé API).</div>', unsafe_allow_html=True)
