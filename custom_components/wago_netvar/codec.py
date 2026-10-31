import math
import struct

from .const import (
    DEFAULT_STRING_LENGTH,
    INTEGER_TYPES,
    MAX_STRING_LENGTH,
    STRING_ENCODING,
    STRING_TYPE,
    TYPE_ALIASES,
    TYPE_SIZES,
)


def normalize_type(var_type):
    var_type = str(var_type).strip().upper()

    return TYPE_ALIASES.get(var_type, var_type)


def string_length(length=None):
    """Return the validated STRING length in characters."""
    if length is None:
        return DEFAULT_STRING_LENGTH

    if isinstance(length, bool):
        raise ValueError("STRING length must be an integer")

    try:
        number = int(length)

        if float(length) != number:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("STRING length must be an integer") from None

    if not 1 <= number <= MAX_STRING_LENGTH:
        raise ValueError(
            f"STRING length must be between 1 and {MAX_STRING_LENGTH}"
        )

    return number


def get_size(var_type, length=None):
    """Return the size in bytes. STRING(n) occupies n + 1 bytes."""
    var_type = normalize_type(var_type)

    if var_type == STRING_TYPE:
        return string_length(length) + 1

    if var_type not in TYPE_SIZES:
        raise ValueError(f"Unsupported variable type: {var_type}")

    return TYPE_SIZES[var_type]


def variable_size(variable):
    return get_size(variable["type"], variable.get("length"))


def _to_integer(value, var_type):
    if isinstance(value, bool):
        raise ValueError(f"{var_type} value must be numeric")

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise ValueError(f"Invalid {var_type} value: {value}") from err

    return number


def _integer_range(size, signed):
    bits = size * 8

    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1

    return 0, (1 << bits) - 1


def decode_value(data, var_type, length=None):
    var_type = normalize_type(var_type)
    size = get_size(var_type, length)

    if len(data) != size:
        raise ValueError(
            f"Invalid data size for {var_type}: "
            f"expected {size}, received {len(data)}"
        )

    if var_type == "BOOL":
        return data[0] != 0

    if var_type in INTEGER_TYPES:
        _size, signed = INTEGER_TYPES[var_type]

        return int.from_bytes(data, "little", signed=signed)

    if var_type == "REAL":
        value = struct.unpack("<f", data)[0]

        if not math.isfinite(value):
            raise ValueError("Received REAL value is not finite")

        return value

    if var_type == STRING_TYPE:
        # The text ends at the first NUL byte. Bytes after it are not
        # cleared by the PLC and may contain stale memory.
        text = bytes(data).split(b"\x00", 1)[0]

        return text.decode(STRING_ENCODING, errors="replace")

    raise ValueError(f"Unsupported variable type: {var_type}")


def encode_value(value, var_type, length=None):
    var_type = normalize_type(var_type)
    size = get_size(var_type, length)

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

    if var_type in INTEGER_TYPES:
        _size, signed = INTEGER_TYPES[var_type]
        number = _to_integer(value, var_type)
        minimum, maximum = _integer_range(size, signed)

        if not minimum <= number <= maximum:
            raise ValueError(
                f"{var_type} value out of range "
                f"({minimum}..{maximum})"
            )

        return number.to_bytes(size, "little", signed=signed)

    if var_type == "REAL":
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as err:
            raise ValueError(f"Invalid REAL value: {value}") from err

        if not math.isfinite(number):
            raise ValueError("REAL value must be finite")

        try:
            return struct.pack("<f", number)
        except (OverflowError, struct.error) as err:
            raise ValueError(
                "REAL value is outside the supported range"
            ) from err

    if var_type == STRING_TYPE:
        if not isinstance(value, str):
            raise ValueError("STRING value must be text")

        try:
            encoded = value.encode(STRING_ENCODING)
        except UnicodeEncodeError as err:
            raise ValueError(
                f"STRING contains characters not supported by "
                f"{STRING_ENCODING}"
            ) from err

        if b"\x00" in encoded:
            raise ValueError("STRING cannot contain NUL characters")

        if len(encoded) > size - 1:
            raise ValueError(
                f"STRING is longer than {size - 1} characters"
            )

        return encoded.ljust(size, b"\x00")

    raise ValueError(f"Unsupported variable type: {var_type}")
