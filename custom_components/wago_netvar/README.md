# Wago NetVar Integration for Home Assistant

Niestandardowa integracja dla Home Assistanta umożliwiająca dwukierunkową komunikację ze sterownikami PLC (Wago / CoDeSys) przez protokół NetVar UDP (.S3). Konfiguracja odbywa się w pliku `configuration.yaml`.

---

## ⚙️ Przykład pełnej konfiguracji w `configuration.yaml`

Poniższy przykład pokazuje, jak skonfigurować urządzenie z pełnym zestawem atrybutów (`device_class`, `state_class`, `unit_of_measurement`, `icon`):

```yaml
wago_netvar:
  - ip_address: "192.168.1.10"
    port: 1202
    cob_id: 1
    var_count: 3
    big_endian: true
    sensors:
      - name: "Temperatura Salon"
        byte_offset: 0
        size: 4
        var_type: "REAL"
        device_class: "temperature"
        state_class: "measurement"
        unit_of_measurement: "°C"
        icon: "mdi:thermometer"
      - name: "Wilgotność"
        byte_offset: 4
        size: 2
        var_type: "INT"
        device_class: "humidity"
        state_class: "measurement"
        unit_of_measurement: "%"
        icon: "mdi:water-percent"
    switches:
      - name: "Światło Salon"
        byte_offset: 8
        bit_offset: 0
        device_class: "switch"
        icon: "mdi:lightbulb"
    numbers:
      - name: "Zadana Temperatura"
        byte_offset: 10
        var_type: "REAL"
        min: 10.0
        max: 30.0
        step: 0.5
        device_class: "temperature"
        unit_of_measurement: "°C"
        icon: "mdi:thermometer-lines"
