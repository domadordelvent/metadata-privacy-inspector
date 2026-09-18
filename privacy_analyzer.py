SENSITIVE_FIELDS = {
    "Make": "Device manufacturer",
    "Model": "Device model",
    "Software": "Software / firmware information",
    "DateTime": "Creation or modification timestamp",
    "Artist": "Author identity",
    "Copyright": "Copyright / owner information",
}


def analyze_privacy(metadata: dict) -> list[dict]:
    findings = []

    for field, description in SENSITIVE_FIELDS.items():
        if field in metadata:
            findings.append({
                "field": field,
                "value": metadata[field],
                "description": description,
            })

    gps = metadata.get("GPS")

    if gps and "latitude_decimal" in gps and "longitude_decimal" in gps:
        findings.append({
            "field": "GPS",
            "value": (
                gps["latitude_decimal"],
                gps["longitude_decimal"],
            ),
            "description": "Precise geographic location",
        })

    return findings