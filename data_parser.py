import sys
import zipfile
import os
from lxml import etree
import matplotlib.pyplot as plt
import numpy as np


def parse_ods_file(filename, num_rows):
    with zipfile.ZipFile(filename, "r") as archive:
        with archive.open("content.xml") as content_file:
            content = content_file.read()

    root = etree.fromstring(content)
    ns = {
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }
    rows = root.xpath(
        "//table:table-row[position() > 25 and position() <= " + str(25 + num_rows) + "]", namespaces=ns)

    time_values = []
    id_values = []

    for row in rows:
        cells = row.xpath(".//table:table-cell/text:p", namespaces=ns)
        if len(cells) > 0:
            value = cells[0].text
            split_values = value.split(";")
            time_ms = float(split_values[1])
            id_hex = int(split_values[5], 16)

            time_values.append(time_ms)
            id_values.append(id_hex)

    return time_values, id_values


def parse_pgn_file(filename):
    with zipfile.ZipFile(filename, "r") as archive:
        with archive.open("content.xml") as content_file:
            content = content_file.read()

    root = etree.fromstring(content)
    ns = {
        "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    }
    rows = root.xpath("//table:table-row", namespaces=ns)

    pgn_values = []

    for row in rows:
        cells = row.xpath(".//table:table-cell/text:p", namespaces=ns)
        if len(cells) > 0:
            value = int(cells[0].text, 16)  # Convert hexadecimal to integer
            pgn_values.append(value)

    return set(pgn_values)


def get_pgn(msg_id):
    # Get the PDU format and PDU specific bits
    pdu_format = (msg_id >> 16) & 0x3
    pdu_specific = (msg_id >> 8) & 0xFF

    # Calculate the PGN
    if pdu_format == 0:
        # PDU 1 format
        pgn = (pdu_specific << 8) | ((msg_id >> 16) & 0xFF)
    elif pdu_format == 1:
        # PDU 2 format
        pgn = (pdu_specific << 8) | ((msg_id >> 16) & 0xFF)
    elif pdu_format == 2:
        # PDU 1 format, group function
        pgn = (pdu_specific << 8) | ((msg_id >> 16) & 0xFF)
    else:
        # PDU 2 format, group function
        pgn = (pdu_specific << 8) | ((msg_id >> 16) & 0xFF)

    return pgn


def extract_pgn(extended_id):
    pgn = (extended_id >> 8) & 0xFFFF
    return pgn


def get_can_id(id_hex):
    """Extracts the standard CAN ID from the given extended CAN ID."""
    return id_hex & 0x1FFFFFFF


def plot_data(time_values, id_values, output_dir, pgn_values, threshold_percentage=5):
    unique_ids = set(id_values)

    category_A = {}
    category_B = set()

    for unique_id in unique_ids:
        if not (0x800 > unique_id >= 0):
            continue

        can_id = get_can_id(unique_id)

        if can_id in pgn_values:
            continue

        filtered_time_values = [time_value for id_value, time_value in zip(
            id_values, time_values) if id_value == unique_id]

        cycle_times = [filtered_time_values[i] - filtered_time_values[i - 1]
                       for i in range(1, len(filtered_time_values))]

        if len(cycle_times) > 0:
            median_cycle_time = np.median(cycle_times)
            threshold = median_cycle_time * (1 + threshold_percentage / 100)

            exceeded_count = sum(
                cycle_time > threshold for cycle_time in cycle_times)

            if exceeded_count > 0:
                category_A[hex(can_id)] = exceeded_count
            else:
                category_B.add(hex(can_id))

        fig, ax = plt.subplots(figsize=(15, 5))
        ax.scatter(filtered_time_values[:-1], cycle_times, marker="o", s=15)
        ax.set_xlabel("Time (ms)")
        ax.set_ylabel("Cycle Time (ms)")
        ax.set_title(f"Cycle Time vs Time (ID {hex(unique_id)})")

        output_file = os.path.join(
            output_dir, f"cycle_time_vs_time_ID_{unique_id}.png")
        plt.savefig(output_file, dpi=300)
        plt.close()

    with open(os.path.join(output_dir, "category_A.txt"), "w") as f:
        for can_id, count in category_A.items():
            if 0x800 > int(can_id, 16) >= 0:
                f.write(f"{can_id}: {count}\n")

    with open(os.path.join(output_dir, "category_B.txt"), "w") as f:
        for can_id in category_B:
            if 0x800 > int(can_id, 16) >= 0:
                f.write(f"{can_id}\n")

    with open(os.path.join(output_dir, "blocked_IDs.txt"), "w") as f:
        f.write(f"{[hex(x) for x in pgn_values]}")

    print(f"Number of members in Category A: {len(category_A)}")
    print(f"Number of members in Category B: {len(category_B)}")
    print(f"Number of extracted PGNs: {len(pgn_values)}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            f"Usage: {sys.argv[0]} <data-ods-file> <pgn-ods-file> <output-dir> <num-rows>")
        sys.exit(1)

    # Input definitions for terminal
    data_file = sys.argv[1]
    pgn_file = sys.argv[2]
    output_dir = sys.argv[3]
    num_rows = int(sys.argv[4])

    # Process the PGN file first
    pgn_values = parse_pgn_file(pgn_file)

    # Process the ODS file and filter the IDs from the PGN file
    time_values, id_values = parse_ods_file(data_file, num_rows)

    # Analyze and plot the data
    plot_data(time_values, id_values, output_dir, pgn_values)
