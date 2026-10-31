import pytest

from finn.symbols import SymbolError, normalize


@pytest.mark.parametrize("raw,key,yahoo", [
    ("INFY", "NSE:INFY", "INFY.NS"), (" infy ", "NSE:INFY", "INFY.NS"), ("NSE:INFY", "NSE:INFY", "INFY.NS"),
    ("INFY.NS", "NSE:INFY", "INFY.NS"), ("M&M", "NSE:M&M", "M&M.NS"), ("BAJAJ-AUTO", "NSE:BAJAJ-AUTO", "BAJAJ-AUTO.NS"),
    ("500209", "BSE:500209", "500209.BO"), ("500209.BO", "BSE:500209", "500209.BO"), ("BSE:500209", "BSE:500209", "500209.BO"),
    ("BOM:500209", "BSE:500209", "500209.BO"),
])
def test_normalize(raw, key, yahoo):
    inst = normalize(raw)
    assert inst.key == key and inst.yahoo == yahoo


@pytest.mark.parametrize("raw", ["", "   ", "BSE:INFY", "12345", "INF Y!", "INFY.L", "A" * 25])
def test_rejects_invalid(raw):
    with pytest.raises(SymbolError):
        normalize(raw)
