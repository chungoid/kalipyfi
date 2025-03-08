import csv
import folium
import pandas
import logging
import subprocess
from pathlib import Path

from config.constants import BASE_DIR
from database.db_manager import get_db_connection
from tools.hcxtool.db import insert_hcxtool_results


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
    """
    Parses a temporary CSV file generated by hcxtool (with tab-delimited fields),
    converts the GPS coordinates from NMEA to decimal, and writes a master CSV.
    Also, inserts each valid row into the hcxtool_results database table.

    If the converted latitude or longitude equals 0.0, they are stored as NULL in the DB.

    Parameters:
        temp_csv_path (Path): The path to the temporary CSV file.
        master_output (str): The filename for the master CSV file.

    Returns:
        Path: The path to the master CSV file.
    """
    results_dir = temp_csv_path.parent
    master_csv = results_dir / master_output
    new_rows = []

    conn = get_db_connection(BASE_DIR)

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

            # If coordinates are 0.0, set NULL
            if latitude == 0.0:
                latitude = None
            if longitude == 0.0:
                longitude = None

            new_rows.append([date, time_val, bssid, ssid, encryption, latitude, longitude])
            # pass an empty string for 'key' ..add it later if user gets wpasec dl
            insert_hcxtool_results(conn, date, time_val, bssid, ssid, encryption, latitude, longitude, "")

    conn.close()
    # delete tmp
    try:
        temp_csv_path.unlink()
        logging.debug(f"Deleted temporary CSV: {temp_csv_path}")
    except Exception as e:
        logging.error(f"Could not delete temporary CSV {temp_csv_path}: {e}")

    # Write the master CSV file.
    with open(master_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Time', 'BSSID', 'SSID', 'Encryption', 'Latitude', 'Longitude'])
        for row in new_rows:
            writer.writerow(row)
    logging.info(f"Wrote {len(new_rows)} rows to master CSV {master_csv}")
    return master_csv

def read_founds(founds_txt: Path) -> dict:
    """Reads founds.txt and returns a dict keyed by (bssid, ssid) with key values."""
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
                raw_bssid = parts[0]
                raw_ssid = parts[2]
                key_val = parts[3]
                bssid = raw_bssid.replace(";", "").replace(":", "").strip().lower()
                ssid = raw_ssid.strip().lower()
                founds_map[(bssid, ssid)] = key_val
        logging.debug(f"Constructed founds_map with {len(founds_map)} entries.")
    except Exception as e:
        logging.error(f"Error reading founds.txt: {e}")
    return founds_map


def read_master_csv(master_csv: Path) -> (dict, list):
    """Reads master CSV and returns a tuple: (data dict, header)."""
    data = {}
    header = ['Date', 'Time', 'BSSID', 'SSID', 'Encryption', 'Latitude', 'Longitude', 'Key']
    try:
        with open(master_csv, 'r', newline='') as f:
            reader = csv.reader(f)
            header = next(reader)
            if "Key" not in header:
                header.append("Key")
            key_index = header.index("Key")
            for row in reader:
                if len(row) < 4:
                    continue
                if len(row) < len(header):
                    row += [""] * (len(header) - len(row))
                csv_bssid = row[2].replace(";", "").replace(":", "").strip().lower()
                csv_ssid = row[3].strip().lower()
                data[(csv_bssid, csv_ssid)] = row
    except Exception as e:
        logging.warning(f"Master CSV not found or could not be read ({e}). Starting with empty CSV.")
    return data, header


def merge_data(csv_data: dict, header: list, founds_map: dict) -> dict:
    """Merges CSV data with founds_map. Updates keys and adds missing entries."""
    key_index = header.index("Key")
    # update existing CSV data with founds keys
    for key_tuple, found_key in founds_map.items():
        if key_tuple in csv_data:
            csv_data[key_tuple][key_index] = found_key
        else:
            # create a new row with defaults
            new_row = ["", "", key_tuple[0], key_tuple[1], "", "", "", found_key]
            csv_data[key_tuple] = new_row
    logging.info(f"Merged total of {len(csv_data)} entries after combining CSV and founds.txt.")
    return csv_data


def write_master_csv(master_csv: Path, header: list, csv_data: dict) -> None:
    """Writes the merged data back to the master CSV."""
    try:
        with open(master_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in csv_data.values():
                writer.writerow(row)
        logging.info(f"Master CSV written with {len(csv_data)} entries.")
    except Exception as e:
        logging.error(f"Error writing master CSV: {e}")


def update_database(csv_data: dict, header: list) -> None:
    """Updates the hcxtool database with the merged data."""
    try:
        conn = get_db_connection(BASE_DIR)
        cursor = conn.cursor()
        for row in csv_data.values():
            # row structure: [Date, Time, BSSID, SSID, Encryption, Latitude, Longitude, Key]
            query = """
                INSERT OR REPLACE INTO hcxtool (date, time, bssid, ssid, encryption, latitude, longitude, key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            # Convert latitude and longitude if possible; use None if empty or zero
            try:
                lat = float(row[5]) if row[5] and row[5] != "0" else None
            except:
                lat = None
            try:
                lon = float(row[6]) if row[6] and row[6] != "0" else None
            except:
                lon = None
            cursor.execute(query, (row[0], row[1], row[2], row[3], row[4], lat, lon, row[7]))
        conn.commit()
        conn.close()
        logging.info("Database updated with merged data from CSV and founds.txt.")
    except Exception as e:
        logging.error(f"Error updating the database with merged data: {e}")


def append_keys_to_master(master_csv: Path, founds_txt: Path) -> None:
    founds_map = read_founds(founds_txt)
    csv_data, header = read_master_csv(master_csv)
    merged_data = merge_data(csv_data, header, founds_map)
    write_master_csv(master_csv, header, merged_data)
    update_database(merged_data, header)


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
