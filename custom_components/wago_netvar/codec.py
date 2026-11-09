"""Stałe oraz kodowanie/dekodowanie wartości NetVar (little-endian)."""
import datetime
import math
import struct

DOMAIN = "wago_netvar"
DEFAULT_PORT = 1202

MAGIC = b"\x00\x2D\x53\x33"
HEADER_SIZE = 20

# Maksymalny ładunek datagramu UDP (IPv4) pomniejszony o nagłówek NetVar.
MAX_PAYLOAD_SIZE = 65507 - HEADER_SIZE

MODE_READ = "read"
MODE_WRITE = "write"

DEFAULT_ON_CHANGE = False
DEFAULT_MIN_INTERVAL = 500  # milisekundy
DEFAULT_UPDATE_INTERVAL = 5  # sekundy, 0 = wyłączone
DEFAULT_TIMEOUT = 0  # sekundy, 0 = wyłączone (tylko listy read)
DEFAULT_REQUIRE_VALUES = False  # lista write: nie wysyłaj, dopóki wszystkie zmienne nie mają wartości

# Jak często (s) odświeżane są sensory diagnostyczne po zmianie liczników.
DIAGNOSTIC_REFRESH_INTERVAL = 1.0

# Minimalny odstęp (s) między powtórzeniami tego samego ostrzeżenia w logu.
WARNING_INTERVAL = 60.0

# Typy całkowite: nazwa -> (rozmiar w bajtach, znak).
# TIME to 32-bitowa liczba milisekund. DATE i DT to 32-bitowe liczby
# sekund od 1970-01-01, TOD to 32-bitowa liczba milisekund od północy.
# DATE, TOD i DT są obsługiwane jako surowe liczby unsigned.
INTEGER_TYPES = {
    "BYTE": (1, False),
    "USINT": (1, False),
    "SINT": (1, True),
    "WORD": (2, False),
    "UINT": (2, False),
    "INT": (2, True),
    "DWORD": (4, False),
    "UDINT": (4, False),
    "DINT": (4, True),
    "TIME": (4, False),
    "DATE": (4, False),
    "TOD": (4, False),
    "DT": (4, False),
}

# Typy o stałym rozmiarze. STRING ma konfigurowalny rozmiar i jest obsługiwane osobno.
TYPE_SIZES = {
    "BOOL": 1,
    "REAL": 4,
    **{name: size for name, (size, _signed) in INTEGER_TYPES.items()},
}

# Typy czasowe: odczyt jako surowa liczba (format raw) albo tekst w zapisie IEC 61131-3 (format text).
TEMPORAL_TYPES = ("TIME", "DATE", "TOD", "DT")
TEMPORAL_FORMATS = ("raw", "text")

STRING_TYPE = "STRING"
DEFAULT_STRING_LENGTH = 80
MAX_STRING_LENGTH = 255
STRING_ENCODING = "ascii"  # NetVar STRING: wyłącznie ASCII

SUPPORTED_TYPES = tuple(TYPE_SIZES) + (STRING_TYPE,)

TYPE_ALIASES = {
    "TIME_OF_DAY": "TOD",
    "DATE_AND_TIME": "DT",
}

READ_ENTITIES = ("sensor", "binary_sensor")
WRITE_ENTITIES = ("switch", "number")

ENTITY_CATEGORIES = ("config", "diagnostic")

DIAGNOSTIC_SENSORS = (
    "rx_packets",
    "tx_packets",
    "rx_errors",
    "tx_errors",
    "rejected_packets",
)

SERVICE_SEND_LIST = "send_list"


# --------------------------------------------------------------------------
# Kodowanie i dekodowanie wartości (little-endian)
# --------------------------------------------------------------------------

def normalize_type(var_type):
    """Zwraca nazwę typu wielkimi literami, z rozwiniętymi aliasami."""
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
    """Rozmiar zmiennej (z definicji konfiguracyjnej) w bajtach."""
    return get_size(variable["type"], variable.get("length"))


def to_bool(value):
    """Konwersja wartości na bool (true/false, on/off, 0/1)."""
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in ("true", "on", "yes", "1"):
            return True

        if normalized in ("false", "off", "no", "0"):
            return False

    raise ValueError(f"Nieprawidłowa wartość BOOL: {value}")


def _integer_range(size, signed):
    bits = size * 8

    if signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1

    return 0, (1 << bits) - 1


def type_range(var_type):
    """Zakres (min, max) typu całkowitego albo None dla pozostałych typów."""
    var_type = normalize_type(var_type)

    if var_type not in INTEGER_TYPES:
        return None

    size, signed = INTEGER_TYPES[var_type]

    return _integer_range(size, signed)


def _round_half_away(number):
    """Zaokrągla do najbliższej liczby całkowitej (połówki od zera, jak llround w C++)."""
    return int(math.copysign(math.floor(abs(number) + 0.5), number))


def _to_integer(value, var_type):
    """Konwertuje wartość na liczbę całkowitą; ułamki są zaokrąglane do najbliższej."""
    if isinstance(value, bool):
        raise ValueError(f"{var_type} wartość musi być numeryczna")

    try:
        if isinstance(value, int):
            return value

        if isinstance(value, str):
            text = value.strip()

            try:
                return int(text)
            except ValueError:
                value = float(text)

        number = float(value)

        if not math.isfinite(number):
            raise ValueError("wartość nieskończona")

        return _round_half_away(number)
    except (TypeError, ValueError, OverflowError) as err:
        raise ValueError(f"Nieprawidłowa wartość {var_type}: {value}") from err


def _truncate_integer(number, size, signed):
    """Obcina liczbę całkowitą do rozmiaru w bajtach, zachowując najmłodsze bity."""
    bits = size * 8
    mask = (1 << bits) - 1
    truncated = number & mask

    if signed and truncated >= (1 << (bits - 1)):
        truncated -= 1 << bits

    return truncated


def decode_value(data, var_type, length=None):
    """Dekoduje bajty z ramki NetVar (little-endian) na wartość Pythona."""
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

        # float32 ma ok. 7-8 cyfr znaczących. Zaokrąglenie usuwa szum
        # konwersji (np. 20.100000381469727 -> 20.1).
        return float(f"{value:.8g}")

    if var_type == STRING_TYPE:
        # Tekst kończy się przy pierwszym bajcie NUL. Bajty po nim nie są
        # czyszczone przez PLC i mogą zawierać nieaktualne dane z pamięci.
        text = bytes(data).split(b"\x00", 1)[0]

        # Bajty spoza ASCII (>127) zamieniamy na '?', jak w wersji ESPHome.
        return bytes(b if b < 128 else 0x3F for b in text).decode(STRING_ENCODING)

    raise ValueError(f"Nieobsługiwany typ zmiennej: {var_type}")


def number_to_text(value):
    """Zamienia liczbę na tekst zapisywany do zmiennej STRING.

    Liczby całkowite (także całkowite wartości float) są zapisywane bez części
    ułamkowej, pozostałe z dokładnością do 7 cyfr znaczących.
    """
    if isinstance(value, bool):
        return "1" if value else "0"

    if isinstance(value, int):
        return str(value)

    number = float(value)

    if not math.isfinite(number):
        raise ValueError("Wartość nie może być nieskończona ani NaN")

    if number == int(number) and abs(number) < 1e15:
        return str(int(number))

    return f"{number:.7g}"


def encode_value(value, var_type, length=None):
    """Koduje wartość do bajtów NetVar (little-endian) dla danego typu."""
    var_type = normalize_type(var_type)
    size = get_size(var_type, length)

    if var_type == "BOOL":
        return b"\x01" if to_bool(value) else b"\x00"

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
        text = value if isinstance(value, str) else number_to_text(value)

        try:
            encoded = text.encode(STRING_ENCODING)
        except UnicodeEncodeError as err:
            raise ValueError(
                f"STRING zawiera znaki spoza ASCII (dozwolone tylko {STRING_ENCODING})"
            ) from err

        if b"\x00" in encoded:
            raise ValueError("STRING nie może zawierać znaków NUL")

        # Tekst dłuższy niż n znaków jest ucinany (jak w wersji ESPHome).
        return encoded[: size - 1].ljust(size, b"\x00")

    raise ValueError(f"Nieobsługiwany typ zmiennej: {var_type}")


def format_temporal(var_type, raw):
    """Tekst w zapisie IEC dla typów czasowych (taki sam jak w wersji ESPHome).

    TIME: T#1d2h3m4s500ms (części zerowe pomijane, zero to T#0ms),
    DATE: D#2026-11-08, DT: DT#2026-11-08-12:34:56,
    TOD: TOD#12:34:56 albo TOD#12:34:56.789 (milisekundy tylko gdy niezerowe).
    DATE i DT to sekundy od 1970-01-01 bez przeliczania strefy czasowej.
    """
    var_type = normalize_type(var_type)
    raw = int(raw)

    if var_type == "TIME":
        days, rest = divmod(raw, 86_400_000)
        hours, rest = divmod(rest, 3_600_000)
        minutes, rest = divmod(rest, 60_000)
        seconds, millis = divmod(rest, 1000)
        parts = "".join(
            f"{value}{unit}"
            for value, unit in (
                (days, "d"), (hours, "h"), (minutes, "m"),
                (seconds, "s"), (millis, "ms"),
            )
            if value
        )

        return "T#" + (parts or "0ms")

    if var_type == "TOD":
        hours, rest = divmod(raw, 3_600_000)
        minutes, rest = divmod(rest, 60_000)
        seconds, millis = divmod(rest, 1000)
        text = f"TOD#{hours:02d}:{minutes:02d}:{seconds:02d}"

        return text + (f".{millis:03d}" if millis else "")

    if var_type in ("DATE", "DT"):
        moment = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=raw)

        if var_type == "DATE":
            return f"D#{moment:%Y-%m-%d}"

        return f"DT#{moment:%Y-%m-%d-%H:%M:%S}"

    raise ValueError(f"Typ {var_type} nie jest typem czasowym")
