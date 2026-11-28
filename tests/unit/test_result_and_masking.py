from decimal import Decimal

from backend.observability import mask_sensitive
from backend.result_engine import format_tr_number


def test_tr_number_format() -> None:
    assert format_tr_number(1250000) == "1.250.000"
    assert format_tr_number(1250000.5) == "1.250.000,50"
    assert format_tr_number(Decimal("0.125")) == "0,13"


def test_masking() -> None:
    text = "tckn 12345678901 mail ali@ornek.com tel 0532 123 45 67 api_key=abc123 TR330006100519786457841326"
    masked = mask_sensitive(text)
    for secret in ("12345678901", "ali@ornek.com", "532 123", "abc123", "TR3300"):
        assert secret not in masked
