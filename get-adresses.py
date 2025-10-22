#!/usr/bin/env python3

import requests
import json
import sys
from collections import Counter
import argparse

API_BASE = "https://api.dataforsyningen.dk"


def get_kommunekode(kommunenavn: str) -> str:
    """Look up kommunekode from a kommunenavn using DAWA API.
    Prefer exact (case-insensitive) match; otherwise take the first result.
    """
    url = f"{API_BASE}/kommuner"
    r = requests.get(url, params={"navn": kommunenavn}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise ValueError(f"Ingen kommune fundet med navnet '{kommunenavn}'.")

    # Exact case-insensitive match if possible
    exact = [k for k in data if k.get("navn", "").lower() == kommunenavn.lower()]
    chosen = exact[0] if exact else data[0]
    if not exact and len(data) > 1:
        sys.stderr.write(
            f"[advarsel] Fandt ikke en entydig match for '{kommunenavn}'. Vælger '{chosen.get('navn')}' (kode {chosen.get('kode')})."
        )
    return chosen["kode"], chosen.get("navn", kommunenavn)


def stream_adresser(kommunekode: str, per_side: int = 1000):
    """Generator der streamer 'mini'-adresser for en kommune fra DAWA, side for side.
    Venter 1 sekund mellem kald, skriver status til stderr og håndterer 'sidst side'-cases.
    Stopper pænt ved tom side ELLER hvis API'et returnerer 400 for en side uden data.
    """
    import time
    import requests

    base = f"{API_BASE}/adresser"
#    params = {"kommunekode": kommunekode, "struktur": "mini", "per_side": per_side, "side": 1}
    params = {"kommunekode": kommunekode, "struktur": "mini" }

    while True:
#        sys.stderr.write(f"Henter side {params['side']}... ")
        sys.stderr.write(f"Henter side... ")
        sys.stderr.flush()
        try:
            r = requests.get(base, params=params, timeout=30)
            # DAWA kan returnere 400 hvis man beder om en side ud over sidste
            if r.status_code == 400:
                sys.stderr.write("400 fra API – antager at der ikke er flere sider.\n")
                break
            r.raise_for_status()
            items = r.json()
        except requests.HTTPError as e:
            code = getattr(e.response, "status_code", None)
            if code == 400:
                sys.stderr.write("400 fra API – antager at der ikke er flere sider.\n")
                break
            sys.stderr.write(f"HTTP-fejl: {e}\n")
            break
        except Exception as e:
            sys.stderr.write(f"Fejl: {e}\n")
            break

        if not items:
            sys.stderr.write("Ingen flere data.\n")
            break

        sys.stderr.write(f"{len(items)} adresser hentet.\n")
        sys.stderr.flush()

        for it in items:
            yield it

        # Hvis vi fik færre end per_side, er vi på sidste side
        if len(items) < per_side:
            sys.stderr.write("Sidste side nået (færre end per_side).\n")
            break

        break
#        params["side"] += 1
        time.sleep(2) # Try and avoid timeouts from dataforsyningen


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Hent adresser fra DAWA for en kommune og skriv enten: "
            "--long (NDJSON pr. linje), --detail (betegnelse pr. linje) "
            "eller (default) et tabel-udtræk med antal adresser pr. vejnavn (tab-separeret)."
        )
    )
    parser.add_argument("kommunenavn", help="Navn på kommune, fx 'Furesø'")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--long", action="store_true", help="Output alle felter som NDJSON (én JSON pr. linje)")
    group.add_argument("--detail", action="store_true", help="Output 'betegnelse' pr. linje")
    parser.add_argument("--outfile", help="Skriv output til fil i stedet for stdout")
    parser.add_argument("--per-page", type=int, default=1000, help="Antal elementer pr. side (default 1000)")

    args = parser.parse_args()

    try:
        kommunekode, resolved_name = get_kommunekode(args.kommunenavn)
    except Exception as e:
        sys.stderr.write(f"Fejl ved opslag af kommune: {e}\n")
        sys.exit(1)

    sys.stderr.write(f"Kommune: {resolved_name} (kode {kommunekode})\n")

    # Vælg output-destination
    out = open(args.outfile, "w", encoding="utf-8") if args.outfile else sys.stdout

    try:
        if args.long:
            # Stream rå NDJSON (mini-struktur)
            for it in stream_adresser(kommunekode, per_side=args.per_page):
                line = json.dumps(it, ensure_ascii=False)
                out.write(line + "\n")
        elif args.detail:
            # Kun 'betegnelse' pr. linje
            for it in stream_adresser(kommunekode, per_side=args.per_page):
                bet = it.get("betegnelse", "")
                out.write(f"{bet}\n")
        else:
            # Default: antal adresser pr. vejnavn, tab-separeret: "<vejnavn>	<count>"
            counts = Counter()
            for it in stream_adresser(kommunekode, per_side=args.per_page):
                vej = it.get("vejnavn", "")
                counts[vej] += 1
            # Sortér alfabetisk efter vejnavn (kan ændres til counts.most_common() hvis ønsket)
            for vej in sorted(counts.keys(), key=lambda s: (s is None, s)):
                out.write(f"{vej}	{counts[vej]}\n")
    finally:
        if args.outfile and out is not sys.stdout:
            out.close()


if __name__ == "__main__":
    main()
