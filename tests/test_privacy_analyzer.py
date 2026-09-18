from privacy_analyzer import analyze_privacy


def test_detects_device_model():
    metadata = {
        "Model": "Galaxy A54 5G"
    }

    findings = analyze_privacy(metadata)

    assert len(findings) == 1
    assert findings[0]["field"] == "Model"
    assert findings[0]["value"] == "Galaxy A54 5G"

def test_detects_gps_location():
    metadata = {
        "GPS": {
            "latitude_decimal": -3.1248,
            "longitude_decimal": 38.2797,
        }
    }

    findings = analyze_privacy(metadata)

    assert len(findings) == 1
    assert findings[0]["field"] == "GPS"
    assert findings[0]["value"] == (-3.1248, 38.2797)

def test_does_not_detect_incomplete_gps():
    metadata = {
        "GPS": {
            "latitude_decimal": -3.1248,
        }
    }

    findings = analyze_privacy(metadata)

    assert findings == []