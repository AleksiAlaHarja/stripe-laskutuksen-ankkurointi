import stripe
import os
import sys
import yaml
import time
from datetime import datetime, timezone, date

CONFIG_FILE = "config.yaml"
LOG_FILE = "debug_stripe.log"

log_file_handle = None

def init_logger():
    global log_file_handle
    log_file_handle = open(LOG_FILE, "w", encoding="utf-8")
    log(f"=== STRIPE DEBUG LOG: {datetime.now(timezone.utc).isoformat()} ===")

def log(msg):
    global log_file_handle
    if log_file_handle:
        log_file_handle.write(str(msg) + "\n")
        log_file_handle.flush()

def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')

def get_default_next_january():
    curr_year = datetime.now().year
    return f"01.01.{curr_year + 1}"

def load_config():
    default_config = {
        "stripe": {
            "api_key": ""
        },
        "billing": {
            "annual-billing-day": 1,
            "annual-billing-month": 1,
            "annual-billing-year": None
        }
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = yaml.safe_load(f)
                if isinstance(loaded, dict):
                    if "stripe" in loaded and isinstance(loaded["stripe"], dict):
                        default_config["stripe"]["api_key"] = loaded["stripe"].get("api_key", "") or ""
                    if "billing" in loaded and isinstance(loaded["billing"], dict):
                        default_config["billing"]["annual-billing-day"] = int(loaded["billing"].get("annual-billing-day", 1))
                        default_config["billing"]["annual-billing-month"] = int(loaded["billing"].get("annual-billing-month", 1))
                        default_config["billing"]["annual-billing-year"] = loaded["billing"].get("annual-billing-year")
        except Exception as e:
            print(f"Asetusten luku epäonnistui ({e}), käytetään oletuksia.")
    return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

def parse_user_date_input(input_str):
    clean_str = input_str.strip().rstrip('.')
    parts = clean_str.split('.')

    if len(parts) == 2:
        return int(parts[0]), int(parts[1]), None
    elif len(parts) == 3:
        return int(parts[0]), int(parts[1]), int(parts[2])
    else:
        raise ValueError("Virheellinen päivämäärämuoto.")

def get_next_occurrences(day, month, explicit_year=None, count=3):
    today = date.today()
    occurrences = []

    if explicit_year is not None:
        start_year = explicit_year
    else:
        start_year = today.year
        try:
            this_year_date = date(start_year, month, day)
            if this_year_date < today:
                start_year += 1
        except ValueError:
            start_year += 1

    year = start_year
    while len(occurrences) < count:
        try:
            d = date(year, month, day)
            occurrences.append(d)
        except ValueError:
            pass
        year += 1

    return occurrences

def get_target_anchor(config):
    b_day = int(config["billing"].get("annual-billing-day", 1))
    b_month = int(config["billing"].get("annual-billing-month", 1))
    b_year = config["billing"].get("annual-billing-year")

    next_dates = get_next_occurrences(b_day, b_month, explicit_year=b_year, count=1)
    target_date = next_dates[0]

    dt_utc = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
    ts = int(dt_utc.timestamp())
    str_val = target_date.strftime("%d.%m.%Y")
    return ts, str_val

def get_customer_name_parts(customer_obj):
    if not customer_obj:
        return "Tuntematon", ""

    if isinstance(customer_obj, str):
        return customer_obj, ""

    c_dict = customer_obj.to_dict() if hasattr(customer_obj, "to_dict") else dict(customer_obj)
    nimi = c_dict.get("name") or c_dict.get("description") or c_dict.get("email") or "Tuntematon"
    osat = str(nimi).strip().split(" ", 1)
    etunimi = osat[0] if len(osat) > 0 else ""
    sukunimi = osat[1] if len(osat) > 1 else ""
    return sukunimi, etunimi

def format_date(ts):
    if not ts: return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y")

def get_actual_next_invoice_date(sub_id, s_dict):
    # Jos tilaus on tauolla tulevaisuuteen (pause_collection.resumes_at)
    pause = s_dict.get("pause_collection")
    if pause:
        p_dict = pause.to_dict() if hasattr(pause, "to_dict") else dict(pause)
        resumes_at = p_dict.get("resumes_at")
        if resumes_at:
            return resumes_at

    try:
        upcoming = stripe.Invoice.create_upcoming(subscription=sub_id)
        u_dict = upcoming.to_dict() if hasattr(upcoming, "to_dict") else dict(upcoming)
        ts = u_dict.get("next_payment_attempt") or u_dict.get("period_end")
        if ts:
            return ts
    except Exception:
        pass

    items = s_dict.get("items")
    if items:
        i_data = items.get("data") if isinstance(items, dict) else getattr(items, "data", [])
        if i_data and len(i_data) > 0:
            first_item = i_data[0].to_dict() if hasattr(i_data[0], "to_dict") else dict(i_data[0])
            item_end = first_item.get("current_period_end")
            if item_end:
                return item_end

    return s_dict.get("current_period_end") or s_dict.get("trial_end") or s_dict.get("billing_cycle_anchor")

def fetch_all_subscriptions():
    init_logger()
    records = []

    try:
        subs = stripe.Subscription.list(status="all", limit=100, expand=["data.customer"])
        for sub in subs.auto_paging_iter():
            s_dict = sub.to_dict() if hasattr(sub, "to_dict") else dict(sub)
            if s_dict.get("status") not in ["active", "trialing", "paused"]:
                continue

            sub_id = s_dict.get("id")
            period_end = get_actual_next_invoice_date(sub_id, s_dict)
            customer_obj = s_dict.get("customer")

            sukunimi, etunimi = get_customer_name_parts(customer_obj)
            log(f"Tilaus: {sub_id}, Asiakas: {etunimi} {sukunimi}, PeriodEnd: {period_end} ({format_date(period_end)})")

            records.append({
                "period_end": period_end or 0,
                "sukunimi": sukunimi,
                "etunimi": etunimi,
                "sub_id": sub_id,
                "sub_raw": s_dict
            })

    except Exception as e:
        log(f"VIRHE haettaessa tilauksia: {e}")
        print(f"\nVirhe haettaessa tilauksia: {e}")
        return []

    records.sort(key=lambda r: (
        r["period_end"],
        r["sukunimi"].lower(),
        r["etunimi"].lower(),
        r["sub_id"]
    ))

    return records

def show_members(filter_mode, target_ts, target_str):
    print("Haetaan tilauksia Stripestä...")
    try:
        records = fetch_all_subscriptions()

        print(f"\n{'Ankkurointipvm':<15} ; {'Sukunimi':<20} ; {'Etunimi':<20} ; {'Subscription ID':<30}")
        print("-" * 92)

        count = 0
        for r in records:
            end_ts = r["period_end"]
            is_match = False
            if end_ts and target_ts:
                is_match = abs(end_ts - target_ts) <= 86400

            if filter_mode == "target" and not is_match:
                continue
            if filter_mode == "differing" and is_match:
                continue

            date_display = format_date(end_ts)
            print(f"{date_display:<15} ; {r['sukunimi']:<20} ; {r['etunimi']:<20} ; {r['sub_id']:<30}")
            count += 1

        print("-" * 92)
        print(f"Yhteensä {count} riviä.\n")
    except Exception as e:
        print(f"Virhe listauksessa: {e}")

def run_anchoring(target_ts, target_str):
    print(f"\nAloitetaan ankkurointi. Kohdepäivä on {target_str} (Timestamp: {target_ts})...")
    try:
        records = fetch_all_subscriptions()
        updated_count = 0
        now_ts = int(time.time())

        # Tarkistetaan onko kohdepäivä yli 1 vuoden päässä (365 päivää = 31536000 s)
        is_more_than_one_year = (target_ts - now_ts) > 31536000

        for r in records:
            end_ts = r["period_end"]
            sub_id = r["sub_id"]

            if not end_ts or abs(end_ts - target_ts) > 86400:
                try:
                    old_sub = stripe.Subscription.retrieve(sub_id)
                    cust_id = old_sub.customer
                    price_id = old_sub.items.data[0].price.id
                    default_pm = old_sub.default_payment_method

                    if not default_pm:
                        cust_obj = stripe.Customer.retrieve(cust_id)
                        default_pm = cust_obj.invoice_settings.default_payment_method

                    # Perutaan vanha tilaus
                    stripe.Subscription.cancel(sub_id, prorate=False)

                    if not is_more_than_one_year:
                        # Normaali suora ankkurointi seuraavaan vuoteen
                        create_params = {
                            "customer": cust_id,
                            "items": [{"price": price_id}],
                            "billing_cycle_anchor": target_ts,
                            "proration_behavior": "none",
                        }
                        if default_pm:
                            create_params["default_payment_method"] = default_pm
                        new_sub = stripe.Subscription.create(**create_params)
                    else:
                        # Kohdepäivä on yli 1v päässä: luodaan tilaus ja asetetaan tauolle kohdepäivään saakka
                        create_params = {
                            "customer": cust_id,
                            "items": [{"price": price_id}],
                            "proration_behavior": "none",
                            "pause_collection": {
                                "behavior": "void",
                                "resumes_at": target_ts
                            }
                        }
                        if default_pm:
                            create_params["default_payment_method"] = default_pm
                        new_sub = stripe.Subscription.create(**create_params)

                    nimi = f"{r['etunimi']} {r['sukunimi']}".strip()
                    print(f"Päivitetty onnistuneesti: {nimi:<25} ({sub_id} -> {new_sub.id}) -> {target_str}")
                    updated_count += 1

                except Exception as e:
                    log(f"Virhe tilauksessa {sub_id}: {e}")
                    print(f"Virhe tilauksessa {sub_id}: {e}")

        print(f"\nValmis! Yhteensä {updated_count} tilausta ankkuroitu päivälle {target_str}.")
    except Exception as e:
        print(f"Virhe suoritettaessa ankkurointia: {e}")

def main():
    config = load_config()

    while True:
        clear_screen()
        api_key = config["stripe"]["api_key"]
        if api_key:
            stripe.api_key = api_key
            api_status = f"Asetettu (..{api_key[-6:]})"
        else:
            stripe.api_key = None
            api_status = "EI ASETETTU"

        target_ts, target_str = get_target_anchor(config)

        print("=" * 60)
        print("          STRIPE LASKUTUKSEN HALLINTA")
        print("=" * 60)
        print(f" Asetustiedosto:    {CONFIG_FILE}")
        print(f" API-tila:          {api_status}")
        print(f" Seuraava laskutus: {target_str} (toistuu vuosittain)")
        print("-" * 60)
        print("1. Aseta Stripe-API")
        print(f"2. Aseta laskutuspäivämäärä (nykyinen: {target_str})")
        print(f"3. Näytä tilaukset, joiden laskutuspäivä on {target_str}")
        print("4. Näytä tilaukset, joilla laskutuspäivä on poikkeava")
        print("5. Näytä kaikki tilaukset")
        print("6. AKTIVOI ANKKUROINTI (Päivitä kaikki tilaukset tähän päivään)")
        print("0. Lopeta")
        print("=" * 60)

        valinta = input("\nValitse toiminto (0-6): ").strip()

        if valinta == '1':
            print("\nVinkki: Saat API-avaimen osoitteesta https://dashboard.stripe.com/apikeys")
            key = input("Syötä API-avain (tyhjä peruuttaa): ").strip()
            if key:
                config["stripe"]["api_key"] = key
                save_config(config)
                print("API-avain tallennettu config.yaml-tiedostoon!")
            input("\nPaina Enter jatkaaksesi...")

        elif valinta == '2':
            print("\nSyötä päivämäärä:")
            print(" - Ilman vuotta (esim. 1.1, 1.1. tai 05.11): käytetään automaattisesti seuraavaa tulevaa ajankohtaa.")
            print(" - Vuoden kanssa (esim. 1.1.2028 tai 21.1.2042): ensimmäinen veloitus kohdistetaan vasta tähän vuoteen.")
            print(f"Nykyinen laskutuspäivämäärä on: {target_str}")
            new_date_str = input("Syötä uusi päivämäärä (Enter säilyttää nykyisen): ").strip()

            if not new_date_str:
                print(f"\nEi muutoksia. Säilytetään nykyinen laskutuspäivämäärä: {target_str}")
            else:
                try:
                    d, m, y = parse_user_date_input(new_date_str)
                    config["billing"]["annual-billing-day"] = d
                    config["billing"]["annual-billing-month"] = m
                    config["billing"]["annual-billing-year"] = y
                    save_config(config)

                    next_three = get_next_occurrences(d, m, explicit_year=y, count=3)
                    print("\nTallennus onnistui!")
                    print("Laskutus toistuu vuosittain. Seuraavat 3 laskutuskertaa ovat:")
                    for idx, dt in enumerate(next_three, 1):
                        print(f"  {idx}. {dt.strftime('%d.%m.%Y')}")
                except Exception as err:
                    print(f"\nVirhe: {err}. Asetusta ei muutettu.")
            input("\nPaina Enter jatkaaksesi...")

        elif valinta in ['3', '4', '5']:
            if not config["stripe"]["api_key"]:
                print("\nAseta ensin API-avain kohdasta 1!")
            else:
                mode = "target" if valinta == '3' else ("differing" if valinta == '4' else "all")
                show_members(mode, target_ts, target_str)
            input("\nPaina Enter jatkaaksesi...")

        elif valinta == '6':
            if not config["stripe"]["api_key"]:
                print("\nAseta ensin API-avain kohdasta 1!")
            else:
                varmistus = input(f"\nHaluatko varmasti siirtää kaikkien tilaukset päivälle {target_str}? (k/e): ").strip().lower()
                if varmistus == 'k':
                    run_anchoring(target_ts, target_str)
                else:
                    print("Toiminto peruutettu.")
            input("\nPaina Enter jatkaaksesi...")

        elif valinta == '0':
            clear_screen()
            print("Lopetetaan. Hei hei!\n")
            sys.exit(0)

if __name__ == "__main__":
    main()
