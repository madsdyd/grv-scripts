#!/usr/bin/env python3

# Script to transform a meeting list in yaml, into something that kalendersiden.dk understands

import sys
import yaml
import dateparser

def parse_date(date_str, year=None):
    """Parses a date string and returns it in 'YYYY-MM-DD' format."""
    try:
        date_obj = dateparser.parse(date_str, settings={'DATE_ORDER': 'DMY', 'PREFER_DAY_OF_MONTH': 'first'})
        if not date_obj:
            sys.exit(f"Error: Unable to parse date '{date_str}'")
        return date_obj.strftime('%-d.%-m.%Y')  # Format as d.m.yyyy
    except ValueError:
        sys.exit(f"Error: Invalid date format '{date_str}'")

def process_group(group, output_lines):
    """Processes a group of meetings and adhoc events, converting them to Kalendersiden.dk format."""
    name = group.get("navn")
    color = group.get("farve")
    if not name or not color:
        sys.exit("Error: Each meeting group must have a 'navn' and 'farve'")

    # Process yearly events
    for year, events in group.items():
        if isinstance(year, int):  # Only process year keys (e.g., 2024, 2025)
            for date_str in events:
                full_date = parse_date(f"{date_str} {year}")
                output_lines.append(f"//{color} {full_date}: {name}")

    # Process adhoc events
    if "adhoc" in group:
        for adhoc_event in group["adhoc"]:
            date_str = adhoc_event.get("dato")
            label = adhoc_event.get("label")
            if not date_str or not label:
                sys.exit("Error: Each adhoc event must have a 'dato' and 'label'")
            full_date = parse_date(date_str)
            output_lines.append(f"//{color} {full_date}: {label}")

def process_individual_events(events, output_lines):
    """Processes individual events and adds them to the output."""
    for event in events:
        date_str = event.get("dato")
        label = event.get("label")
        color = event.get("farve")
        if not date_str or not label or not color:
            sys.exit(f"Error: Each individual event must have 'dato', 'label', and 'farve'. Something missing for {event}")
        full_date = parse_date(date_str)
        output_lines.append(f"//{color} {full_date}: {label}")

def process_standard_days(standard_days, output_lines):
    """Processes standard days and adds them directly to the output."""
    for day in standard_days:
        output_lines.append(day)

def main():
    # Check command-line arguments
    if len(sys.argv) < 3:
        print("Usage: python script.py <input_yaml_file> <output_text_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Load YAML data
    try:
        with open(input_file, "r") as file:
            data = yaml.safe_load(file)
    except FileNotFoundError:
        sys.exit(f"Error: File '{input_file}' not found.")
    except yaml.YAMLError as e:
        sys.exit(f"Error: Failed to parse YAML file. {e}")

    output_lines = []

    # Process standard days
    if "standard" in data:
        process_standard_days(data["standard"], output_lines)
    else:
        sys.exit("Error: No 'standard' section found in the YAML file.")

    # Process meetings (møde)
    if "møde" in data:
        for group in data["møde"]:
            process_group(group, output_lines)
    else:
        sys.exit("Error: No 'møde' section found in the YAML file.")

    # Process individual events (begivenhed)
    if "begivenhed" in data:
        process_individual_events(data["begivenhed"], output_lines)
    else:
        sys.exit("Error: No 'begivenhed' section found in the YAML file.")

    # Write output to file
    try:
        with open(output_file, "w") as file:
            file.write("\n".join(output_lines) + "\n")
    except IOError:
        sys.exit(f"Error: Could not write to '{output_file}'")

    print(f"Success: Calendar data written to '{output_file}'")

if __name__ == "__main__":
    main()
