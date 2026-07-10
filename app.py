import streamlit as st
import datetime
import pytz
import textwrap # Stále ho necháme, aj keď ho priamo nepoužijeme na final_html_table, môže byť užitočný inde.

# --- Konfigurácia Streamlit stránky ---
st.set_page_config(
    page_title="Dividend Tracker",
    layout="wide", # Široké rozloženie pre lepšiu kompaktnosť
    initial_sidebar_state="collapsed" # Skryje bočný panel
)

# --- Konštanty ---
BRATISLAVA_TZ = pytz.timezone('Europe/Bratislava')

# Zoznam búrz s ich detailmi
EXCHANGES = [
    {"name": "NYSE", "city": "New York", "country": "USA", "timezone_str": "America/New_York", "open_h": 9, "open_m": 30, "close_h": 16, "close_m": 0},
    {"name": "NASDAQ", "city": "New York", "country": "USA", "timezone_str": "America/New_York", "open_h": 9, "open_m": 30, "close_h": 16, "close_m": 0},
    {"name": "LSE", "city": "London", "country": "UK", "timezone_str": "Europe/London", "open_h": 8, "open_m": 0, "close_h": 16, "close_m": 30},
    {"name": "Euronext Paris", "city": "Paríž", "country": "Francúzsko", "timezone_str": "Europe/Paris", "open_h": 9, "open_m": 0, "close_h": 17, "close_m": 30},
    {"name": "Xetra (Frankfurt)", "city": "Frankfurt", "country": "Nemecko", "timezone_str": "Europe/Berlin", "open_h": 9, "open_m": 0, "close_h": 17, "close_m": 30},
    {"name": "TSE (Tokio)", "city": "Tokio", "country": "Japonsko", "timezone_str": "Asia/Tokyo", "open_h": 9, "open_m": 0, "close_h": 15, "close_m": 0},
    {"name": "SSE (Šanghaj)", "city": "Šanghaj", "country": "Čína", "timezone_str": "Asia/Shanghai", "open_h": 9, "open_m": 30, "close_h": 15, "close_m": 0},
    {"name": "ASX (Sydney)", "city": "Sydney", "country": "Austrália", "timezone_str": "Australia/Sydney", "open_h": 10, "open_m": 0, "close_h": 16, "close_m": 0},
    {"name": "TSX (Toronto)", "city": "Toronto", "country": "Kanada", "timezone_str": "America/Toronto", "open_h": 9, "open_m": 30, "close_h": 16, "close_m": 0},
    {"name": "BSE (Bombaj)", "city": "Bombaj", "country": "India", "timezone_str": "Asia/Kolkata", "open_h": 9, "open_m": 15, "close_h": 15, "close_m": 30},
]

# --- Pomocné funkcie ---
def format_timedelta_to_hm(td: datetime.timedelta):
    """Formátuje timedelta na reťazec 'Xh Ym'."""
    total_seconds = int(td.total_seconds())
    is_negative = total_seconds < 0
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes}m", is_negative

def get_exchange_status(exchange_data, current_utc_time):
    """
    Vypočíta stav burzy (otvorená/zatvorená), miestny čas a časový rozdiel.
    """
    exchange_tz = pytz.timezone(exchange_data['timezone_str'])
    local_time = current_utc_time.astimezone(exchange_tz)

    local_time_str = local_time.strftime("%H:%M:%S")

    open_time_today = local_time.replace(hour=exchange_data['open_h'], minute=exchange_data['open_m'], second=0, microsecond=0)
    close_time_today = local_time.replace(hour=exchange_data['close_h'], minute=exchange_data['close_m'], second=0, microsecond=0)

    status_str = ""
    color_class = "red-text"

    # Kontrola, či je obchodný deň (pondelok-piatok)
    if local_time.weekday() >= 5: # Sobota alebo nedeľa
        days_to_monday = (7 - local_time.weekday()) % 7
        next_open_time = open_time_today + datetime.timedelta(days=days_to_monday)
        time_to_open = next_open_time - local_time
        formatted_diff, _ = format_timedelta_to_hm(time_to_open)
        status_str = f"Zatvorené (víkend, otvorí za {formatted_diff})"
    elif local_time < open_time_today:
        time_to_open = open_time_today - local_time
        formatted_diff, _ = format_timedelta_to_hm(time_to_open)
        status_str = f"Zatvorené (otvorí za {formatted_diff})"
    elif local_time >= close_time_today:
        # Už zatvorené pre dnešok, vypočítaj čas do ďalšieho otvorenia (zajtra alebo v pondelok)
        next_open_time = open_time_today + datetime.timedelta(days=1)
        if local_time.weekday() == 4: # Ak je piatok, ďalšie otvorenie je v pondelok
            next_open_time += datetime.timedelta(days=2)
        time_to_open = next_open_time - local_time
        formatted_diff, _ = format_timedelta_to_hm(time_to_open)
        status_str = f"Zatvorené (otvorí za {formatted_diff})"
    else: # Burza je aktuálne otvorená
        time_since_open = local_time - open_time_today
        formatted_diff, _ = format_timedelta_to_hm(time_since_open)
        status_str = f"Otvorené (otvorené {formatted_diff})"
        color_class = "green-text"

    return local_time_str, status_str, color_class

# --- Streamlit Aplikácia ---

# Malý a kompaktný názov
st.markdown("### Dividend tracker")

# Aktuálny UTC čas (používame ho ako referenciu pre všetky výpočty)
current_utc_time = datetime.datetime.now(pytz.utc)
current_bratislava_time = current_utc_time.astimezone(BRATISLAVA_TZ)

# --- Logika pre horný banner (globálny časovač) ---
top_banner_message = "N/A"
top_banner_color = "red"
closest_open_diff_seconds = float('inf') # Pre najbližšie otvorenie
longest_open_diff_seconds = -1 # Pre najdlhšie otvorenú burzu

for exchange_data in EXCHANGES:
    exchange_tz = pytz.timezone(exchange_data['timezone_str'])
    
    # Vypočítame časy otvorenia/zatvorenia burzy v jej lokálnom čase pre aktuálny deň
    # a potom ich prekonvertujeme na čas v Bratislave pre porovnanie.
    
    # Lokálny čas burzy pre aktuálny UTC čas
    current_local_time_exchange = current_utc_time.astimezone(exchange_tz)

    open_time_local = current_local_time_exchange.replace(hour=exchange_data['open_h'], minute=exchange_data['open_m'], second=0, microsecond=0)
    close_time_local = current_local_time_exchange.replace(hour=exchange_data['close_h'], minute=exchange_data['close_m'], second=0, microsecond=0)

    # Upravíme časy otvorenia/zatvorenia, ak je víkend v lokálnom čase burzy
    if current_local_time_exchange.weekday() >= 5: # Sobota alebo nedeľa
        days_to_monday = (7 - current_local_time_exchange.weekday()) % 7
        open_time_local += datetime.timedelta(days=days_to_monday)
        close_time_local += datetime.timedelta(days=days_to_monday)
    
    # Prekonvertujeme tieto časy udalostí na časovú zónu Bratislavy pre porovnanie
    open_time_bratislava = open_time_local.astimezone(BRATISLAVA_TZ)
    close_time_bratislava = close_time_local.astimezone(BRATISLAVA_TZ)

    # --- Logika pre výber správy do horného bannera ---
    if current_bratislava_time < open_time_bratislava: # Burza sa ešte len otvorí
        time_to_open = open_time_bratislava - current_bratislava_time
        if time_to_open.total_seconds() > 0 and time_to_open.total_seconds() < closest_open_diff_seconds:
            closest_open_diff_seconds = time_to_open.total_seconds()
            formatted_diff, _ = format_timedelta_to_hm(time_to_open)
            top_banner_message = f"Otvára za {formatted_diff} ({exchange_data['name']})"
            top_banner_color = "red"
    elif current_bratislava_time >= open_time_bratislava and current_bratislava_time < close_time_bratislava: # Burza je otvorená
        time_since_open = current_bratislava_time - open_time_bratislava
        if time_since_open.total_seconds() > longest_open_diff_seconds: # Hľadáme tú, ktorá je otvorená najdlhšie
            longest_open_diff_seconds = time_since_open.total_seconds()
            formatted_diff, _ = format_timedelta_to_hm(time_since_open)
            top_banner_message = f"Otvorené {formatted_diff} ({exchange_data['name']})"
            top_banner_color = "green"
    else: # Burza je zatvorená pre dnešok (alebo víkend už bol ošetrený)
        # Vypočítame otvorenie na ďalší obchodný deň
        next_open_time_local = open_time_local + datetime.timedelta(days=1)
        if open_time_local.weekday() == 4: # Ak je piatok, ďalšie otvorenie je v pondelok
            next_open_time_local += datetime.timedelta(days=2)
        
        next_open_time_bratislava = next_open_time_local.astimezone(BRATISLAVA_TZ)
        time_to_open = next_open_time_bratislava - current_bratislava_time
        
        if time_to_open.total_seconds() > 0 and time_to_open.total_seconds() < closest_open_diff_seconds:
            closest_open_diff_seconds = time_to_open.total_seconds()
            formatted_diff, _ = format_timedelta_to_hm(time_to_open)
            top_banner_message = f"Otvára za {formatted_diff} ({exchange_data['name']})"
            top_banner_color = "red"

# Zobrazenie horného bannera
st.markdown(f"<p style='font-size:1.2em; font-weight:bold; color:{top_banner_color}; margin-bottom: 0.5rem;'>{top_banner_message}</p>", unsafe_allow_html=True)

# --- Vlastné CSS pre tabuľku a kompaktnosť ---
# Použijeme textwrap.dedent aj tu, aby sme si boli istí, že CSS je správne naformátované
st.markdown(textwrap.dedent("""
    <style>
        /* Všeobecné nastavenia pre Streamlit app */
        .stApp {
            padding-top: 1rem;
            padding-right: 1rem;
            padding-left: 1rem;
            padding-bottom: 1rem;
        }
        /* Menší a kompaktnejší nadpis */
        h3 {
            margin-top: 0.5rem;
            margin-bottom: 0.5rem;
            font-size: 1.5em; /* Prispôsob veľkosť podľa potreby */
        }

        /* Štýly pre kompaktnú tabuľku */
        .compact-table {
            width: 100%;
            border-collapse: collapse; /* Odstráni medzery medzi bunkami */
            font-family: monospace; /* Pre pocit "odletovej tabule" */
            font-size: 0.9em;
        }
        .compact-table th, .compact-table td {
            padding: 2px 5px; /* Minimálne odsadenie */
            border: none; /* Bez okrajov */
            text-align: left;
            white-space: nowrap; /* Zabráni zalomeniu textu */
        }
        .compact-table tr {
            line-height: 1.2; /* Kompaktná výška riadku */
        }
        .compact-table thead {
            background-color: #f0f2f6; /* Svetlo sivá hlavička */
        }
        .compact-table .red-text { color: red; }
        .compact-table .green-text { color: green; }
        
        /* Sekcia s bielym pozadím pre tabuľku */
        .white-background-section {
            background-color: white;
            padding: 10px; /* Trochu odsadenia okolo tabuľky */
            border-radius: 5px;
        }
    </style>
    """), unsafe_allow_html=True)

# --- Generovanie tabuľky ---
# Použijeme zoznam riadkov a potom ich spojíme, aby sme mali plnú kontrolu nad odsadením.
html_lines = []

html_lines.append('<div class="white-background-section">')
html_lines.append('<table class="compact-table">')
html_lines.append('    <thead>')
html_lines.append('        <tr>')
html_lines.append('            <th>Burza</th>')
html_lines.append('            <th>Mesto</th>')
html_lines.append('            <th>Štát</th>')
html_lines.append('            <th>Miestny čas</th>')
html_lines.append('            <th>Stav</th>')
html_lines.append('        </tr>')
html_lines.append('    </thead>')
html_lines.append('    <tbody>')

for exchange_data in EXCHANGES:
    local_time_str, status_str, color_class = get_exchange_status(exchange_data, current_utc_time)
    # Každý riadok HTML je explicitne definovaný s odsadením, ktoré chceme
    html_lines.append(f'        <tr>')
    html_lines.append(f'            <td class="{color_class}">{exchange_data["name"]}</td>')
    html_lines.append(f'            <td class="{color_class}">{exchange_data["city"]}</td>')
    html_lines.append(f'            <td class="{color_class}">{exchange_data["country"]}</td>')
    html_lines.append(f'            <td class="{color_class}">{local_time_str}</td>')
    html_lines.append(f'            <td class="{color_class}">{status_str}</td>')
    html_lines.append(f'        </tr>')

html_lines.append('    </tbody>')
html_lines.append('</table>')
html_lines.append('</div>')

# Spojíme všetky riadky do jedného reťazca.
# Týmto sa zabezpečí, že prvý riadok HTML začína na stĺpci 0, čo zabráni interpretácii ako kódového bloku.
final_html_table = "
".join(html_lines)

st.markdown(final_html_table, unsafe_allow_html=True)
