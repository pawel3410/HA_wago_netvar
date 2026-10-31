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
- Automatyczny sensor diagnostyczny kompletności listy.
- Informacja o numerze cyklu i brakujących indeksach zmiennych.
- Obsługa 16-bitowego licznika `sequence`, w tym jego przepełnienia.
- Rozpoznawanie cofnięcia numeracji jako restartu PLC.

## Obsługiwane typy

Typy odpowiadają typom elementarnym CODESYS 2.3. Wszystkie typy wielobajtowe są kodowane w kolejności little-endian.

| Typ | Rozmiar | Interpretacja | Encje | Potwierdzone przechwyceniem |
|---|---:|---|---|:---:|
| BOOL | 1 bajt | `00` = false, wartość niezerowa = true. Zajmuje cały bajt, nie pojedynczy bit | `binary_sensor`, `switch` | tak |
| BYTE | 1 bajt | bez znaku, 0..255 | `sensor`, `number` | tak |
| USINT | 1 bajt | bez znaku, 0..255 | `sensor`, `number` | tak |
| SINT | 1 bajt | ze znakiem, -128..127 | `sensor`, `number` | tak |
| WORD | 2 bajty | bez znaku, 0..65535 | `sensor`, `number` | tak |
| UINT | 2 bajty | bez znaku, 0..65535 | `sensor`, `number` | tak |
| INT | 2 bajty | ze znakiem, -32768..32767 | `sensor`, `number` | tak |
| DWORD | 4 bajty | bez znaku, 0..4294967295 | `sensor`, `number` | tak |
| UDINT | 4 bajty | bez znaku, 0..4294967295 | `sensor`, `number` | tak |
| DINT | 4 bajty | ze znakiem | `sensor`, `number` | tak |
| REAL | 4 bajty | IEEE 754 (float 32-bit) | `sensor`, `number` | tak |
| TIME | 4 bajty | czas trwania w milisekundach, liczba bez znaku (np. `DC 05 00 00` = 1500 ms) | `sensor`, `number` | tak |
| DATE | 4 bajty | surowa liczba bez znaku (wg CODESYS: sekundy od 1970-01-01) | `sensor`, `number` | nie |
| TOD (`TIME_OF_DAY`) | 4 bajty | surowa liczba bez znaku (wg CODESYS: milisekundy od północy) | `sensor`, `number` | nie |
| DT (`DATE_AND_TIME`) | 4 bajty | surowa liczba bez znaku (wg CODESYS: sekundy od 1970-01-01) | `sensor`, `number` | nie |
| STRING | długość + 1 bajt | tekst ASCII / cp1250, zakończony bajtem `00` | `sensor` (tylko odczyt) | tak |

Uwagi:

- **LREAL nie jest obsługiwany.** Sterownik nie przyjmuje tego typu na listach zmiennych sieciowych (błąd *LREAL not supported* przy kompilacji).
- **DATE, TOD i DT** są dekodowane jako surowe liczby bez znaku. Nie są zamieniane na datę ani godzinę, a ich rozmiar wynika ze specyfikacji CODESYS, a nie z przechwyconych ramek.
- **Aliasy:** `TIME_OF_DAY` jest traktowany jak `TOD`, a `DATE_AND_TIME` jak `DT`.
- **BOOL zawsze zajmuje pełny bajt**, także w liście pakowanej. Nie ma adresowania bitowego, dlatego nie używa się `bit_offset` ani `big_endian`.
- **STRING(n) zajmuje n + 1 bajtów.** Długość podaje parametr `length` (domyślnie 80, zakres 1..255, taka sama jak w deklaracji PLC). Tekst kończy się na pierwszym bajcie `00`. Bajty za nim to nieczyszczona pamięć sterownika i mogą zawierać dowolne wartości, więc integracja je ignoruje. Zapis STRING z Home Assistant nie jest obsługiwany.
- Konwersja wartości liczbowej na typ całkowity wykorzystuje `int()`. Część ułamkowa jest obcinana w kierunku zera (`12.9` -> `12`, `-12.9` -> `-12`).

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

W tym przykładzie bufor ma 5 + 21 = 26 bajtów.

### Przykład listy zapisu

```yaml
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
```

### Parametry listy

| Parametr | Znaczenie |
|---|---|
| ip_address | Adres IP PLC |
| port | Port UDP, domyślnie 1202 |
| list_id | Identyfikator listy NetVar |
| mode | `read` albo `write` |
| pack_variables | `true` - cały bufor w jednej ramce; `false` - osobna ramka dla zmiennej |

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

W trybie niepakowanym każda ramka zawiera dane jednej zmiennej. Po jej odebraniu odpowiednia encja jest aktualizowana natychmiast. Nie trzeba czekać na odebranie wszystkich zmiennych z listy.

Pozostałe encje zachowują ostatnie odebrane wartości. Brak ramki dla danej zmiennej nie powoduje wyzerowania jej wartości.

W trybie pakowanym jedna ramka zawiera dane całego skonfigurowanego bufora listy. Po odebraniu poprawnej ramki aktualizowane są encje wszystkich zmiennych. Lista pakowana musi być skonfigurowana w całości (wszystkie zmienne w kolejności deklaracji PLC), bo liczba zmiennych i długość danych muszą zgadzać się z ramką.

### Numer sequence

Pole `sequence` jest 16-bitowym numerem cyklu listy.

Wszystkie ramki należące do tego samego cyklu mają ten sam numer `sequence`.

Zasady obsługi:

- Pierwsza odebrana ramka rozpoczyna cykl.
- Kolejne ramki z tym samym numerem `sequence` należą do tego samego cyklu.
- Zmiana numeru `sequence` rozpoczyna nowy cykl.
- Przejście z `65535` na `0` jest traktowane jako normalne przepełnienie licznika.
- Cofnięcie numeracji, które nie jest normalnym przepełnieniem, jest traktowane jako restart licznika PLC.
- Po wykryciu restartu rozpoczyna się nowy cykl diagnostyczny.

Integracja nie wymaga, aby pierwszy odebrany numer cyklu wynosił `0` lub `1`.

Nie jest wymagane odebranie wszystkich ramek poprzedniego cyklu przed rozpoczęciem kolejnego. Jeżeli jakaś ramka nie dotrze, zmienna zostanie wykazana jako brakująca w diagnostyce bieżącego cyklu.

### Automatyczny sensor diagnostyczny

Dla każdej listy w trybie `read` integracja tworzy dodatkowy sensor diagnostyczny:

`sensor.netvar_list_<list_id>_packet_status`

Rzeczywisty identyfikator encji zależy od nazwy nadanej przez Home Assistant.

Stan:

- `complete` - odebrano wszystkie zmienne z bieżącego cyklu.
- `incomplete` - nie odebrano jeszcze wszystkich zmiennych z bieżącego cyklu.

Atrybuty:

- `list_id` - identyfikator listy.
- `sequence` - numer bieżącego cyklu.
- `received_count` - liczba odebranych zmiennych w cyklu.
- `expected_count` - liczba skonfigurowanych zmiennych.
- `received_indices` - indeksy odebranych zmiennych.
- `missing_indices` - indeksy brakujących zmiennych.
- `ever_received_count` - liczba zmiennych odebranych przynajmniej raz.
- `packed` - tryb pakowania.
- `checksum_field` - bajty 18-19 z ostatniej ramki w kolejności z ramki, np. `02 DB` (tylko informacyjnie, patrz „Suma kontrolna”).

W trybie niepakowanym kompletność cyklu jest obliczana na podstawie liczby różnych indeksów odebranych dla tego samego numeru `sequence`.

Przykład dla listy zawierającej 12 zmiennych:

- Po pierwszej ramce: `received_count: 1`, `expected_count: 12`.
- Po odebraniu sześciu różnych zmiennych: `received_count: 6`.
- Po odebraniu wszystkich dwunastu zmiennych: stan `complete`.

Po rozpoczęciu nowego cyklu licznik odebranych zmiennych jest liczony od nowa. Wartości encji pozostają bez zmian do czasu odebrania kolejnych ramek.

Sensor diagnostyczny jest tworzony automatycznie. Nie trzeba dodawać go ręcznie do konfiguracji.

## Struktura ramki NetVar UDP

Przechwycone ramki mają sygnaturę:

`00 2D 53 33`

Nagłówek ma 20 bajtów. Każdy datagram UDP zawiera dokładnie jedną ramkę.

| Offset | Rozmiar | Znaczenie |
|---:|---:|---|
| 0 | 4 bajty | Sygnatura `00 2D 53 33` |
| 4 | 4 bajty | Pole zarezerwowane (zawsze `00 00 00 00` w przechwyceniach) |
| 8 | 2 bajty | List ID |
| 10 | 2 bajty | Indeks zmiennej |
| 12 | 2 bajty | Liczba zmiennych |
| 14 | 2 bajty | Długość całej ramki |
| 16 | 2 bajty | Numer sequence / cyklu |
| 18 | 1 bajt | Flagi: `00` bez sumy kontrolnej, `02` z sumą kontrolną |
| 19 | 1 bajt | Suma kontrolna (`00`, gdy wyłączona) |
| 20 | zmienna | Dane zmiennej lub bufor listy |

Wszystkie wielobajtowe pola nagłówka są zapisane little-endian.

### List ID

Identyfikator listy NetVar (16-bitowy), taki jak ustawiony w CODESYS jako COB-ID listy.

### Indeks zmiennej

W trybie niepakowanym indeks wskazuje pozycję zmiennej na skonfigurowanej liście, w kolejności deklaracji w PLC. Indeksowanie rozpoczyna się od zera. Zmienne w konfiguracji muszą więc być wpisane w tej samej kolejności co w PLC.

W trybie pakowanym indeks wynosi zero.

### Liczba zmiennych

W trybie pakowanym pole zawiera liczbę wszystkich zmiennych na liście.

Przykład:
- 11 zmiennych: `0B 00`
- 12 zmiennych: `0C 00`

W trybie niepakowanym pole ma wartość `1` w każdej ramce. Nie oznacza ono liczby wszystkich zmiennych na liście.

Liczbę oczekiwanych ramek określa konfiguracja Home Assistant.

### Długość ramki

Pole zawiera całkowitą długość ramki UDP, łącznie z 20-bajtowym nagłówkiem.

Przykłady:
- BOOL, BYTE, SINT, USINT: 21 bajtów.
- INT, UINT, WORD: 22 bajty.
- DINT, UDINT, DWORD, REAL, TIME: 24 bajty.
- STRING(10): 31 bajtów, STRING(80): 101 bajtów.

W trybie pakowanym długość zależy od rozmiaru skonfigurowanego bufora.

### Sequence

Pole 16-17 jest numerem cyklu listy, a nie indeksem zmiennej.

Przykłady zaobserwowane w przechwyceniach:
- `18 00` = sequence 24.
- `19 00` = sequence 25.
- `01 00` = sequence 1.
- `02 00` = sequence 2.
- `03 00` = sequence 3.
- `04 00` = sequence 4.
- `05 00` = sequence 5.

Numer jest 16-bitowy i może zawijać się z 65535 do 0.

Zmiana numeru sequence rozpoczyna nowy cykl diagnostyczny. Cofnięcie numeracji jest traktowane jako restart PLC, z wyjątkiem normalnego przejścia przez granicę licznika `65535 -> 0`.

W przechwyceniach cykl powtarzał się co około 5-10 s (zależnie od ustawień PLC), a ramki jednego cyklu następowały po sobie w odstępach 5-30 ms.

### Dane i rozmiary ramek

Dane zaczynają się od offsetu 20.

W trybie niepakowanym:

- BOOL, BYTE, SINT, USINT: 1 bajt danych, cała ramka 21 bajtów.
- INT / UINT / WORD: 2 bajty danych, cała ramka 22 bajty.
- DINT / UDINT / DWORD / REAL / TIME / DATE / TOD / DT: 4 bajty danych, cała ramka 24 bajty.
- STRING(n): n + 1 bajtów danych.

W trybie pakowanym dane zawierają skonfigurowany bufor listy: zmienne występują w kolejności deklaracji, jedna za drugą, **bez wyrównania i bez dopełnienia**. Offset zmiennej to suma rozmiarów wszystkich poprzednich zmiennych (np. DWORD po trzech BOOL zaczyna się na offsecie 3).

Pozycje zmiennych określają ich `offset` i `type`.

Przykład DWORD:

Wartość PLC:

`16#AABBCCDD`

Dane w ramce:

`DD CC BB AA`

REAL jest kodowany jako 32-bitowy IEEE 754 little-endian.

## Suma kontrolna

Lista NetVar w CODESYS ma opcję *Transmit checksum* (nadawanie) i *Check checksum* (odbiór). Poniższe informacje pochodzą z przechwyconych ramek (32 różne układy list). Algorytm sumy kontrolnej nie jest znany, dlatego **integracja nie oblicza ani nie weryfikuje sumy kontrolnej.**

### Co zaobserwowano

- Bajt 18 ma wartość `00` przy wyłączonej sumie kontrolnej i `02` przy włączonej.
- Bajt 19 ma wartość `00` przy wyłączonej sumie kontrolnej, a przy włączonej niesie sumę.
- Suma jest **stała dla danego układu listy**. Nie zmienia się przy zmianie wartości zmiennych ani przy kolejnych cyklach.
- Suma **nie zależy** od: wartości zmiennych, numeru sequence, nazw zmiennych, List ID, trybu pakowania (dla pojedynczej zmiennej) ani od długości STRING.
- Suma **zależy** od sekwencji typów zmiennych: ich rodzajów, kolejności i liczby. Przykładowo `[BOOL, BYTE]` daje `CE`, a `[BYTE, BOOL]` daje `51`.
- W trybie niepakowanym każda ramka ma sumę właściwą dla typu jednej zmiennej. W trybie pakowanym ramka niesie jedną sumę dla całego układu listy.
- Kilka przetestowanych wariantów CRC-8 (po kodach typów i po nazwach typów) nie pasuje do danych. Z obecnych danych algorytmu nie udało się odtworzyć.

### Zmierzone sumy (bajt 19, przy fladze `02`)

Pojedyncze zmienne:

| Typ | Suma | Typ | Suma |
|---|---|---|---|
| BOOL | `52` | INT | `A5` |
| BYTE | `78` | UINT | `6F` |
| WORD | `4C` | DINT | `05` |
| DWORD | `28` | UDINT | `BA` |
| SINT | `3D` | REAL | `9F` |
| USINT | `0F` | TIME | `5B` |
| | | STRING (dowolna długość) | `DD` |

Listy pakowane:

| Układ | Suma |
|---|---|
| `[BOOL ×2]` | `2D` |
| `[BOOL ×3]` | `2D` |
| `[BOOL ×4]` | `61` |
| `[BOOL ×5]` | `FD` |
| `[BOOL ×8]` | `D0` |
| `[BOOL ×16]` | `49` |
| `[BYTE ×2]` | `E1` |
| `[BYTE ×3]` | `FE` |
| `[BYTE ×4]` | `5E` |
| `[DWORD ×2]` | `58` |
| `[BOOL, BYTE]` | `CE` |
| `[BYTE, BOOL]` | `51` |
| `[BOOL, BOOL, BYTE]` | `57` |
| `[BOOL, BYTE, BOOL]` | `91` |
| `[BYTE, BOOL, BOOL]` | `4C` |
| `[BOOL, BYTE, BYTE]` | `34` |
| `[BOOL ×3, BYTE]` | `09` |
| `[BYTE, BYTE, BOOL]` | `31` |
| `[DWORD, BOOL]` | `8C` |
| `[BOOL ×3, DWORD ×4, BYTE ×2, BOOL ×2]` (11 zmiennych) | `DB` |
| `[BOOL ×3, BYTE, DWORD ×4, BYTE ×2, BOOL ×2]` (12 zmiennych) | `B3` |
| `[BOOL ×3, DWORD ×4, BYTE ×2, BOOL ×2, BYTE]` (12 zmiennych) | `37` |

### Zachowanie integracji

- **Odbiór:** bajty 18-19 są ignorowane. Ramki z włączoną sumą kontrolną są przyjmowane tak samo jak bez niej. Można więc włączyć *Transmit checksum* na listach nadających PLC.
- **Wysyłanie:** ramki z Home Assistant mają w bajtach 18-19 wartość `00 00`. Na listach odbiorczych w PLC musi być **wyłączone sprawdzanie sumy kontrolnej** (*Check checksum*), bo w przeciwnym razie PLC może odrzucać ramki.
- **Parametr `transmit_checksum` został usunięty** z konfiguracji YAML i z formularza UI. W istniejącej konfiguracji z `transmit_checksum: false` parametr jest po prostu pomijany. Konfiguracja listy `write` z `transmit_checksum: true` jest odrzucana z komunikatem o błędzie. Dla listy `read` jest ignorowana.
- **Diagnostyka:** atrybut `checksum_field` sensora statusu pokazuje bajty 18-19 ostatniej ramki (np. `02 DB`), a w logu debug są one wypisane jako `header_bytes_18_19`.
- Zmiana układu listy w PLC (np. dodanie zmiennej) zmienia sumę, ale nie jest wykrywana. Po zmianie deklaracji w PLC zaktualizuj konfigurację w Home Assistant.

## Konfiguracja przez UI

W formularzu integracji podaj:

- adres IP sterownika,
- port UDP,
- List ID,
- tryb `read` lub `write`,
- ustawienie `pack_variables`,
- zmienne wraz z ich typami, offsetami i encjami (dla typu `STRING` także długość).

## Ograniczenia

- Algorytm sumy kontrolnej nie jest znany: integracja jej nie oblicza ani nie weryfikuje (patrz „Suma kontrolna”).
- LREAL nie jest obsługiwany przez sterownik.
- STRING jest dostępny tylko do odczytu.
- DATE, TOD i DT są dekodowane jako surowe liczby i nie były potwierdzone przechwyceniem.
- Zmiana układu listy w PLC nie jest wykrywana.
- `initial_value` inicjalizuje bufor zapisu, ale nie jest automatycznie wysyłane do PLC podczas uruchamiania Home Assistant.
- W liście pakowanej w trybie `write` zapis jednej zmiennej wysyła cały bufor, w którym pozostałe zmienne mają wartości początkowe lub ostatnio zapisane z Home Assistant.
- Format ramek TX wymaga dalszego potwierdzenia przechwyceniem pakietów wysyłanych z Home Assistant do PLC.
- Nie ma potwierdzonego mechanizmu retransmisji brakujących ramek.
- Diagnostyka kompletności dotyczy odebranych ramek i nie gwarantuje, że PLC wysłało wszystkie zmienne.

## Ważne uwagi przed uruchomieniem

1. Sensor diagnostyczny będzie tworzony automatycznie dla każdej listy `read`. Nie trzeba dodawać go ręcznie do konfiguracji.
2. Po pierwszej ramce niepakowanej sensor może pokazać `incomplete`, np. `received_count: 1`, `expected_count: 12`.
3. Po odebraniu wszystkich 12 indeksów tego samego cyklu sensor pokaże `complete`.
4. Gdy rozpocznie się następny cykl, diagnostyka zacznie liczyć odebrane zmienne od nowa.
5. Encje zachowają ostatnie odebrane wartości, dopóki nie nadejdą ich nowe ramki.
6. Przejście numeru sequence z `65535` na `0` nie jest traktowane jako restart PLC.
7. Cofnięcie numeracji poza normalnym przepełnieniem licznika rozpoczyna nowy cykl diagnostyczny.
8. W Home Assistant zmienne STRING w liście pakowanej muszą mieć w konfiguracji tę samą `length` co w deklaracji PLC.
