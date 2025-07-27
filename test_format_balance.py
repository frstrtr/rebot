# test_format_balance.py
from rebot_main import format_balance

def test_cases():
    cases = [
        # (value, token_decimal, expected)
        (1460597601088, 6, "1460597.601088"),
        (1460176979501, 6, "1460176.979501"),
        (0, 6, "0"),
        (123456789, 8, "1.234568"),
        (123456789, None, "123456789"),
        (123456789.123456, None, "123456789.123456"),
        (None, 6, None),
        (1000000, 6, "1"),
        (1000000, 8, "0.01"),
        (1000000, 0, "1000000"),
    ]
    for val, dec, expected in cases:
        result = format_balance(val, dec)
        print(f"format_balance({val}, {dec}) = {result} | expected: {expected}")
        assert result == expected, f"Failed: {val}, {dec}, got {result}, expected {expected}"

if __name__ == "__main__":
    test_cases()
    print("All tests passed.")
