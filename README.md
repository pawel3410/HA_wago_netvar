# Wago NetVar UDP - Home Assistant

Integracja Home Assistant do komunikacji UDP ze sterownikami WAGO / CODESYS wykorzystującymi protokół NetVar UDP (.S3).

## Funkcje

- Odbieranie danych z PLC.
- Wysyłanie danych z Home Assistant do PLC.
- Tryb `read` oraz `write`.
- Obsługa pakietów pakowanych i niepakowanych.
- Obsługa wielu list NetVar.
- Obsługa wielu sterowników.
- Konfiguracja YAML.
- Konfiguracja przez interfejs Home Assistant.
- Kodowanie little-endian.
- Aktualizacja encji po każdej poprawnej ramce UDP.
- Automatyczne sensory diagnostyczne: `rx_packets`, `tx_packets`, `rx_errors`, `tx_errors`, `rejected_packets`.
- Numer `sequence` (bajty 16-17) jest odczytywany i logowany, ale nie jest uwzględniany w logice integracji.
- Suma kontrolna (bajty 18-19) jest odczytywana, ale nie jest weryfikowana; przy wysyłce zawsze `00 00`.

## Obsługiwane typy

Typy odpowiadają typom elementarnym CODESYS 2.3. Wszystkie typy wielobajtowe są kodowane w kolejności little-endian.

| Typ CODESYS | Rozmiar | Typ Home Assistant | Typ ESPHome | Zakres / opis | Encje |
|---|---:|---|---|---|---|
| BOOL | 1 bajt | `binary_sensor` / `switch` | `binary_sensor` / `switch` | `00` = false, niezerowe = true | `binary_sensor`, `switch` |
| BYTE | 1 bajt | `sensor` / `number` | `sensor` / `number` | 0..255 | `sensor`, `number` |
| USINT | 1 bajt | `sensor` / `number` | `sensor` / `number` | 0..255 | `sensor`, `number` |
| SINT | 1 bajt | `sensor` / `number` | `sensor` / `number` | -128..127 | `sensor`, `number` |
| WORD | 2 bajty | `sensor` / `number` | `sensor` / `number` | 0..65535 | `sensor`, `number` |
| UINT | 2 bajty | `sensor` / `number` | `sensor` / `number` | 0..65535 | `sensor`, `number` |
| INT | 2 bajty | `sensor` / `number` | `sensor` / `number` | -32768..32767 | `sensor`, `number` |
| DWORD | 4 bajty | `sensor` / `number` | `sensor` / `number` | 0..4294967295 | `sensor`, `number` |
| UDINT | 4 bajty | `sensor` / `number` | `sensor` / `number` | 0..4294967295 | `sensor`, `number` |
| DINT | 4 bajty | `sensor` / `number` | `sensor` / `number` | -2147483648..2147483647 | `sensor`, `number` |
| REAL | 4 bajty | `sensor` / `number` | `sensor` / `number` | IEEE 754 float 32-bit | `sensor`, `number` |
| TIME | 4 bajty | `sensor` / `number` | `sensor` / `number` | ms, bez znaku | `sensor`, `number` |
| DATE | 4 bajty | `sensor` / `number` | `sensor` / `number` | surowa liczba sekund od 1970-01-01 | `sensor`, `number` |
| TOD (`TIME_OF_DAY`) | 4 bajty | `sensor` / `number` | `sensor` / `number` | surowa liczba ms od północy | `sensor`, `number` |
| DT (`DATE_AND_TIME`) | 4 bajty | `sensor` / `number` | `sensor` / `number` | surowa liczba sekund od 1970-01-01 | `sensor`, `number` |
| STRING | n + 1 bajt | `sensor` | `sensor` | ASCII / cp1250, zakończony `00`, max 255 znaków | `sensor` (tylko read) |

Uwagi:

- **LREAL nie jest obsługiwany.**
- **DATE, TOD i DT** są dekodowane jako surowe liczby bez znaku.
- **Aliasy:** `TIME_OF_DAY` = `TOD`, `DATE_AND_TIME` = `DT`.
- **BOOL zawsze zajmuje pełny bajt**, bez adresowania bitowego.
- **STRING(n) zajmuje n + 1 bajtów.** Domyślnie 80 znaków, zakres 1..255. Zapis STRING z Home Assistant nie jest obsługiwany.
- Przy przepełnieniu typu całkowitego mniej znaczące bity są obcinane. Przy STRING liczby są konwertowane na tekst.

## Instalacja

Skopiuj katalog:

`custom_components/wago_netvar`

do katalogu konfiguracji Home Assistant:

`config/custom_components/wago_netvar`

Następnie uruchom ponownie Home Assistant.

## Konfiguracja YAML

### Przykład listy odczytowej

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

      - name: "Komunikat"
        offset: 5
        type: STRING
        length: 20
        entity: sensor
```

### Przykład listy zapisu

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    port: 1202
    list_id: 124
    mode: write
    pack_variables: false
    on_change: true
    min_interval: 500
    update_interval: 5

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
```

### Parametry listy

| Parametr | Domyślnie | Znaczenie |
|---|---|---|
| ip_address | — | Adres IP PLC. `0.0.0.0` akceptuje pakiety z dowolnego nadawcy. |
| port | 1202 | Port UDP. |
| list_id | — | Identyfikator listy NetVar (COB-ID). |
| mode | `read` | `read` albo `write`. |
| pack_variables | `true` | `true` - cały bufor w jednej ramce; `false` - osobna ramka dla zmiennej. |
| on_change | `false` | Wysyłaj przy zmianie wartości (tylko tryb write). |
| min_interval | 500 | Minimalny odstęp między wysyłkami przy `on_change`, w milisekundach. |
| update_interval | 5 | Cykliczny interwał wysyłania całej listy, w sekundach. `0` = wyłączone. |

Parametr `transmit_checksum` został usunięty (patrz sekcja „Suma kontrolna”).

### Parametry zmiennej

| Parametr | Znaczenie |
|---|---|
| name | Nazwa encji |
| offset | Pozycja w buforze w bajtach |
| type | Typ danych PLC (tabela powyżej) |
| length | Tylko `STRING`: długość tekstu w znakach, domyślnie 80 |
| entity | `sensor`, `binary_sensor`, `switch` albo `number` |
| initial_value | Początkowa wartość bufora w trybie write |
| min | Minimalna wartość encji number |
| max | Maksymalna wartość encji number |
| step | Krok encji number |
| device_class | Klasa urządzenia |
| state_class | Klasa stanu sensora |
| unit_of_measurement | Jednostka |
| icon | Ikona |
| zero_as_unavailable | Traktowanie zera jako braku wartości sensora |

Reguły doboru encji: `BOOL` używa `binary_sensor` lub `switch`, `STRING` tylko `sensor`, pozostałe typy `sensor` lub `number`. Lista `read` zawiera `sensor` i `binary_sensor`, a lista `write` `switch` i `number`.

## Aktualizacja danych i cykle NetVar

Integracja aktualizuje dane po każdej poprawnej ramce UDP.

W trybie niepakowanym każda ramka zawiera dane jednej zmiennej. Po jej odebraniu odpowiednia encja jest aktualizowana natychmiast.

W trybie pakowanym jedna ramka zawiera dane całego skonfigurowanego bufora listy. Po odebraniu poprawnej ramki aktualizowane są encje wszystkich zmiennych.

### Numer sequence

Pole `sequence` (bajty 16-17) jest 16-bitowym numerem cyklu listy. Integracja go odczytuje i zapisuje w logach debug, ale **nie używa go do wykrywania cykli ani resetowania diagnostyki**. Każda poprawna ramka jest dekodowana natychmiast.

## Automatyczne sensory diagnostyczne

Dla każdej listy integracja tworzy następujące sensory diagnostyczne:

- `sensor.netvar_list_<list_id>_rx_packets` - liczba poprawnie odebranych ramek.
- `sensor.netvar_list_<list_id>_tx_packets` - liczba wysłanych ramek.
- `sensor.netvar_list_<list_id>_rx_errors` - liczba błędów odbioru.
- `sensor.netvar_list_<list_id>_tx_errors` - liczba błędów wysyłki.
- `sensor.netvar_list_<list_id>_rejected_packets` - liczba ramek odrzuconych podczas walidacji.

Rzeczywiste identyfikatory encji zależą od nazw nadanych przez Home Assistant.

## Struktura ramki NetVar UDP

Nagłówek ma 20 bajtów. Każdy datagram UDP zawiera dokładnie jedną ramkę.

| Offset | Rozmiar | Znaczenie |
|---:|---:|---|
| 0 | 4 bajty | Sygnatura `00 2D 53 33` |
| 4 | 4 bajty | Pole zarezerwowane |
| 8 | 2 bajty | List ID |
| 10 | 2 bajty | Indeks zmiennej |
| 12 | 2 bajty | Liczba zmiennych (`var_count`) |
| 14 | 2 bajty | Długość całej ramki (`frame_size`) |
| 16 | 2 bajty | Numer sequence / cyklu |
| 18 | 1 bajt | Flagi: `00` bez sumy kontrolnej, `02` z sumą kontrolną |
| 19 | 1 bajt | Suma kontrolna (`00`, gdy wyłączona) |
| 20 | zmienna | Dane zmiennej lub bufor listy |

Wszystkie wielobajtowe pola nagłówka są zapisane little-endian.

### Walidacja ramki

Ramka jest walidowana po:

- IP nadawcy (jeśli w konfiguracji różne od `0.0.0.0`),
- porcie docelowym,
- `list_ID` (bajty 8-9),
- rozmiarze całej ramki `frame_size` (bajty 14-15),
- `var_count` (bajty 12-13) względem zadeklarowanej liczby zmiennych na liście.

Ramki nieprzechodzące walidacji są odrzucane i zwiększają licznik `rejected_packets`.

## Suma kontrolna

Algorytm sumy kontrolnej nie jest znany. Integracja nie oblicza ani nie weryfikuje sumy kontrolnej.

- Odbiór: bajty 18-19 są ignorowane.
- Wysyłanie: ramki z Home Assistant mają w bajtach 18-19 wartość `00 00`. Na listach odbiorczych w PLC musi być wyłączone sprawdzanie sumy kontrolnej.

## Wysyłanie z Home Assistant (tryb write)

Wysyłanie może być wyzwalane na dwa sposoby, działające równolegle:

1. **Przy zmianie (`on_change`)** - gdy wartość encji zmieni się w Home Assistant, lista jest wysyłana po upływie `min_interval` od ostatniej wysyłki.
2. **Cyklicznie (`update_interval`)** - co `update_interval` sekund cała lista jest wysyłana niezależnie od zmian. Wartość `0` wyłącza wysyłanie cykliczne.

W trybie pakowanym wysyłana jest cały bufor. W trybie niepakowanym każda zmienna jest wysyłana w osobnej ramce.

## Konfiguracja przez UI

W formularzu integracji podaj:

- adres IP sterownika,
- port UDP,
- List ID,
- tryb `read` lub `write`,
- pakowanie zmiennych,
- opcjonalnie `on_change`, `min_interval`, `update_interval`,
- zmienne wraz z typami, offsetami i encjami (dla `STRING` także długość).

## Ograniczenia

- Algorytm sumy kontrolnej nie jest znany.
- LREAL nie jest obsługiwany przez sterownik.
- STRING jest dostępny tylko do odczytu.
- DATE, TOD i DT są dekodowane jako surowe liczby.
- Zmiana układu listy w PLC nie jest wykrywana automatycznie.
- `initial_value` inicjalizuje bufor zapisu, ale nie jest wysyłane do PLC przy starcie Home Assistant.
- W liście pakowanej w trybie `write` zapis jednej zmiennej wysyła cały bufor.
- Format ramek TX wymaga dalszego potwierdzenia przechwyceniem pakietów.
- Nie ma mechanizmu retransmisji brakujących ramek.
