import streamlit as st
import yfinance as yf
import pytz
import json
from pathlib import Path
from datetime import datetime, time, timedelta

st.set_page_config(page_title="Dividend tracker", layout="wide")

# ----------------- Config -----------------
HOLDINGS_FILE = Path("holdings.json")
FETCH_TTL = 60  # seconds for caching yfinance results

# ----------------- CSS -----------------
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

# ----------------- Helpers: persist only user fields -----------------
def save_holdings_file():
    try:
        to_save = []
        for h in st.session_state.holdings:
            item = {
                "ticker": h.get("ticker"),
                "quantity": h.get("quantity", 0)
            }
            # if user-managed fields exist, persist them too
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
            # quantity persisted
            "quantity": item.get("quantity", 0),
            # preserve user fields if present, else defaults
            "declared": bool(item.get("declared", False)),
            "next_div": item.get("next_div", None),
            # runtime-only fields (will be filled from yfinance)
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

# ----------------- yfinance fetch (runtime fields only) -----------------
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
        "exchange": exch,
        "country": country
    }

# simple suffix map for exchange inference (extend as needed)
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
            return ("Euronext (Paris)","Paris","France")
        if "frankfurt" in ex_l or "xetra" in ex_l:
            return ("XETRA (Frankfurt)","Frankfurt","Germany")
        if "hong" in ex_l or "hkex" in ex_l:
            return ("HKEX","Hong Kong","Hong Kong")
        if "tokyo" in ex_l or "tse" in ex_l or "jpx" in ex_l:
            return ("TSE (Tokyo)","Tokyo","Japan")
        if country:
            return (exch, "", country)
    if "." in ticker:
        suf = ticker.split(".")[-1].upper()
        if suf in SUFFIX_MAP:
            return SUFFIX_MAP[suf]
    return ("", "", "")

# ----------------- Init session -----------------
if "holdings" not in st.session_state:
    st.session_state.holdings = load_holdings_file()

if "add_error" not in st.session_state:
    st.session_state.add_error = ""
if "add_success" not in st.session_state:
    st.session_state.add_success = ""

# ----------------- Add handler -----------------
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
            # persisted user fields:
            "declared": False,
            "next_div": None,
            # runtime-only fields (start empty; will be filled below)
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
            "auto_declared": False
        })
    # persist only user fields (ticker + quantity + declared/next_div)
    save_holdings_file()
    st.session_state.add_success = f"Pridané: {t} ({format_qty(qty)})"
    st.session_state["add_ticker"] = ""
    st.session_state["add_qty"] = ""
    try:
        st.experimental_rerun()
    except:
        pass

# ----------------- Layout: exchanges top (compact) -----------------
st.markdown('<div class="main-title">Dividend tracker</div>', unsafe_allow_html=True)

# small exchanges list (kept minimal)
EXCHANGES_SIMPLE = [
    {"name":"NYSE","city":"New York","country":"USA","tz":"America/New_York","open":time(9,30),"close":time(16,0)},
    {"name":"NASDAQ","city":"New York","country":"USA","tz":"America/New_York","open":time(9,30),"close":time(16,0)},
    {"name":"LSE","city":"London","country":"UK","tz":"Europe/London","open":time(8,0),"close":time(16,30)},
]
rows = []
for ex in EXCHANGES_SIMPLE:
    rows.append({"Burza": ex["name"], "Mesto": ex["city"], "Stat": ex["country"], "Miestny cas": datetime.now(pytz.timezone(ex["tz"])).strftime("%H:%M"), "Stav": ""})
cols_ex = ["Burza","Mesto","Stat","Miestny cas","Stav"]
html_ex = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in cols_ex) + '</tr>'
for r in rows:
    html_ex += "<tr>" + ''.join(f"<td>{r.get(c,'')}</td>" for c in cols_ex) + "</tr>"
html_ex += "</table>"
st.markdown(html_ex, unsafe_allow_html=True)
st.write("")

# ----------------- Add inputs (left) -----------------
left_col, right_col = st.columns([0.5, 0.5])
with left_col:
    add_cols = st.columns([0.3,0.3,0.4])
    with add_cols[0]:
        st.text_input("", placeholder="Ticker", key="add_ticker", max_chars=10)
    with add_cols[1]:
        st.text_input("", placeholder="Množstvo", key="add_qty", max_chars=10, on_change=handle_add)
    with add_cols[2]:
        st.write("")
    if st.session_state.add_error:
        st.error(st.session_state.add_error)
    if st.session_state.add_success:
        st.success(st.session_state.add_success)
        st.session_state.add_success = ""

with right_col:
    st.write("")

# ----------------- Refresh runtime fields from internet -----------------
today = datetime.now().date()
for i, h in enumerate(st.session_state.holdings):
    try:
        info = fetch_ticker_info(h["ticker"])
        # update runtime-only fields from internet (do NOT save these to file)
        st.session_state.holdings[i]["name"] = info.get("name") or h.get("name")
        st.session_state.holdings[i]["price"] = info.get("price") or h.get("price")
        st.session_state.holdings[i]["currency"] = info.get("currency") or h.get("currency")
        st.session_state.holdings[i]["dividendRate"] = info.get("dividendRate")
        st.session_state.holdings[i]["dividendYield"] = info.get("dividendYield")
        st.session_state.holdings[i]["exDividendDate"] = info.get("exDividendDate")
        # exchange/country from yfinance preferred
        exch_sym = info.get("exchange") or h.get("exchange")
        country = info.get("country") or h.get("exchange_country")
        if exch_sym:
            # infer nicer labels
            ex_sym, ex_city, ex_country = infer_exchange_info(h["ticker"], info)
            if ex_sym:
                st.session_state.holdings[i]["exchange"] = ex_sym
                st.session_state.holdings[i]["exchange_city"] = ex_city
                st.session_state.holdings[i]["exchange_country"] = ex_country
            else:
                st.session_state.holdings[i]["exchange"] = exch_sym
                st.session_state.holdings[i]["exchange_country"] = country
        # auto-declared detection
        if info.get("exDividendDate") and info.get("exDividendDate") > today:
            st.session_state.holdings[i]["auto_declared"] = True
            st.session_state.holdings[i]["declared"] = True
        # infer next_div from history (runtime only)
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
    except Exception:
        # keep existing runtime values if fetch fails
        pass

# ----------------- Build holdings table (compact) -----------------
# Desired order: Ticker | Meno | Burza | Štát | Akt.Cena | Množstvo | Roc.Div[%]
hdr_cols = ["Ticker","Meno","Burza","Štát","Akt.Cena","Množstvo","Roc.Div[%]"]
holdings_html = '<table class="compact-table"><tr>' + ''.join(f"<th>{c}</th>" for c in hdr_cols) + '</tr>'
for h in st.session_state.holdings:
    ticker = h.get("ticker","")
    name = h.get("name","") or ""
    exch = h.get("exchange","") or ""
    exch_country = h.get("exchange_country","") or ""
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
    price_disp = f"{price} {currency}" if price is not None else f"- {currency}"
    qty_disp = format_qty(h.get("quantity",0))
    holdings_html += "<tr>"
    holdings_html += f"<td>{ticker}</td>"
    holdings_html += f"<td>{name}</td>"
    holdings_html += f"<td>{exch}</td>"
    holdings_html += f"<td>{exch_country}</td>"
    holdings_html += f"<td>{price_disp}</td>"
    holdings_html += f"<td>{qty_disp}</td>"
    holdings_html += f"<td>{annual_pct}</td>"
    holdings_html += "</tr>"
holdings_html += "</table>"
st.markdown(holdings_html, unsafe_allow_html=True)

# ----------------- Ex-Dividend section (same logic) -----------------
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

st.markdown('<div style="font-size:11px;color:#999">Poznámka: name/price/exDate/exchange/dividend údaje sa dynamicky aktualizujú z internetu (yfinance) a nie sú ukladané do holdings.json. Uložia sa len ticker a množstvo (a voliteľné user polia declared/next_div).</div>', unsafe_allow_html=True)
