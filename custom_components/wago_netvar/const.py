DOMAIN = "wago_netvar"
DEFAULT_PORT = 1202

MAGIC = b"\x00\x2D\x53\x33"
HEADER_SIZE = 20

MODE_READ = "read"
MODE_WRITE = "write"

DEFAULT_ON_CHANGE = False
DEFAULT_MIN_INTERVAL = 500  # milisekundy
DEFAULT_UPDATE_INTERVAL = 5  # sekundy, 0 = wyłączone

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

STRING_TYPE = "STRING"
DEFAULT_STRING_LENGTH = 80
MAX_STRING_LENGTH = 255
STRING_ENCODING = "cp1250"

SUPPORTED_TYPES = tuple(TYPE_SIZES) + (STRING_TYPE,)

TYPE_ALIASES = {
    "TIME_OF_DAY": "TOD",
    "DATE_AND_TIME": "DT",
}

READ_ENTITIES = ("sensor", "binary_sensor")
WRITE_ENTITIES = ("switch", "number")
