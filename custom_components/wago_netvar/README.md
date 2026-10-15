# Wago NetVar UDP Integration dla Home Assistant

Niestandardowa integracja dla Home Assistanta umożliwiająca dwukierunkową komunikację ze sterownikami PLC **Wago / CoDeSys** za pomocą protokołu **NetVar UDP (.S3)**.

Integracja pozwala na odbieranie danych ze sterownika (czujniki) oraz wysyłanie poleceń (przełączniki bitowe oraz zmienne numeryczne) w czasie rzeczywistym, bez konieczności używania MQTT czy dodatkowego oprogramowania pośredniczącego.

---

## 🚀 Główne cechy
* **Konfiguracja w YAML:** Pełna konfiguracja urządzeń i mapowania pamięci bezpośrednio w pliku `configuration.yaml`.
* **Automatyczne parsowanie nagłówka .S3:** Nagłówek ramki NetVar jest automatycznie parsowany w formacie *little-endian* (co zapewnia poprawny odczyt `cob_id`), podczas gdy payload zmiennych może mieć konfigurowany endianizm (`big_endian`).
* **Wsparcie dla wielu platform:**
  * **Sensor:** Obsługa zmiennych typu `REAL`, `INT`, `DINT`, `UINT`, `UDINT` z pełnymi atrybutami (`device_class`, `state_class`, `unit_of_measurement`, `icon`).
  * **Switch:** Obsługa zmiennych bitowych (odczyt stanu oraz zapis/wysyłka ramki do PLC).
  * **Number:** Obsługa wprowadzania wartości numerycznych (suwaki/pola liczbowe) zdefiniowane w określonych zakresach (`min`, `max`, `step`).
* **Stabilne unikalne ID (`unique_id`):** Oparte na nazwie encji oraz `cob_id`, co gwarantuje zachowanie historii i konfiguracji w Home Assistancie nawet w przypadku zmiany offsetów w pamięci PLC.
* **Wymuszenie odświeżania (`force_update`):** Opcjonalny, edytowalny atrybut pozwalający wymusić aktualizację stanu przy każdej odebranej ramce UDP (przydatne dla wykresów w czasie rzeczywistym).

---

## 📦 Instalacja

1. Pobierz lub skopiuj folder integracji do katalogu konfiguracyjnego Home Assistanta:
   `/config/custom_components/wago_netvar/`
2. Upewnij się, że w katalogu znajdują się następujące pliki:
   * `__init__.py`
   * `const.py`
   * `sensor.py`
   * `switch.py`
   * `number.py`
   * `manifest.json`
3. Wykonaj **pełny restart Home Assistanta** (Ustawienia -> System -> Uruchom ponownie).

---

## ⚙️ Konfiguracja (`configuration.yaml`)

Dodaj blok konfiguracyjny do swojego pliku `configuration.yaml`. Możesz skonfigurować wiele sterowników PLC lub wiele list NetVar (rozróżnianych po `cob_id`).

### Pełny schemat parametrów

```yaml
wago_netvar:
  - ip_address: "IP_STEROWNIKA_PLC"    # Adres IP sterownika (używany do wysyłki ramek [TX])
    port: 1202                         # Port UDP (domyślnie: 1202)
    cob_id: 126                        # Identyfikator listy NetVar (COB-ID) zgodny z CoDeSys
    var_count: 2                       # Liczba zmiennych w pakiecie
    big_endian: true                   # Endianizm payloadu (true dla Big Endian, false dla Little Endian)
    
    sensors:                           # Lista czujników (odczyt)
      - name: "Nazwa Sensora"
        byte_offset: 0                 # Offset w bajtach od początku payloadu
        size: 4                        # Rozmiar w bajtach (4 dla REAL/DINT, 2 dla INT)
        var_type: "REAL"               # Typ zmiennej (REAL, INT, DINT, UINT, UDINT)
        device_class: "temperature"    # Klasa urządzenia (opcjonalnie)
        state_class: "measurement"     # Klasa stanu (opcjonalnie: measurement, total, itp.)
        unit_of_measurement: "°C"      # Jednostka (opcjonalnie)
        icon: "mdi:thermometer"        # Ikona MDI (opcjonalnie)
        force_update: true             # Wymuszenie odświeżania przy każdym pakiecie (opcjonalnie, domyślnie false)

    switches:                          # Lista przełączników (odczyt/zapis bitowy)
      - name: "Nazwa Przełącznika"
        byte_offset: 4                 # Offset bajtu w payloadzie
        bit_offset: 0                  # Numer bitu w bajcie (0-7)
        device_class: "switch"         # Klasa urządzenia (opcjonalnie)
        icon: "mdi:power"              # Ikona (opcjonalnie)
        force_update: false

    numbers:                           # Lista pól liczbowych (suwaki - odczyt/zapis)
      - name: "Zadana Temperatura"
        byte_offset: 6                 # Offset w bajtach
        var_type: "REAL"               # Typ zmiennej (REAL, INT, itp.)
        min: 10.0                      # Wartość minimalna suwaka
        max: 30.0                      # Wartość maksymalna suwaka
        step: 0.5                      # Krok zmiany wartości
        unit_of_measurement: "°C"      # Jednostka
        icon: "mdi:tune"               # Ikona
        force_update: true

💡 Przykłady konfiguracji

Przykład 1: Prosta stacja pogodowa (Czujniki temperatury i wilgotności)

wago_netvar:
  - ip_address: "192.168.17.25"
    port: 1202
    cob_id: 126
    var_count: 2
    big_endian: true
    sensors:
      - name: "Salon Temperatura"
        byte_offset: 0
        size: 4
        var_type: "REAL"
        device_class: "temperature"
        state_class: "measurement"
        unit_of_measurement: "°C"
        icon: "mdi:thermometer"
        force_update: true

      - name: "Salon Wilgotność"
        byte_offset: 4
        size: 2
        var_type: "INT"
        device_class: "humidity"
        state_class: "measurement"
        unit_of_measurement: "%"
        icon: "mdi:water-percent"
        force_update: true

Przykład 2: Zaawansowana integracja mieszana (Sensory, Przełączniki i Suwaki)

wago_netvar:
  - ip_address: "192.168.17.25"
    port: 1202
    cob_id: 126
    var_count: 4
    big_endian: true
    
    sensors:
      - name: "Kocioł Temperatura"
        byte_offset: 0
        size: 4
        var_type: "REAL"
        device_class: "temperature"
        state_class: "measurement"
        unit_of_measurement: "°C"
        force_update: true
        
    switches:
      - name: "Pompa Ciepła Sterowanie"
        byte_offset: 4
        bit_offset: 0
        icon: "mdi:heat-pump"
        
      - name: "Ogrzewanie Salon Włącznik"
        byte_offset: 4
        bit_offset: 1
        icon: "mdi:radiator"

    numbers:
      - name: "Zadana Temperatura Kotła"
        byte_offset: 6
        var_type: "REAL"
        min: 20.0
        max: 80.0
        step: 0.5
        unit_of_measurement: "°C"
        icon: "mdi:thermometer-lines"

🔍 Diagnostyka i Logowanie
Jeśli chcesz monitorować odbierane pakiety [RX] oraz wysyłane ramki [TX] w logach Home Assistanta, dodaj następujący wpis do swojego pliku configuration.yaml:

logger:
  default: warning
  logs:
    custom_components.wago_netvar: info

Po restarcie systemu w zakładce Ustawienia -> System -> Logi zobaczysz szczegółowe informacje o przychodzących pakietach UDP (wraz z nagłówkiem i payloadem w formacie HEX).
