import csv
import folium
import pandas
import logging
import subprocess
from pathlib import Path

def normalize_mac(mac: str) -> str:
    """
    Normalize a MAC address by removing semicolons and colons,
    then converting it to lowercase.
    """
    return mac.replace(";", "").replace(":", "").strip().lower()


def results_to_csv(results_dir: Path, temp_output: str = "tmpresults.csv", master_output: str = "results.csv") -> None:
    """
    Runs hcxpcapngtool on all .pcapng files in the given directory (using a wildcard),
    then parses the temporary CSV output to extract Date, Time, BSSID, SSID, Encryption,
    and converts raw NMEA GPS fields into decimal degrees for Latitude and Longitude.
    Duplicate rows (based on BSSID and SSID) are skipped.

    Adjust the column indexes below as needed based on your actual output.
    """
    temp_csv_path = results_dir / temp_output
    master_csv = results_dir / master_output
    seen = set()  # track uniques
    new_rows = []

    # cap to csv
    cmd = f"hcxpcapngtool --csv={temp_output} *.pcapng"
    subprocess.run(cmd, shell=True, cwd=results_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # load master csv if it exists otherwise new
    if master_csv.exists():
        with open(master_csv, 'r', newline='') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if len(row) >= 4:
                    seen.add((row[2], row[3]))

    # open tmp csv
    with open(temp_csv_path, 'r', newline='') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            # ensure column space
            if len(row) < 9:
                continue
            date = row[0]
            time_val = row[1]
            bssid = row[2]
            ssid = row[3]
            encryption = row[4]

            # get/convert nmea fields
            raw_lat = row[5]
            lat_dir = row[6]
            raw_lon = row[7]
            lon_dir = row[8]
            latitude = nmea_to_decimal(raw_lat, lat_dir)
            longitude = nmea_to_decimal(raw_lon, lon_dir)

            key = (bssid, ssid)
            if key in seen:
                continue
            seen.add(key)
            new_rows.append([date, time_val, bssid, ssid, encryption, latitude, longitude])

    # remove temp csv
    try:
        temp_csv_path.unlink()
    except Exception as e:
        print(f"Could not delete temporary CSV: {e}")

    # append new rows
    write_header = not master_csv.exists()
    with open(master_csv, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['Date', 'Time', 'BSSID', 'SSID', 'Encryption', 'Latitude', 'Longitude'])
        for row in new_rows:
            writer.writerow(row)


def append_keys_to_results(results_csv: Path, founds_txt: Path) -> None:
    """
    Compares bssid:ssid pairs in founds.txt (lines formatted as
    "bssid:randomvalue:ssid:key") with the corresponding values in results.csv.
    If a match is found, the key from founds.txt is appended (or updated) in results.csv.

    The MAC addresses are normalized (lowercase and semicolons removed) before comparison.

    :param results_csv: Path to the results CSV file.
    :param founds_txt: Path to the founds.txt file from WPA-sec.
    """
    # Build mapping from founds.txt: (bssid, ssid) -> key
    founds_map = {}
    try:
        with open(founds_txt, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(':')
                if len(parts) != 4:
                    continue
                raw_bssid, random_val, raw_ssid, key_val = parts
                bssid = normalize_mac(raw_bssid)
                ssid = raw_ssid.strip().lower()  # Normalizing the ssid too
                founds_map[(bssid, ssid)] = key_val
    except Exception as e:
        logging.error(f"Error reading {founds_txt}: {e}")
        return

    # Read the current results.csv into memory.
    rows = []
    header = []
    try:
        with open(results_csv, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader)
            rows = list(reader)
    except Exception as e:
        logging.error(f"Error reading {results_csv}: {e}")
        return

    # Check if "Key" column exists; if not, add it.
    if "Key" not in header:
        header.append("Key")
        key_index = len(header) - 1
        # Extend every row to include an empty key value.
        for row in rows:
            row.append("")
    else:
        key_index = header.index("Key")

    updated_count = 0
    # Assuming results.csv has BSSID at index 2 and SSID at index 3.
    for row in rows:
        if len(row) < 4:
            continue
        csv_bssid = normalize_mac(row[2])
        csv_ssid = row[3].strip().lower()
        match_key = founds_map.get((csv_bssid, csv_ssid))
        if match_key:
            if len(row) <= key_index or row[key_index] != match_key:
                if len(row) <= key_index:
                    row.extend([""] * (key_index - len(row) + 1))
                row[key_index] = match_key
                updated_count += 1

    # Write the updated CSV back.
    try:
        with open(results_csv, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)
            writer.writerows(rows)
        logging.error(f"Updated {updated_count} rows in {results_csv}.")
    except Exception as e:
        logging.error(f"Error writing {results_csv}: {e}")


def nmea_to_decimal(coord_str: str, direction: str) -> float:
    """
    Converts an NMEA coordinate string (e.g., "4507.007812" for latitude or "8737.377930" for longitude)
    along with its direction ('N', 'S', 'E', or 'W') to a decimal degree value.

    For latitude, the first 2 digits are degrees.
    For longitude, the first 3 digits are degrees.

    Example:
      nmea_to_decimal("4507.007812", "N") -> 45 + 7.007812/60 ≈ 45.1168
      nmea_to_decimal("8737.377930", "W") -> -(87 + 37.377930/60) ≈ -87.622965

    :param coord_str: The raw coordinate string.
    :param direction: The direction character.
    :return: The coordinate in decimal degrees.
    """
    try:
        if not coord_str or not direction:
            return 0.0

        # Determine number of degree digits based on direction:
        deg_digits = 2 if direction.upper() in ['N', 'S'] else 3

        degrees = float(coord_str[:deg_digits])
        minutes = float(coord_str[deg_digits:])
        decimal = degrees + minutes / 60.0
        if direction.upper() in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception as e:
        print(f"Error converting NMEA coordinate '{coord_str}' with direction '{direction}': {e}")
        return 0.0


def create_html_map(results_csv: Path, output_html: str = "map.html") -> None:
    """
    Reads the results CSV, filters out invalid GPS entries, converts longitudes
    to negative if necessary, and creates an interactive map with markers for each valid entry.

    Debug logging is added to trace the processing steps.

    :param results_csv: Path to the results CSV file.
    :param output_html: Name of the HTML file to save.
    """
    logger = logging.getLogger("create_html_map")

    try:
        df = pandas.read_csv(results_csv)
        logger.debug(f"Read CSV: {results_csv}, shape: {df.shape}")
    except Exception as e:
        logger.error(f"Error reading CSV {results_csv}: {e}")
        return

    try:
        # convert columns to float
        df["Latitude"] = df["Latitude"].astype(float)
        df["Longitude"] = df["Longitude"].astype(float)
        logger.debug("Converted Latitude and Longitude columns to float.")
    except Exception as e:
        logger.error(f"Error converting coordinates: {e}")
        return

    # filter out 0's from hcxpcapngtool results (erroneous data)
    df_valid = df[(df["Latitude"] != 0.0) & (df["Longitude"] != 0.0)]
    logger.debug(f"After filtering zeros, valid entries: {df_valid.shape[0]}")

    if df_valid.empty:
        logger.error("No valid GPS entries found.")
        return

    # debugging
    logger.debug(f"Sample valid entries:\n{df_valid.head()}")


    # computer center
    avg_lat = df_valid["Latitude"].mean()
    avg_lon = df_valid["Longitude"].mean()
    logger.debug(f"Map center computed as: ({avg_lat}, {avg_lon})")

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=10)

    # add markers for valid rows
    for idx, row in df_valid.iterrows():
        popup_content = (
            f"<strong>Date:</strong> {row['Date']}<br>"
            f"<strong>Time:</strong> {row['Time']}<br>"
            f"<strong>BSSID:</strong> {row['BSSID']}<br>"
            f"<strong>SSID:</strong> {row['SSID']}<br>"
            f"<strong>Encryption:</strong> {row['Encryption']}<br>"
            f"<strong>Key:</strong> {row.get('Key', '')}"
        )
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=popup_content,
        ).add_to(m)
        logger.debug(f"Added marker for {row['BSSID']} at ({row['Latitude']}, {row['Longitude']})")

    # save
    html_path = results_csv.parent / output_html
    try:
        m.save(html_path)
        logger.info(f"Map saved to {html_path}")
    except Exception as e:
        logger.error(f"Error saving map to {html_path}: {e}")

