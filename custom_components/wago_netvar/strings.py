{
  "config": {
    "step": {
      "user": {
        "title": "Wago NetVar UDP",
        "description": "Configure a WAGO NetVar UDP list. Enter variable definitions as a JSON list.",
        "data": {
          "ip_address": "PLC IP address",
          "port": "UDP port",
          "list_id": "NetVar List ID",
          "mode": "List mode",
          "pack_variables": "Packed variables",
          "variables_json": "Variable definitions (JSON)"
        },
        "data_description": {
          "variables_json": "Example: [{\"name\":\"Temperature\",\"offset\":0,\"type\":\"REAL\",\"entity\":\"sensor\"}]"
        }
      }
    },
    "error": {
      "invalid_config": "Invalid configuration. Check the IP address, list ID and JSON variable definitions."
    }
  }
}
