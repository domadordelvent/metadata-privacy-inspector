from PIL import ExifTags


def extract_gps(exif) -> dict:
    """Extract GPS metadata from a Pillow EXIF object."""

    gps = {}

    try:
        GPS_INFO_TAG = 34853
        gps_ifd = exif.get_ifd(GPS_INFO_TAG)
    except (KeyError, AttributeError):
        return gps

    for tag_id, value in gps_ifd.items():
        tag = ExifTags.GPSTAGS.get(tag_id, str(tag_id))
        gps[tag] = value

    if "GPSLatitude" in gps and "GPSLongitude" in gps:
        gps["latitude_decimal"] = _to_decimal(
            gps["GPSLatitude"],
            gps["GPSLatitudeRef"],
        )

        gps["longitude_decimal"] = _to_decimal(
            gps["GPSLongitude"],
            gps["GPSLongitudeRef"],
        )

    return gps

def _to_decimal(coordinates, reference):
    degrees, minutes, seconds = coordinates

    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600

    if reference in ("S", "W"):
        decimal = -decimal

    return decimal