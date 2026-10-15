# Wago NetVar UDP Integration dla Home Assistant

Niestandardowa integracja dla Home Assistanta umożliwiająca dwukierunkową komunikację ze sterownikami PLC **Wago / CoDeSys** za pomocą protokołu **NetVar UDP (.S3)** z poziomu pliku `configuration.yaml`.

---

## 📋 Obsługiwane typy zmiennych i rozmiary

Podczas konfiguracji czujników (`sensors`) oraz pól numerycznych (`numbers`) należy podać odpowiedni rozmiar w bajtach (`size`) w zależności od typu zmiennej w sterowniku PLC:

| Typ w CoDeSys | Opis / Zastosowanie | Rozmiar (`size`) | Uwagi |
| :--- | :--- | :--- | :--- |
| **BOOL** | Zmienna bólana / bitowa | *Użyj sekcji `switches`* | Wymaga podania `byte_offset` oraz `bit_offset` (0–7) |
| **INT** | Liczba całkowita 16-bit (ze znakiem) | `2` bajty | Domyślnie Little-Endian (możliwość zmiany na Big-Endian) |
| **UINT** | Liczba całkowita 16-bit (bez znaku) | `2` bajty | Domyślnie Little-Endian |
| **DINT** | Liczba całkowita 32-bit (ze znakiem) | `4` bajty | Domyślnie Little-Endian |
| **UDINT** | Liczba całkowita 32-bit (bez znaku) | `4` bajty | Domyślnie Little-Endian |
| **REAL** | Liczba zmiennoprzecinkowa (float) | `4` bajty | Standard IEEE 754 |

---

## ⚙️ Konfiguracja (`configuration.yaml`)

### Schemat parametrów
* `ip_address`: Adres IP sterownika PLC (używany do wysyłki ramek zwrotnych `[TX]`).
* `port`: Port UDP (domyślnie `1202`).
* `list_id`: Identyfikator listy NetVar zgodny z CoDeSys (dawniej COB-ID).
* `big_endian`: Endianizm payloadu (`true` dla Big Endian, `false` dla **Little Endian** — domyślnie `false`).

---

## 💡 Przykłady konfiguracji

### Przykład: Obsługa dwóch różnych list NetVar z jednego lub wielu sterowników

Poniższy przykład pokazuje konfigurację dwóch niezależnych strumieni danych (`list_id: 126` oraz `list_id: 127`), z których każdy może zawierać własny zestaw czujników, przełączników i suwaków:

```yaml
wago_netvar:
  # Pierwsza lista NetVar (np. dane klimatyczne i sterowanie oświetleniem)
  - ip_address: "192.168.17.25"
    port: 1202
    list_id: 126
    var_count: 3
    big_endian: false # Little Endian (domyślnie)
    
    sensors:
      - name: "Temperatura Salon"
        byte_offset: 0
        size: 4
        var_type: "REAL"
        device_class: "temperature"
        state_class: "measurement"
        unit_of_measurement: "°C"
        icon: "mdi:thermometer"
        force_update: true

    switches:
      - name: "Światło Salon"
        byte_offset: 4
        bit_offset: 0
        icon: "mdi:lightbulb"

    numbers:
      - name: "Zadana Temperatura Salon"
        byte_offset: 6
        var_type: "REAL"
        min: 15.0
        max: 30.0
        step: 0.5
        unit_of_measurement: "°C"
        icon: "mdi:thermostat"

  # Druga niezależna lista NetVar (np. parametry kotłowni / energii)
  - ip_address: "192.168.17.25"
    port: 1202
    list_id: 127
    var_count: 2
    big_endian: false
    
    sensors:
      - name: "Temperatura Kotła"
        byte_offset: 0
        size: 4
        var_type: "REAL"
        device_class: "temperature"
        state_class: "measurement"
        unit_of_measurement: "°C"
        icon: "mdi:fire"
        force_update: true

      - name: "Ciśnienie w Instalacji"
        byte_offset: 4
        size: 4
        var_type: "REAL"
        device_class: "pressure"
        state_class: "measurement"
        unit_of_measurement: "bar"
        icon: "mdi:gauge"
        force_update: true

```

---

## 🔍 Diagnostyka i Logowanie

Aby włączyć podgląd przychodzących pakietów `[RX]` (wraz z numerem portu, `list-ID` oraz podglądem payloadu w formacie HEX) w logach Home Assistanta, dodaj do pliku `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.wago_netvar: info

```

```

```
