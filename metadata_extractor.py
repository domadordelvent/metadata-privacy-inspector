from pathlib import Path
from PIL import Image, ExifTags
from gps_extractor import extract_gps


def extract_image_metadata(file_path: Path) -> dict:
    metadata = {}

    with Image.open(file_path) as image:
        metadata["format"] = image.format
        metadata["width"] = image.width
        metadata["height"] = image.height

        exif = image.getexif()

        gps = extract_gps(exif)

        if gps:
            metadata["GPS"] = gps

        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, str(tag_id))
            metadata[tag] = value

    return metadata
