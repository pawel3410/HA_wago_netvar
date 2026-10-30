
DOMAIN = "wago_netvar"
DEFAULT_PORT = 1202

MAGIC = b"\x00\x2D\x53\x33"
HEADER_SIZE = 20

MODE_READ = "read"
MODE_WRITE = "write"

TYPE_SIZES = {
    "BOOL": 1,
    "BYTE": 1,
    "INT": 2,
    "UINT": 2,
    "DINT": 4,
    "UDINT": 4,
    "DWORD": 4,
    "REAL": 4,
}

READ_ENTITIES = ("sensor", "binary_sensor")
WRITE_ENTITIES = ("switch", "number")

ALL_ENTITIES = READ_ENTITIES + WRITE_ENTITIES
