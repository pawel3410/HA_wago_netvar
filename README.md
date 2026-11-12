# Wago NetVar UDP - Home Assistant

Integracja Home Assistant do komunikacji UDP ze sterownikami WAGO / CODESYS wykorzystującymi protokół NetVar UDP (.S3).

Wymagana wersja Home Assistant: **2024.11 lub nowsza**.

## Funkcje

- Odbieranie danych z PLC (listy `read`) i wysyłanie danych do PLC (listy `write`).
- Obsługa pakietów pakowanych i niepakowanych.
- Obsługa wielu list NetVar i wielu sterowników. Listy `read` i `write` mogą korzystać z tego samego portu.
- Wysyłka na adres jednego PLC lub **broadcast** (`255.255.255.255`).
- Odczyt wybranych zmiennych z listy (pozostałe można pominąć).
- Typy czasowe (TIME, DATE, TOD, DT) jako czytelny tekst IEC (`T#1s500ms`, `DT#2026-11-08-12:34:56`) albo surowa liczba.
- Przywracanie stanu encji `switch`/`number` po restarcie (`restore_value`) oraz blokada wysyłki do czasu uzyskania wartości (`require_values`, `require_value`).
- Listy poprawnie skonfigurowane działają nawet wtedy, gdy inna lista w YAML ma błąd (błędna jest pomijana, komunikat w logu).
- Opcjonalny `timeout` odbioru: po jego przekroczeniu encje stają się niedostępne.
- Konfiguracja wyłącznie ręczna, tekstowa (YAML w `configuration.yaml`) ze ścisłą walidacją: literówki w nazwach pól są błędem. Integracja nie ma kreatora w interfejsie (config flow).
- Kodowanie little-endian.
- Aktualizacja encji po każdej poprawnej ramce UDP.
- Automatyczne sensory diagnostyczne: `rx_packets_<list_id>`, `rx_errors_<list_id>`, `rejected_packets_<list_id>` dla list `read`, `tx_packets_<list_id>`, `tx_errors_<list_id>` dla list `write` oraz sumy wszystkich list (`total_rx_packets` itd.).
- Konfiguracja (nazwy parametrów i domyślne wartości) jest taka sama jak w komponencie ESPHome: tę samą listę można opisać w obu platformach niemal identycznie.
- Wysyłka przy zmianie wysyła tylko zmienioną zmienną (lista niepakowana), z osobnym `min_interval` i `sequence` dla każdej zmiennej.
- Usługa `wago_netvar.send_list` wymuszająca natychmiastową wysyłkę listy `write`.
- Numer `sequence` (bajty 16-17) jest przy odbiorze odczytywany i logowany, ale nie jest uwzględniany w logice; przy wysyłce rośnie osobno dla listy (pakowana) albo dla każdej zmiennej (niepakowana).
- Flagi (bajt 18) i suma kontrolna (bajt 19) są odczytywane, ale nie weryfikowane; przy wysyłce zawsze `00 00`. Ramki z typem wiadomości (bajty 4-7) różnym od `0` są odrzucane.

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
| TIME | 4 bajty | `sensor` / `number` | `text_sensor` lub `sensor` / `number` | ms, bez znaku; tekst `T#1d2h3m4s500ms` | `sensor`, `number` |
| DATE | 4 bajty | `sensor` / `number` | `text_sensor` lub `sensor` / `number` | sekundy od 1970-01-01; tekst `D#2026-11-08` | `sensor`, `number` |
| TOD (`TIME_OF_DAY`) | 4 bajty | `sensor` / `number` | `text_sensor` lub `sensor` / `number` | ms od północy; tekst `TOD#12:34:56.789` | `sensor`, `number` |
| DT (`DATE_AND_TIME`) | 4 bajty | `sensor` / `number` | `text_sensor` lub `sensor` / `number` | sekundy od 1970-01-01; tekst `DT#2026-11-08-12:34:56` | `sensor`, `number` |
| STRING(n) | n + 1 bajt | `sensor` (read) / `number` (write, liczba zapisana jako tekst) | `text_sensor` (read) / `number` (write) | tekst ASCII zakończony `00`, domyślnie 80 znaków, max 255 | `sensor` (read), `number` (write) |

Uwagi:

- **LREAL nie jest obsługiwany** (nie jest obsługiwany przez NetVar).
- **Typy czasowe (TIME, DATE, TOD, DT)**: encja `sensor` pokazuje domyślnie tekst w zapisie IEC (`format: text`), a przy `format: raw` surową liczbę bez znaku (można wtedy ustawić `device_class`, `state_class`, jednostkę). Tekst jest taki sam jak w wersji ESPHome: TIME `T#0ms`, `T#1s500ms`, `T#49d17h2m47s295ms` (części zerowe pomijane), DATE `D#2026-11-08`, DT `DT#2026-11-08-12:34:56`, TOD `TOD#12:34:56` (z `.mmm` tylko gdy milisekundy są niezerowe). DATE i DT są wyświetlane bez przeliczania strefy czasowej, tak jak je przechowuje sterownik. Zapis odbywa się surową liczbą przez `number`.
- **Aliasy:** `TIME_OF_DAY` = `TOD`, `DATE_AND_TIME` = `DT`.
- **BOOL zawsze zajmuje pełny bajt**, bez adresowania bitowego.
- **STRING(n) zajmuje n + 1 bajtów.** Domyślnie 80 znaków, zakres 1..255. Tylko ASCII: przy odczycie bajty spoza ASCII (>127) są zamieniane na `?`, przy zapisie tekst ze znakami spoza ASCII jest odrzucany (błąd w interfejsie). Zapis STRING odbywa się encją `number`: liczba jest zamieniana na tekst (patrz „Konwersja wartości przy zapisie”).
- **REAL** jest zaokrąglany do 8 cyfr znaczących przy odczycie, co usuwa szum konwersji float32 (np. `20.1` zamiast `20.100000381`).
- Zasady konwersji przy zapisie opisuje sekcja „Konwersja wartości przy zapisie”.

## Instalacja

Skopiuj katalog `custom_components/wago_netvar` do katalogu konfiguracji Home Assistant (`config/custom_components/wago_netvar`), dopisz konfigurację do `configuration.yaml` i uruchom ponownie Home Assistant. Repozytorium zawiera też `hacs.json` do instalacji jako repozytorium własne w HACS.

Uwaga dla użytkowników wersji 1.1.0: konfiguracja przez interfejs (config flow) została usunięta, a listy konfiguruje się wyłącznie w YAML. Dotychczasowe wpisy utworzone w interfejsie przestaną działać: usuń je w *Ustawienia → Urządzenia i usługi* i przenieś ich konfigurację do `configuration.yaml` (nazwy pól są takie same jak w kreatorze).

## Konfiguracja YAML

### Lista odczytowa, pakowana

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    port: 1202
    list_id: 123
    mode: read
    pack_variables: true
    timeout: 30

    variables:
      - name: "Temperatura"
        offset: 0
        type: REAL
        entity: sensor
        device_class: temperature
        state_class: measurement
        unit_of_measurement: "°C"
        suggested_display_precision: 1

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

### Lista zapisu ze zmienną STRING

Zmienna STRING w liście `write` jest sterowana encją `number`; liczba jest zamieniana na tekst, a tekst dłuższy niż `length` jest ucinany:

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    list_id: 125
    mode: write
    variables:
      - name: "Numer receptury"
        offset: 0
        type: STRING
        length: 8
        entity: number
        min: 0
        max: 99999999
        initial_value: 0
```

### Odczyt tylko wybranych zmiennych

Lista w PLC ma 10 zmiennych typu INT (po 2 bajty), a w Home Assistant potrzebne są tylko dwie pierwsze i ostatnia. Offsety wskazują położenie zmiennych w buforze, a `var_count` informuje, ile zmiennych ma cała lista w PLC:

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    list_id: 130
    mode: read
    pack_variables: true
    var_count: 10          # tyle zmiennych ma lista w PLC
    variables:
      - {name: "Wartość 1",  offset: 0,  type: INT, entity: sensor}
      - {name: "Wartość 2",  offset: 2,  type: INT, entity: sensor}
      - {name: "Wartość 10", offset: 18, type: INT, entity: sensor}
```

W liście **niepakowanej** o położeniu zmiennej w ramce decyduje `index` (numer zmiennej w liście PLC), a `offset` to tylko miejsce w buforze Home Assistant i można go pominąć:

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    list_id: 131
    mode: read
    pack_variables: false
    variables:
      - {name: "Wartość 3",  index: 2, type: INT, entity: sensor}
      - {name: "Wartość 10", index: 9, type: INT, entity: sensor}
```

Ramki zmiennych, których nie skonfigurowano, są w trybie niepakowanym poprawnie pomijane (liczą się do `rx_packets`, nie do `rejected_packets`).

### Lista zapisu

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"   # albo "255.255.255.255" dla broadcastu
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
| ip_address | — | Adres IPv4. Lista `read`: adres nadawcy (PLC), `0.0.0.0` akceptuje pakiety z dowolnego nadawcy. Lista `write`: adres docelowy, może to być broadcast `255.255.255.255` (nie może być `0.0.0.0`). |
| port | 1202 | Port UDP. Lista `read` nasłuchuje na nim (jeśli jest zajęty, lista nie uruchomi się), lista `write` wysyła na ten port. Listy `write` nie zajmują portu: wysyłają z osobnego gniazda na porcie lokalnym przydzielonym przez system, więc nie kolidują z listami `read` na tym samym numerze portu. |
| list_id | — | Identyfikator listy NetVar (COB-ID), 0..65535. |
| mode | `read` | `read` albo `write`. Alias: `direction` (nazwa używana w ESPHome); nie podawaj obu naraz. |
| pack_variables | `true` | `true` - cały bufor w jednej ramce; `false` - osobna ramka dla zmiennej. |
| var_count | liczba zmiennych | Tylko listy pakowane. Liczba zmiennych w liście PLC. Przy odczycie musi się zgadzać z polem `var_count` ramki, przy wysyłce jest wpisywana do nagłówka. Nie może być mniejsza od liczby skonfigurowanych zmiennych. |
| payload_size | z offsetów | Tylko listy pakowane. Rozmiar danych listy w bajtach. Domyślnie wynika z najdalszej zmiennej; przy odczycie ramka może wtedy mieć dłuższy ładunek. Po podaniu `payload_size` ładunek odbieranej ramki musi mieć dokładnie taki rozmiar, a wysyłany bufor ma taki rozmiar. |
| on_change | `false` | Wysyłaj przy zmianie wartości (tylko tryb write). Alias: `send_on_change`. Patrz „Wysyłanie z Home Assistant”. |
| min_interval | 500 | Minimalny odstęp między wysyłkami przy `on_change` (osobno dla każdej ramki: listy albo zmiennej). Liczba oznacza milisekundy; można podać też tekst z jednostką: `"500ms"`, `"1s"`, `"2min"`, `"1h"`. |
| update_interval | 5 | Cykliczny interwał wysyłania całej listy. Liczba oznacza sekundy; można podać też tekst z jednostką (`"500ms"`, `"5s"`, `"2min"`). `0`, `"0s"` albo `never` = wyłączone. |
| timeout | 0 | Tylko tryb read. Po tym czasie bez ramki encje stają się niedostępne (liczba = sekundy, albo tekst z jednostką jak wyżej). `0` = wyłączone. W liście niepakowanej liczony osobno dla każdej zmiennej. |
| require_values | `false` | Tylko tryb write, lista **pakowana**: nie wysyłaj listy, dopóki każda zmienna nie ma wartości (patrz „Wartości początkowe i przywracanie”). W liście niepakowanej użycie `require_values` jest błędem: służy do tego `require_value` przy zmiennych. |

Parametry niedotyczące danego trybu (np. `timeout` w liście write, `var_count` w niepakowanej) są ignorowane. Parametr `transmit_checksum` został usunięty (patrz sekcja „Suma kontrolna”).

### Parametry zmiennej

| Parametr | Dotyczy | Znaczenie |
|---|---|---|
| name | wszystkie | Nazwa encji. |
| unique_id | wszystkie | Identyfikator encji. Domyślnie wyznaczany z nazwy (`slug`). Można go podać ręcznie, żeby zmiana nazwy zmiennej nie tworzyła nowej encji. Powtórzony `unique_id` w obrębie listy (także dwie nazwy dające ten sam slug) jest błędem. |
| type | wszystkie | Typ danych PLC (tabela powyżej). |
| entity | wszystkie | `sensor`, `binary_sensor`, `switch` albo `number`. |
| offset | wszystkie | Pozycja w buforze w bajtach. Wymagany w liście pakowanej, w niepakowanej opcjonalny (domyślnie bezpośrednio za poprzednimi zmiennymi). Alias: `byte_offset` (nazwa używana w ESPHome). |
| index | lista niepakowana | Numer zmiennej w liście PLC. Domyślnie najmniejszy wolny numer (bez jawnych `index` jest to pozycja na liście YAML). W listach pakowanych ignorowany. |
| length | `STRING` | Długość tekstu w znakach (1..255), domyślnie 80. |
| format | `sensor` typu TIME, DATE, TOD, DT | `text` (domyślnie): tekst IEC, `raw`: surowa liczba. Przy `text` nie wolno podawać `device_class`, `state_class`, `unit_of_measurement`, `suggested_display_precision` ani `suggested_unit_of_measurement`. |
| initial_value | lista write | Początkowa wartość bufora i encji. Podanie go jawnie oznacza też, że zmienna „ma wartość” od startu (patrz „Wartości początkowe i przywracanie”). |
| restore_value | `switch`, `number` | `true`: po restarcie Home Assistant przywracany jest ostatni stan encji i wysyłany do PLC. Domyślnie `false`. |
| require_value | lista write niepakowana | `true`: ramka tej zmiennej nie jest wysyłana, dopóki zmienna nie ma wartości. W liście pakowanej jest błędem (użyj `require_values` listy). |
| min, max | `number` | Zakres. Dla typów całkowitych domyślnie zakres typu (nie może go przekraczać), dla `REAL` i `STRING` pola wymagane. |
| step | `number` | Krok, domyślnie 1. Dla typów całkowitych musi być liczbą całkowitą. |
| mode | `number` | `auto` (domyślnie), `box` albo `slider`. |
| device_class | `sensor`, `binary_sensor`, `switch`, `number` | Klasa urządzenia (sprawdzana względem listy klas Home Assistant). |
| state_class | `sensor` | Klasa stanu (`measurement`, `total`, `total_increasing`). |
| unit_of_measurement | `sensor`, `number` | Jednostka. Dla `sensor` z `device_class` musi do niej pasować. |
| suggested_display_precision | `sensor` | Liczba miejsc po przecinku (0..15) w interfejsie. |
| zero_as_unavailable | `sensor` | Traktowanie zera jako braku wartości. |
| icon | wszystkie | Ikona. |
| entity_category | wszystkie | `config` albo `diagnostic`. |
| enabled_by_default | wszystkie | Czy encja jest domyślnie włączona (domyślnie `true`). |
| force_update | wszystkie | Wymuszanie zapisu stanu także bez zmiany wartości (domyślnie `false`). |
| visible_by_default | wszystkie | Czy encja jest domyślnie widoczna w rejestrze encji (domyślnie `true`). |
| suggested_unit_of_measurement | `sensor` | Sugerowana jednostka wyświetlania (Home Assistant przelicza wartość z `unit_of_measurement`, np. °C na °F). |
| inverted | `binary_sensor`, `switch` | Odwraca wartość BOOL: dla `binary_sensor` PLC FALSE oznacza stan włączony, dla `switch` do PLC trafia negacja stanu (dotyczy też `initial_value` i `restore_value`, które opisują stan encji). |

Reguły doboru encji: `BOOL` używa `binary_sensor` lub `switch`, `STRING` używa `sensor` (lista `read`) albo `number` (lista `write`), pozostałe typy `sensor` lub `number`. Lista `read` zawiera `sensor` i `binary_sensor`, a lista `write` `switch` i `number`.

Konfiguracja jest walidowana ściśle: nieznane pola, pola niepasujące do rodzaju encji (np. `min` w `sensor`), nakładające się offsety, powtórzone `index` i `unique_id` oraz błędne `initial_value` kończą się komunikatem o błędzie.

**Każda lista jest walidowana osobno** przy starcie: lista z błędem jest pomijana (komunikat w logu Home Assistant: „Nie można uruchomić listy YAML nr N: …”), a pozostałe listy działają normalnie. Ponieważ Home Assistant nie sprawdza tej walidacji w *Narzędzia deweloperskie → YAML → Sprawdź konfigurację*, po zmianie konfiguracji warto przejrzeć log.

### Identyfikatory encji (`unique_id`)

Identyfikator encji składa się z adresu listy i `unique_id` zmiennej: `wago_netvar_<ip>_<port>_<list_id>_<tryb>_<unique_id>`. Bez pola `unique_id` jest ono wyznaczane z nazwy zmiennej, więc kolejność zmiennych w YAML nie ma znaczenia, ale **zmiana nazwy zmiennej tworzy nową encję** (stara pozostaje w rejestrze jako niedostępna). Żeby tego uniknąć, podaj `unique_id` ręcznie; wtedy nazwę można zmieniać dowolnie. Powtórzony `unique_id` w obrębie listy jest błędem konfiguracji.

Uwaga dla użytkowników wersji 1.1.0 i starszych: format identyfikatorów zmienił się (wcześniej zawierał numer pozycji zmiennej), więc encje po aktualizacji pojawią się jako nowe, a dawne trzeba usunąć z rejestru encji.

## Aktualizacja danych i cykle NetVar

Integracja aktualizuje dane po każdej poprawnej ramce UDP.

W trybie niepakowanym każda ramka zawiera dane jednej zmiennej. Po jej odebraniu odpowiednia encja jest aktualizowana natychmiast.

W trybie pakowanym jedna ramka zawiera dane całego bufora listy. Po odebraniu poprawnej ramki aktualizowane są encje wszystkich zmiennych.

### Dostępność i timeout

Encja listy `read` jest niedostępna do chwili odebrania pierwszych danych. Przy `timeout > 0` po przekroczeniu tego czasu bez ramki (w liście niepakowanej: bez ramki danej zmiennej) encje przechodzą w stan niedostępny, a po wznowieniu transmisji wracają automatycznie. Encje listy `write` są zawsze dostępne.

### Błędy dekodowania

Wartość, której nie da się zdekodować (np. REAL będący NaN lub nieskończonością), nie zmienia stanu encji, zwiększa `rx_errors`, a ostrzeżenie w logu jest powtarzane najwyżej raz na minutę.

### Numer sequence

Pole `sequence` (bajty 16-17) jest 16-bitowym licznikiem ramek. **Odbiór:** integracja go odczytuje i zapisuje w logach debug, ale nie używa go do wykrywania cykli ani resetowania diagnostyki; każda poprawna ramka jest dekodowana natychmiast. **Wysyłka:** licznik startuje od 1 i rośnie przy każdej wysłanej ramce. Lista pakowana ma jeden licznik na listę, a lista niepakowana osobny licznik dla każdej zmiennej.

## Automatyczne sensory diagnostyczne

Sensory diagnostyczne (liczniki rosnące od uruchomienia Home Assistant, odświeżane najwyżej raz na sekundę) tworzone są automatycznie, a ich nazwy zawierają `list_id`:

| Lista | Sensory |
|-------|---------|
| `read` | `rx_packets_<list_id>` - ramki, które przeszły walidację (także ramki zmiennych pominiętych w liście niepakowanej); `rx_errors_<list_id>` - błędy gniazda przy odbiorze oraz błędy dekodowania wartości; `rejected_packets_<list_id>` - ramki, które nie przeszły walidacji listy (reguły w sekcji „Walidacja ramki”) |
| `write` | `tx_packets_<list_id>` - wysłane ramki (w liście niepakowanej każda zmienna to osobna ramka); `tx_errors_<list_id>` - nieudane wysyłki |

Dodatkowo powstaje jeden zestaw sum po wszystkich listach: `total_rx_packets`, `total_rx_errors`, `total_rejected_packets`, `total_tx_packets`, `total_tx_errors`. Identyfikatory encji nadaje Home Assistant na podstawie nazw (np. `sensor.rx_packets_124`); przy dwóch listach tego samego kierunku o tym samym `list_id` Home Assistant dopisze do drugiej nazwy numer.

Encje z YAML nie tworzą urządzenia (ograniczenie Home Assistant dla encji bez wpisu konfiguracyjnego).

## Struktura ramki NetVar UDP

Nagłówek ma 20 bajtów. Każdy datagram UDP zawiera dokładnie jedną ramkę.

| Offset | Rozmiar | Znaczenie |
|---:|---:|---|
| 0 | 4 bajty | Sygnatura `00 2D 53 33` |
| 4 | 4 bajty | Typ wiadomości (w dokumentacji 3S pole „ID”; nie mylić z list_ID): `0` = dane zmiennych sieciowych. Inne wartości oznaczają potwierdzenia, prośby bootup i wymianę parametrów (SDO). Przy odbiorze ramki z wartością różną od `0` są odrzucane, przy wysyłce `0` |
| 8 | 2 bajty | List ID |
| 10 | 2 bajty | Index zmiennej w trybie niepakowanym (w pakowanym `0`) |
| 12 | 2 bajty | Liczba zmiennych (`var_count`; w niepakowanym `1`) |
| 14 | 2 bajty | Długość całej ramki (`frame_size`) |
| 16 | 2 bajty | Numer sequence / cyklu |
| 18 | 1 bajt | Flagi (bit 0: żądanie potwierdzenia, bit 1: żądanie sprawdzenia sumy, bit 2: błędna suma). W obserwowanych ramkach `00` lub `02`; odbiór ignoruje to pole, wysyłka zawsze `00` |
| 19 | 1 bajt | Suma kontrolna (algorytm nieznany); odbiór ignoruje to pole, wysyłka zawsze `00` |
| 20 | zmienna | Dane zmiennej lub bufor listy |

Wszystkie wielobajtowe pola nagłówka są zapisane little-endian.

### Walidacja ramki

Ramka jest walidowana po:

- IP nadawcy (jeśli w konfiguracji różne od `0.0.0.0`),
- porcie docelowym (lista nasłuchuje na swoim porcie),
- typie wiadomości (bajty 4-7), który musi wynosić `0` (dane zmiennych); potwierdzenia, prośby bootup i SDO są odrzucane,
- `list_ID` (bajty 8-9),
- rozmiarze całej ramki `frame_size` (bajty 14-15) względem rzeczywistej długości datagramu,
- `var_count` (bajty 12-13): w liście pakowanej względem `var_count` listy, w niepakowanej musi wynosić 1,
- rozmiarze ładunku: w liście pakowanej co najmniej `payload_size` (lub rozmiar wynikający z offsetów; dokładnie tyle, gdy podano `payload_size`), w niepakowanej dokładnie rozmiar zmiennej.

Wszystkie listy `read` na jednym porcie korzystają z jednego gniazda. Każdy datagram jest przekazywany do list o zgodnym `list_id`, a ramka jest dekodowana przez każdą listę, która przejdzie pełną walidację (także kilka list o tym samym `list_id`, ale różnych adresach nadawcy). Zliczanie `rejected_packets` jest takie samo jak w wersji ESPHome:

- ramka niemożliwa do zidentyfikowania (za krótka, błędne magic bytes) albo o `list_id`, którego nie obsługuje żadna lista `read` tego portu, jest zliczana na **wszystkich** listach `read` tego portu (powód trafia tylko do logu debug),
- ramka o `list_id` obsługiwanym przez listy tego portu, której żadna z nich nie przyjęła (zły adres nadawcy, typ wiadomości różny od `0`, `var_count`, `frame_size`, rozmiar ładunku), jest zliczana tylko na listach o tym `list_id` (ostrzeżenie w logu, najwyżej raz na minutę).

Uwaga: jeżeli sterownik wysyła na ten sam port wiele list, a Home Assistant odczytuje tylko jedną, licznik `rejected_packets` będzie rósł przy każdej ramce pozostałych list. To zamierzone: ramka o innym `list_id` nie przechodzi walidacji listy.

## Suma kontrolna

Algorytm sumy kontrolnej nie jest znany. Integracja nie oblicza ani nie weryfikuje sumy kontrolnej.

- Odbiór: bajty 18-19 są ignorowane.
- Wysyłanie: ramki z Home Assistant mają w bajtach 18-19 wartość `00 00`. Na listach odbiorczych w PLC musi być wyłączone sprawdzanie sumy kontrolnej.

## Wysyłanie z Home Assistant (tryb write)

Lista `write` jest wysyłana w trzech trybach, które działają niezależnie od siebie i można je łączyć:

1. **Przy zmianie (`on_change`)**, 2. **cyklicznie (`update_interval`)**, 3. **na żądanie** - usługa `wago_netvar.send_list` (pola: `list_id`, opcjonalnie `ip_address`) wysyła listę natychmiast (w liście niepakowanej wszystkie zmienne), z zachowaniem blokad `require_value(s)`.

| Ustawienie | Zachowanie |
|------------|------------|
| tylko `on_change: true` (`update_interval: 0`) | Ramka jest wysyłana po zmianie wartości. Pierwsza wysyłka nie jest ograniczona; kolejna nie wcześniej niż `min_interval` po poprzedniej. Zmiana w trakcie odstępu jest wysyłana dopiero po jego upływie, a kilka zmian w tym czasie trafia do jednej ramki (ostatnie wartości). Ustawienie tej samej wartości nie jest zmianą i niczego nie wysyła. `min_interval: 0` wysyła każdą zmianę natychmiast. |
| tylko `update_interval` (`on_change: false`) | Co `update_interval` wysyłana jest cała lista (w liście niepakowanej: wszystkie zmienne), niezależnie od zmian. Zmiany same niczego nie wysyłają. |
| oba | Cykliczna wysyłka niesie aktualne wartości, czyli także niewysłane zmiany, i anuluje ich oczekiwanie. Każda wysyłka (także cykliczna) liczy się jako „poprzednia” dla `min_interval`, więc zmiana tuż po wysyłce cyklicznej czeka do upływu `min_interval`. |

**Lista pakowana:** zmiana dowolnej zmiennej powoduje wysłanie całej listy (jedna ramka, `payload_size` bajtów, nagłówek z `var_count`); `min_interval` i `sequence` dotyczą listy.

**Lista niepakowana:** po zmianie wysyłana jest **tylko ta zmienna, która zmieniła wartość** (własna ramka z numerem `index`), a `min_interval` jest liczony osobno dla każdej zmiennej (zmiany różnych zmiennych nie opóźniają się wzajemnie). Każda zmienna ma własny `sequence`.

Bajty bufora nieobjęte żadną zmienną mają wartość `00`. Nieudana wysyłka jest ponawiana najwyżej raz na `min_interval` (co najmniej raz na sekundę) i liczona w `tx_errors`. Encje `switch` i `number` pokazują stan optymistyczny (`assumed_state`): PLC nie potwierdza zapisu.

### Konwersja wartości przy zapisie

Wysyłana wartość jest konwertowana na typ zmiennej NetVar (te same reguły co w wersji ESPHome):

- Przy przepełnieniu typu całkowitego zachowywane są najmniej znaczące bity, a nadmiarowe, najbardziej znaczące, są odrzucane (np. `70000` zapisane do INT daje `4464`).
- Wartości ułamkowe zapisywane do typów całkowitych są zaokrąglane do najbliższej liczby całkowitej (połówki od zera: `2.5` daje `3`).
- Liczby zapisywane do zmiennej STRING są zamieniane na tekst ASCII: wartości całkowite bez części ułamkowej i wykładnika (`12`, `1000000`), pozostałe z dokładnością do 7 cyfr znaczących (`7.5`). Tekst dłuższy niż `length` znaków jest ucinany (ostrzeżenie w logu), a tekst ze znakami spoza ASCII jest odrzucany.
- Wartość REAL poza zakresem float32 oraz nieskończona lub NaN są odrzucane.
- Dla BOOL akceptowane są: `1/0`, `true/false`, `on/off`, `yes/no` (bez rozróżniania wielkości liter).

### Wartości początkowe i przywracanie

Dla zmiennych sterowanych encją `switch` lub `number`:

- `initial_value` – wartość bufora i encji po starcie, gdy nie ma przywróconego stanu. Bez niego bufor zaczyna od zera (`switch`: wyłączony, `number`: wartość najbliższa zeru w zakresie `min..max`).
- `restore_value: true` – po restarcie Home Assistant przywracany jest ostatni stan encji, który trafia do bufora i jest **wysyłany do PLC** jedną ramką w ok. 1 s po starcie (po przywróceniu wszystkich encji listy; tylko gdy lista jest wysyłana automatycznie, czyli ma `on_change` albo `update_interval > 0`). Gdy nie ma zapisanego stanu (np. pierwsze uruchomienie), obowiązuje `initial_value`.

Domyślnie (bez `restore_value` i jawnego `initial_value`) po starcie wysyłane są wartości domyślne, np. zera. Żeby temu zapobiec, użyj blokady wysyłki:

- **lista pakowana:** `require_values: true` – lista nie jest wysyłana (także cyklicznie i przez usługę `send_list`), dopóki **każda** zmienna nie ma wartości,
- **lista niepakowana:** `require_value: true` przy zmiennej – ramka tej zmiennej jest pomijana, dopóki zmienna nie ma wartości; pozostałe zmienne są wysyłane normalnie.

Zmienna „ma wartość”, gdy: podano jej `initial_value` jawnie, przywrócono jej stan (`restore_value`) albo ustawiono ją w czasie pracy (z interfejsu lub automatyzacji). Różnica między trybami wynika z budowy ramek: lista pakowana jest wysyłana jako jedna ramka, więc blokada dotyczy całej listy, a lista niepakowana składa się z niezależnych ramek. Pominięcie wysyłki jest zgłaszane w logu (ostrzeżenie, najwyżej raz na minutę).

Przykład listy zapisu, która nie wyśle niczego, dopóki sterownik nie dostanie konkretnych wartości:

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    list_id: 126
    mode: write
    on_change: true
    require_values: true
    variables:
      - name: "Pompa"
        unique_id: pompa
        offset: 0
        type: BOOL
        entity: switch
        restore_value: true
      - name: "Temperatura zadana"
        unique_id: temp_zadana
        offset: 1
        type: REAL
        entity: number
        min: 0
        max: 100
        initial_value: 20.0
        restore_value: true
```

### Broadcast i wysyłka do siebie

Wysyłka na `255.255.255.255` wymaga, aby Home Assistant miał dostęp do sieci lokalnej. Broadcast wysłany na port, na którym ten sam Home Assistant nasłuchuje listą `read`, wraca do tego hosta. Integracja rozpoznaje własne, niedawno wysłane ramki (po porcie źródłowym gniazda wysyłającego i treści ramki) i **pomija** je: nie są dekodowane ani zliczane w `rejected_packets`. Oznacza to, że lista `read` w tym samym Home Assistant nie odczyta danych z listy `write` wysłanej przez ten sam Home Assistant (np. do testów trzeba użyć drugiego urządzenia).

## Różnice względem integracji ESPHome

Konfiguracja listy i zmiennych (nazwy, domyślne wartości, reguły) jest taka sama w obu platformach, a ramki, walidacja (w tym `rejected_packets`), konwersje wartości, `on_change`/`min_interval`/`update_interval`, restore i blokady wysyłki działają tak samo. Pozostałe różnice wynikają z platform:

| Obszar | Home Assistant | ESPHome |
|--------|----------------|---------|
| Identyfikator listy | brak | opcjonalne `id` (do lambd i akcji) |
| Dodatkowe parametry encji | `visible_by_default`, `suggested_unit_of_measurement` | cały schemat encji ESPHome (`filters`, `on_value`, `internal`, `web_server`, ...) |
| Wysyłka na żądanie | usługa `wago_netvar.send_list` | akcja `wago_netvar.send` lub `send_now()` |
| Przywracanie stanu | `RestoreEntity` Home Assistant | pamięć nieulotna ESPHome (klucz: `unique_id`) |
| Precyzja liczb 32-bitowych | dokładna (liczby całkowite Pythona) | `float` (do 16 777 216 dokładnie) |
| REAL będący NaN/Inf przy odbiorze | ramka przyjęta, stan encji bez zmian, `rx_errors` +1 | stan „unknown” (NaN) |
| Własny broadcast na ten sam port | rozpoznawany i pomijany przez listy `read` | nie dotyczy (inne urządzenie) |
| Walidacja konfiguracji | błędna lista jest pomijana, reszta działa | błąd odrzuca całą konfigurację (kompilacja) |
| Stan po `timeout` | `unavailable` | `unknown` (`binary_sensor`/`text_sensor`: o ile wersja ESPHome ma `invalidate_state()`) |

## Zmiany w wersji 1.3.0 (łącznie ze zmianami 1.2.0)

- Konfiguracja wyłącznie ręczna (YAML): usunięto config flow oraz pliki `config_flow.py`, `translations/en.json` i `translations/pl.json`; stałe (`const.py`) scalono z kodekiem (`codec.py`). Opisy usługi `send_list` są w `services.yaml`.
- **Walidacja per lista:** błędna lista jest pomijana (komunikat w logu), pozostałe działają. Wcześniej błąd w jednej liście wyłączał całą integrację.
- **Osobne gniazdo wysyłające** (port lokalny przydzielony przez system) dla list `write`; hub portu służy tylko do odbioru. Własny broadcast wracający do list `read` jest rozpoznawany i pomijany (nie psuje `rejected_packets`).
- **`unique_id` encji:** wyznaczany z nazwy zmiennej albo podawany ręcznie, powtórzenia są błędem. Format identyfikatora zmienił się (patrz „Identyfikatory encji”).
- **Przywracanie stanu i blokada wysyłki:** `restore_value`, `require_values` (lista pakowana), `require_value` (lista niepakowana); `initial_value` podane jawnie oznacza, że zmienna ma wartość od startu.
- **Typy czasowe** (TIME, DATE, TOD, DT) jako tekst IEC (`format: text`, domyślnie) albo surowa liczba (`format: raw`).
- **Czasy z jednostkami** (`"500ms"`, `"5s"`, `"2min"`, `never`) w `min_interval`, `update_interval` i `timeout`; liczby bez jednostki działają jak dotąd (ms / s).
- Aliasy nazw zgodne z ESPHome: `direction` (= `mode`) i `byte_offset` (= `offset`).
- Zapis STRING: encja `number` może sterować zmienną STRING (liczba jest zamieniana na tekst, tekst ucinany do `length`).
- STRING jest wyłącznie ASCII (wcześniej cp1250); bajty spoza ASCII są przy odczycie zamieniane na `?`.
- Zaokrąglanie przy zapisie wartości ułamkowych do typów całkowitych (wcześniej obcinanie części ułamkowej). BOOL przyjmuje także `yes`/`no`.
- Zliczanie `rejected_packets` zgodne z wersją ESPHome (ramki o nieobsługiwanym `list_id`, z niewłaściwego adresu nadawcy lub niezidentyfikowane są teraz zliczane, wcześniej były ignorowane). Ramka jest dekodowana przez każdą pasującą listę, a nie tylko jedną.
- Lista `read` z `ip_address: 255.255.255.255` jest błędem (adres nadawcy).
- Usunięto wycofaną opcję `transmit_checksum` (jej użycie jest teraz błędem „nieznane pole”).

## Zmiany w wersji 1.5.0

- Ramki z typem wiadomości (bajty 4-7, w dokumentacji 3S pole „ID”) różnym od `0` (potwierdzenia, prośby bootup, SDO) są odrzucane i zwiększają `rejected_packets`. Prośby bootup rozsyłane przez sterownik po restarcie będą więc widoczne w tym liczniku.
- Opis bajtów 18 (flagi) i 19 (suma kontrolna) rozdzielono zgodnie z dokumentacją protokołu.

## Zmiany w wersji 1.4.0

- **Konfiguracja ujednolicona z komponentem ESPHome:** te same nazwy parametrów i domyślne wartości. Nowe aliasy: `send_on_change` (= `on_change`). Dotychczasowe nazwy nadal działają.
- **Wysyłka przy zmianie:** tylko zmieniona zmienna w liście niepakowanej; `min_interval` liczony osobno dla każdej zmiennej; ustawienie tej samej wartości nie wywołuje wysyłki (wcześniej `set_variable` zawsze planował wysyłkę). Sprawdzono kombinacje `on_change`, `min_interval` i `update_interval` osobno i razem.
- **`sequence` przy wysyłce:** osobny licznik dla każdej zmiennej (lista niepakowana) albo jeden na listę (pakowana); startuje od 1.
- **Sensory diagnostyczne:** `rx_packets_<list_id>`, `rx_errors_<list_id>`, `rejected_packets_<list_id>` tylko dla list `read`, `tx_packets_<list_id>`, `tx_errors_<list_id>` tylko dla list `write`, oraz sumy `total_*`. Zmieniły się nazwy encji diagnostycznych (identyfikatory `unique_id` pozostały).
- Nowe parametry zmiennej: `visible_by_default`, `suggested_unit_of_measurement`, `inverted`.

## Ograniczenia

- Algorytm sumy kontrolnej nie jest znany.
- LREAL nie jest obsługiwany przez NetVar.
- DATE i DT są wyświetlane bez przeliczania strefy czasowej (tak, jak je przechowuje sterownik).
- Zmiana układu listy w PLC nie jest wykrywana automatycznie.
- Stan encji `switch`/`number` jest przywracany tylko przy `restore_value: true` (patrz „Wartości początkowe i przywracanie”).
- Lista `read` w tym samym Home Assistant nie odbiera ramek wysłanych przez listę `write` tego samego Home Assistant (własne ramki są pomijane).
- W liście pakowanej w trybie `write` zapis jednej zmiennej wysyła cały bufor.
- Format ramek TX wymaga dalszego potwierdzenia przechwyceniem pakietów.
- Nie ma mechanizmu retransmisji brakujących ramek.
- Ramki UDP nie są uwierzytelniane: przy `ip_address: 0.0.0.0` dowolny host w sieci może podszyć się pod PLC, a listę `write` odbierze każdy host nasłuchujący na danym porcie. Używaj w zaufanej sieci.
