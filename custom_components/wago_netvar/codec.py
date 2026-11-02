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
    """Zwraca zweryfikowaną długość STRING w znakach."""
    if length is None:
        return DEFAULT_STRING_LENGTH

    if isinstance(length, bool):
        raise ValueError("Długość STRING musi być liczbą całkowitą")

    try:
        number = int(length)

        if float(length) != number:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Długość STRING musi być liczbą całkowitą") from None

    if not 1 <= number <= MAX_STRING_LENGTH:
        raise ValueError(
            f"Długość STRING musi być z przedziału 1 do {MAX_STRING_LENGTH}"
        )

    return number


def get_size(var_type, length=None):
    """Zwraca rozmiar w bajtach. STRING(n) zajmuje n + 1 bajtów."""
    var_type = normalize_type(var_type)

    if var_type == STRING_TYPE:
        return string_length(length) + 1

    if var_type not in TYPE_SIZES:
        raise ValueError(f"Nieobsługiwany typ zmiennej: {var_type}")

    return TYPE_SIZES[var_type]


def variable_size(variable):
    return get_size(variable["type"], variable.get("length"))


def _to_integer(value, var_type):
    if isinstance(value, bool):
        raise ValueError(f"{var_type} wartość musi być numeryczna")

    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise ValueError(f"Nieprawidłowa wartość {var_type}: {value}") from err

    return number


def _integer_range(size, signed):
    bits = size * 8

    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1

    return 0, (1 << bits) - 1


def _truncate_integer(number, size, signed):
    """Obcina liczbę całkowitą do rozmiaru w bajtach, zachowując najmłodsze bity."""
    bits = size * 8
    mask = (1 << bits) - 1
    truncated = number & mask

    if signed and truncated >= (1 << (bits - 1)):
        truncated -= 1 << bits

    return truncated


def decode_value(data, var_type, length=None):
    var_type = normalize_type(var_type)
    size = get_size(var_type, length)

    if len(data) != size:
        raise ValueError(
            f"Nieprawidłowy rozmiar danych dla {var_type}: "
            f"oczekiwano {size}, otrzymano {len(data)}"
        )

    if var_type == "BOOL":
        return data[0] != 0

    if var_type in INTEGER_TYPES:
        _size, signed = INTEGER_TYPES[var_type]

        return int.from_bytes(data, "little", signed=signed)

    if var_type == "REAL":
        value = struct.unpack("<f", data)[0]

        if not math.isfinite(value):
            raise ValueError("Otrzymana wartość REAL nie jest skończona")

        return value

    if var_type == STRING_TYPE:
        # Tekst kończy się przy pierwszym bajcie NUL. Bajty po nim nie są
        # czyszczone przez PLC i mogą zawierać nieaktualne dane z pamięci.
        text = bytes(data).split(b"\x00", 1)[0]

        return text.decode(STRING_ENCODING, errors="replace")

    raise ValueError(f"Nieobsługiwany typ zmiennej: {var_type}")


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

            raise ValueError(f"Nieprawidłowa wartość BOOL: {value}")

        if isinstance(value, bool):
            return b"\x01" if value else b"\x00"

        if value in (0, 1):
            return b"\x01" if value == 1 else b"\x00"

        raise ValueError("Wartość BOOL musi być true, false, 0 lub 1")

    if var_type in INTEGER_TYPES:
        _size, signed = INTEGER_TYPES[var_type]
        number = _to_integer(value, var_type)
        truncated = _truncate_integer(number, size, signed)

        return truncated.to_bytes(size, "little", signed=signed)

    if var_type == "REAL":
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as err:
            raise ValueError(f"Nieprawidłowa wartość REAL: {value}") from err

        if not math.isfinite(number):
            raise ValueError("Wartość REAL musi być skończona")

        try:
            return struct.pack("<f", number)
        except (OverflowError, struct.error) as err:
            raise ValueError(
                "Wartość REAL jest poza obsługiwanym zakresem"
            ) from err

    if var_type == STRING_TYPE:
        if not isinstance(value, str):
            value = str(value)

        try:
            encoded = value.encode(STRING_ENCODING)
        except UnicodeEncodeError as err:
            raise ValueError(
                f"STRING zawiera znaki nieobsługiwane przez {STRING_ENCODING}"
            ) from err

        if b"\x00" in encoded:
            raise ValueError("STRING nie może zawierać znaków NUL")

        if len(encoded) > size - 1:
            raise ValueError(
                f"STRING jest dłuższy niż {size - 1} znaków"
            )

        return encoded.ljust(size, b"\x00")

    raise ValueError(f"Nieobsługiwany typ zmiennej: {var_type}")
