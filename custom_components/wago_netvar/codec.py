import math
import struct

from .const import TYPE_SIZES


def get_size(var_type):
    var_type = str(var_type).upper()

    if var_type not in TYPE_SIZES:
        raise ValueError(f"Unsupported variable type: {var_type}")

    return TYPE_SIZES[var_type]


def _to_integer(value, var_type):
    if isinstance(value, bool):
        raise ValueError(f"{var_type} value must be numeric")

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"Invalid {var_type} value: {value}")

    return number


def decode_value(data, var_type):
    var_type = str(var_type).upper()
    size = get_size(var_type)

    if len(data) != size:
        raise ValueError(
            f"Invalid data size for {var_type}: "
            f"expected {size}, received {len(data)}"
        )

    if var_type == "BOOL":
        return data[0] != 0

    if var_type == "BYTE":
        return data[0]

    if var_type == "INT":
        return int.from_bytes(data, "little", signed=True)

    if var_type == "UINT":
        return int.from_bytes(data, "little", signed=False)

    if var_type == "DINT":
        return int.from_bytes(data, "little", signed=True)

    if var_type in ("UDINT", "DWORD"):
        return int.from_bytes(data, "little", signed=False)

    if var_type == "REAL":
        value = struct.unpack("<f", data)[0]

        if not math.isfinite(value):
            raise ValueError("Received REAL value is not finite")

        return value

    raise ValueError(f"Unsupported variable type: {var_type}")


def encode_value(value, var_type):
    var_type = str(var_type).upper()
    size = get_size(var_type)

    if var_type == "BOOL":
        if isinstance(value, str):
            normalized = value.strip().lower()

            if normalized in ("true", "on", "1"):
                return b"\x01"

            if normalized in ("false", "off", "0"):
                return b"\x00"

            raise ValueError(f"Invalid BOOL value: {value}")

        if isinstance(value, bool):
            return b"\x01" if value else b"\x00"

        if value in (0, 1):
            return b"\x01" if value == 1 else b"\x00"

        raise ValueError("BOOL value must be true, false, 0 or 1")

    if var_type == "BYTE":
        number = _to_integer(value, var_type)

        if not 0 <= number <= 255:
            raise ValueError("BYTE value must be between 0 and 255")

        return number.to_bytes(size, "little", signed=False)

    if var_type == "INT":
        number = _to_integer(value, var_type)

        if not -32768 <= number <= 32767:
            raise ValueError("INT value out of range")

        return number.to_bytes(size, "little", signed=True)

    if var_type == "UINT":
        number = _to_integer(value, var_type)

        if not 0 <= number <= 65535:
            raise ValueError("UINT value out of range")

        return number.to_bytes(size, "little", signed=False)

    if var_type == "DINT":
        number = _to_integer(value, var_type)

        if not -2147483648 <= number <= 2147483647:
            raise ValueError("DINT value out of range")

        return number.to_bytes(size, "little", signed=True)

    if var_type in ("UDINT", "DWORD"):
        number = _to_integer(value, var_type)

        if not 0 <= number <= 4294967295:
            raise ValueError(f"{var_type} value out of range")

        return number.to_bytes(size, "little", signed=False)

    if var_type == "REAL":
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"Invalid REAL value: {value}")

        if not math.isfinite(number):
            raise ValueError("REAL value must be finite")

        try:
            return struct.pack("<f", number)
        except (OverflowError, struct.error):
            raise ValueError("REAL value is outside the supported range")

    raise ValueError(f"Unsupported variable type: {var_type}")
