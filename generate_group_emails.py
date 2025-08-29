#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generér e-mail-lister pr. matchgruppe.

Brug:
    python generate_group_emails.py /sti/til/members.xlsx /sti/til/.match_groups.json

Forventet Excel:
- Første fane indeholder data.
- Kolonner: "Navn" og "E-mail".

Forventet JSON (.match_groups.json):
[
  { "name": "Gruppenavn", "matches": ["Navn 1", "Navn 2", ...], "color": "valgfri" },
  ...
]

Uddata (til stdout):
Gruppenavn: "Navn 1" <mail1@eksempel.dk>, "Navn 2" <mail2@eksempel.dk>, ...

Bemærk:
- Navnematch er case-insensitive og trimmet for mellemrum.
- Hvis en e-mail ikke findes, udskrives <mangler email>.
- Evt. advarsler (fx dubletter) skrives til stderr.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


def normalize(s: str) -> str:
    """Normalisér navne for robust match: trim + casefold."""
    if s is None:
        return ""
    return str(s).strip().casefold()


def build_name_to_email(excel_path: Path) -> Tuple[Dict[str, str], List[str]]:
    """
    Læs Excel og byg et opslagskort: normaliseret navn -> e-mail.
    Returnerer (map, warnings).
    """
    warnings: List[str] = []
    try:
        # Læs første fane
        df = pd.read_excel(excel_path, sheet_name=0, dtype={"Navn": str, "E-mail": str})
    except Exception as e:
        print(f"Kunne ikke læse Excel-filen: {excel_path}: {e}", file=sys.stderr)
        sys.exit(2)

    # Tjek nødvendige kolonner
    required = {"Navn", "E-mail"}
    missing = required.difference(df.columns)
    if missing:
        print(f"Excel mangler kolonner: {', '.join(sorted(missing))}", file=sys.stderr)
        sys.exit(2)

    name_to_email: Dict[str, str] = {}
    for i, row in df.iterrows():
        name_raw = row.get("Navn")
        email_raw = row.get("E-mail")
        key = normalize(name_raw)
        email = (str(email_raw).strip() if isinstance(email_raw, str) else "").strip()

        if not key:
            # Tomt navn – spring over
            if email:
                warnings.append(f"Række {i}: tomt navn men har e-mail '{email}' – ignoreres.")
            continue

        if key in name_to_email:
            # Dubletnavn i Excel – log advarsel og behold eksisterende ikke-tomme e-mail
            prev = name_to_email[key]
            if prev and email and prev != email:
                warnings.append(
                    f"Dublet af navn '{row['Navn']}' med forskellig e-mail: '{prev}' vs '{email}'. "
                    f"Beholder første forekomst."
                )
            elif not prev and email:
                # Opgradér fra tom -> ny ikke-tom e-mail
                name_to_email[key] = email
        else:
            name_to_email[key] = email

    return name_to_email, warnings


def load_groups(json_path: Path) -> List[dict]:
    """Læs match-grupper fra JSON."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("JSON-roden skal være en liste af objekter.")
        return data
    except Exception as e:
        print(f"Kunne ikke læse JSON-filen: {json_path}: {e}", file=sys.stderr)
        sys.exit(2)


def format_entry(person_name: str, email: str) -> str:
    """
    Formatér som: "Person Navn" <email>
    Hvis email mangler: <mangler email>
    """
    email_part = email if email else "mangler email"
    # Hvis email mangler, vis som <mangler email>; ellers <email>
    email_bracketed = f"<{email_part}>" if email else "<mangler email>"
    return f"\"{person_name}\" {email_bracketed}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generér e-mail-lister pr. matchgruppe.")
    parser.add_argument("excel", type=Path, nargs="?", default=Path("members.xlsx"), help="Sti til members.xlsx (første fane bruges)")
    parser.add_argument("groups_json", type=Path, nargs="?", default=Path(".match_groups.json"), help="Sti til .match_groups.json")    
    args = parser.parse_args()

    name_to_email, warnings = build_name_to_email(args.excel)
    groups = load_groups(args.groups_json)

    # Skriv evt. advarsler til stderr allerede nu
    for w in warnings:
        print(f"ADVARSEL: {w}", file=sys.stderr)

    # For hver gruppe, udskriv på den ønskede form
    for idx, grp in enumerate(groups):
        grp_name = grp.get("name", f"Gruppe {idx+1}")
        matches = grp.get("matches", [])
        if not isinstance(matches, list):
            print(f"ADVARSEL: 'matches' i gruppe '{grp_name}' er ikke en liste – springer over.", file=sys.stderr)
            continue

        # Byg liste i den rækkefølge, de står i JSON
        entries: List[str] = []
        for person in matches:
            person_str = str(person)
            key = normalize(person_str)
            email = name_to_email.get(key, "")
            if not email and key not in name_to_email:
                print(f"ADVARSEL: '{person_str}' findes ikke i Excel – udskrives uden e-mail.", file=sys.stderr)
            entries.append(format_entry(person_str, email))

        # Udskriv linjen
        line = f"{grp_name}: " + ", ".join(entries)
        print(line)


if __name__ == "__main__":
    main()
