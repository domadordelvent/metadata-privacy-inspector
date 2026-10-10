import sys
from pathlib import Path

from inspection import inspect_file


def main():
    result = inspect_file(Path(sys.argv[1]))
    file_info = result["file"]
    print(f"Name: {file_info['name']}")
    print(f"Extension: {file_info['extension']}")
    print(f"Size: {file_info['size_bytes'] / 1024:.1f} KB")
    print(f"MIME type: {file_info['mime_type']}")

    print("\nMetadata:")
    for key, value in result["metadata"].items():
        print(f"{key}: {value}")

    if result["findings"]:
        print("\nPrivacy findings:")
        for finding in result["findings"]:
            print(
                f"- {finding['field']}: {finding['value']} "
                f"({finding['description']})"
            )


if __name__ == "__main__":
    main()
