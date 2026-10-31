DOMAIN = "wago_netvar"
DEFAULT_PORT = 1202

MAGIC = b"\x00\x2D\x53\x33"
HEADER_SIZE = 20

MODE_READ = "read"
MODE_WRITE = "write"

# Integer-like types: name -> (size in bytes, signed).
# TIME is a 32-bit number of milliseconds. DATE and DT are 32-bit numbers of
# seconds since 1970-01-01, TOD is a 32-bit number of milliseconds since
# midnight. DATE, TOD and DT are handled as raw unsigned integers.
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

# Fixed-size types. STRING has a configurable size and is handled separately.
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

ALL_ENTITIES = READ_ENTITIES + WRITE_ENTITIES
