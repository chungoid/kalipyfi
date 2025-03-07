import csv
import folium
import pandas
import logging
import subprocess
from pathlib import Path


def nmea_to_decimal(coord_str: str, direction: str) -> float:
    """
    Converts an NMEA coordinate string to a decimal degree value.

    For latitude (N/S), the coordinate is expected in ddmm.mmmmm format.
    For longitude (E/W), if the coordinate string is 11 characters long,
    it's assumed to be in ddmm.mmmmm format (i.e. missing a leading 0), otherwise
    it uses dddmm.mmmmm.

    :param coord_str: The raw coordinate string.
    :param direction: The direction ('N', 'S', 'E', or 'W').
    :return: The coordinate in decimal degrees.
    """
    try:
        if not coord_str or not direction:
            return 0.0

        if direction.upper() in ['N', 'S']:
            deg_digits = 2
        else:  # for 'E' or 'W'
            # If the string is 11 characters, assume it is ddmm.mmmmm
            if len(coord_str) == 11:
                deg_digits = 2
            else:
                deg_digits = 3

        degrees = float(coord_str[:deg_digits])
        minutes = float(coord_str[deg_digits:])
        decimal = degrees + minutes / 60.0
        if direction.upper() in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception as e:
        logging.error(f"Error converting NMEA coordinate '{coord_str}' with direction '{direction}': {e}")
        return 0.0


def run_hcxpcapngtool(results_dir: Path, temp_output: str = "tmpresults.csv") -> Path:
    cmd = f"hcxpcapngtool --csv={temp_output} *.pcapng"
    logging.debug(f"Running command: {cmd} in {results_dir}")
    subprocess.run(cmd, shell=True, cwd=results_dir, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return results_dir / temp_output


def parse_temp_csv(temp_csv_path: Path, master_output: str = "results.csv") -> Path:
    results_dir = temp_csv_path.parent
    master_csv = results_dir / master_output
    new_rows = []
    with open(temp_csv_path, 'r', newline='') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            if len(row) < 14:
                logging.debug(f"Skipping row (insufficient columns): {row}")
                continue
            date = row[0]
            time_val = row[1]
            bssid = row[2]
            ssid = row[3]
            encryption = row[4]
            raw_lat = row[10]
            lat_dir = row[11]
            raw_lon = row[12]
            lon_dir = row[13]
            logging.debug(f"Raw GPS for {bssid}/{ssid}: lat='{raw_lat}' {lat_dir}, lon='{raw_lon}' {lon_dir}")
            latitude = nmea_to_decimal(raw_lat, lat_dir)
            longitude = nmea_to_decimal(raw_lon, lon_dir)
            logging.debug(f"Converted GPS for {bssid}/{ssid}: latitude={latitude}, longitude={longitude}")
            new_rows.append([date, time_val, bssid, ssid, encryption, latitude, longitude])
    try:
        temp_csv_path.unlink()
        logging.debug(f"Deleted temporary CSV: {temp_csv_path}")
    except Exception as e:
        logging.error(f"Could not delete temporary CSV {temp_csv_path}: {e}")
    with open(master_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Time', 'BSSID', 'SSID', 'Encryption', 'Latitude', 'Longitude'])
        for row in new_rows:
            writer.writerow(row)
    logging.info(f"Wrote {len(new_rows)} rows to master CSV {master_csv}")
    return master_csv


def append_keys_to_master(master_csv: Path, founds_txt: Path) -> None:
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
                raw_bssid, _, raw_ssid, key_val = parts
                bssid = raw_bssid.replace(";", "").replace(":", "").strip().lower()
                ssid = raw_ssid.strip().lower()
                founds_map[(bssid, ssid)] = key_val
        logging.debug(f"Constructed founds_map with {len(founds_map)} entries.")
    except Exception as e:
        logging.error(f"Error reading founds.txt: {e}")
        return
    rows = []
    try:
        with open(master_csv, 'r', newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
    except Exception as e:
        logging.error(f"Error reading master CSV: {e}")
        return
    if "Key" not in header:
        header.append("Key")
        key_index = len(header) - 1
        for row in rows:
            row.append("")
    else:
        key_index = header.index("Key")
    updated_count = 0
    for row in rows:
        if len(row) < 4:
            continue
        csv_bssid = row[2].replace(";", "").replace(":", "").strip().lower()
        csv_ssid = row[3].strip().lower()
        if (csv_bssid, csv_ssid) in founds_map:
            row[key_index] = founds_map[(csv_bssid, csv_ssid)]
            updated_count += 1
    try:
        with open(master_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        logging.info(f"Updated {updated_count} rows in master CSV with keys.")
    except Exception as e:
        logging.error(f"Error writing master CSV: {e}")


def create_html_map(results_csv: Path, output_html: str = "map.html") -> None:
    logger = logging.getLogger("create_html_map")
    try:
        df = pandas.read_csv(results_csv)
        logger.debug(f"Read CSV: {results_csv}, shape: {df.shape}")
    except Exception as e:
        logger.error(f"Error reading CSV {results_csv}: {e}")
        return
    try:
        df["Latitude"] = df["Latitude"].astype(float)
        df["Longitude"] = df["Longitude"].astype(float)
        logger.debug("Converted Latitude and Longitude columns to float.")
    except Exception as e:
        logger.error(f"Error converting coordinates: {e}")
        return
    df_valid = df[(df["Latitude"] != 0.0) & (df["Longitude"] != 0.0)]
    logger.debug(f"After filtering zeros, valid entries: {df_valid.shape[0]}")
    if df_valid.empty:
        logger.error("No valid GPS entries found.")
        return
    logger.debug(f"Sample valid entries:\n{df_valid.head()}")
    avg_lat = df_valid["Latitude"].mean()
    avg_lon = df_valid["Longitude"].mean()
    logger.debug(f"Map center computed as: ({avg_lat}, {avg_lon})")
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=10)
    for _, row in df_valid.iterrows():
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
    html_path = results_csv.parent / output_html
    try:
        m.save(html_path)
        logger.info(f"Map saved to {html_path}")
    except Exception as e:
        logger.error(f"Error saving map to {html_path}: {e}")
