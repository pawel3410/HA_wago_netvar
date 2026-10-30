# Wago NetVar UDP - Home Assistant

Integracja Home Assistant do komunikacji UDP ze sterownikami
WAGO / CoDeSys wykorzystującymi protokół NetVar UDP (.S3).

## Funkcje

- Odbieranie danych z PLC.
- Wysyłanie danych z Home Assistant do PLC.
- Tryb `read` oraz `write`.
- Pakiety pakowane i niepakowane.
- Obsługa wielu list NetVar.
- Obsługa wielu sterowników.
- Konfiguracja YAML.
- Konfiguracja przez interfejs Home Assistant.
- Kodowanie little-endian.

## Obsługiwane typy

| Typ | Rozmiar | Interpretacja |
|---|---:|---|
| BOOL | 1 bajt | 0 = false, wartość niezerowa = true |
| BYTE | 1 bajt | unsigned |
| INT | 2 bajty | signed |
| UINT | 2 bajty | unsigned |
| DINT | 4 bajty | signed |
| UDINT | 4 bajty | unsigned |
| DWORD | 4 bajty | unsigned |
| REAL | 4 bajty | IEEE 754 float |

Wszystkie typy wielobajtowe są kodowane w kolejności little-endian.

## Instalacja

Skopiuj katalog:

`custom_components/wago_netvar`

do katalogu konfiguracji Home Assistant:

`config/custom_components/wago_netvar`

Następnie uruchom ponownie Home Assistant.

## Konfiguracja YAML

Przykład listy odczytowej:

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    port: 1202
    list_id: 123
    mode: read
    pack_variables: true

    variables:
      - name: "Temperatura"
        offset: 0
        type: REAL
        entity: sensor
        device_class: temperature
        state_class: measurement
        unit_of_measurement: "°C"

      - name: "Stan pompy"
        offset: 4
        type: BOOL
        entity: binary_sensor

Przykład listy zapisu:

wago_netvar:
  - ip_address: "192.168.17.45"
    port: 1202
    list_id: 124
    mode: write
    pack_variables: false

    variables:
      - name: "Pompa"
        offset: 0
        type: BOOL
        entity: switch
        initial_value: false

      - name: "Temperatura zadana"
        offset: 1
        type: REAL
        entity: number
        initial_value: 20.0
        min: 0
        max: 100
        step: 0.5
        unit_of_measurement: "°C"

Parametry listy
Parametr	Znaczenie
ip_address	Adres IP PLC
port	Port UDP, domyślnie 1202
list_id	Identyfikator listy NetVar
mode	read albo write
pack_variables	true - cały bufor w jednej ramce; false - osobna ramka dla zmiennej

Parametry zmiennej
Parametr	Znaczenie
name	Nazwa encji
offset	Pozycja w buforze w bajtach
type	Typ danych PLC
entity	sensor, binary_sensor, switch albo number
initial_value	Początkowa wartość bufora w trybie write
min	Minimalna wartość encji number
max	Maksymalna wartość encji number
step	Krok encji number
device_class	Klasa urządzenia
state_class	Klasa stanu sensora
unit_of_measurement	Jednostka
icon	Ikona
zero_as_unavailable	Traktowanie zera jako braku wartości sensora

Nie używa się bit_offset ani big_endian.
Konfiguracja przez UI
W formularzu integracji podaj:
- adres IP sterownika,
- port UDP,
- List ID,
- tryb read lub write,
- ustawienie pack_variables,
- listę zmiennych w formacie JSON.
Przykład JSON:

[
  {
    "name": "Temperatura",
    "offset": 0,
    "type": "REAL",
    "entity": "sensor",
    "device_class": "temperature",
    "state_class": "measurement",
    "unit_of_measurement": "°C"
  },
  {
    "name": "Pompa",
    "offset": 4,
    "type": "BOOL",
    "entity": "binary_sensor"
  }
]

Format ramki
Nagłówek ma 20 bajtów.
Bajty	Znaczenie
0-3	Sygnatura 00 2D 53 33
8-9	List ID
10-11	Indeks zmiennej
12-13	Liczba zmiennych
14-15	Długość całej ramki
16-17	Numer sekwencyjny
18-19	Pole pozostawione bez obsługi
20...	Dane

Dla pakietów niepakowanych indeks zmiennej wskazuje jej pozycję
na skonfigurowanej liście, a liczba zmiennych wynosi 1.
Ograniczenia
- Obsługa checksum nie jest zaimplementowana.
- initial_value inicjalizuje bufor zapisu, ale nie jest automatycznie
  wysyłane do PLC podczas uruchamiania Home Assistant.
- Format ramek TX wymaga potwierdzenia przechwyceniem pakietów
  wysyłanych z Home Assistant do PLC.

