
# Wago NetVar UDP - Home Assistant

Integracja Home Assistant do komunikacji UDP ze sterownikami WAGO / CoDeSys wykorzystujacymi protokol NetVar UDP (.S3).

## Funkcje

- Odbieranie danych z PLC.
- Wysylanie danych z Home Assistant do PLC.
- Tryb `read` oraz `write`.
- Obsluga pakietow pakowanych i niepakowanych.
- Obsluga wielu list NetVar.
- Obsluga wielu sterownikow.
- Konfiguracja YAML.
- Konfiguracja przez interfejs Home Assistant.
- Kodowanie little-endian.
- Aktualizacja encji po kazdej poprawnej ramce UDP.
- Diagnostyka kompletności listy.
- Informacja o numerze cyklu i brakujacych indeksach zmiennych.
- Obsluga 16-bitowego licznika `sequence`, w tym jego przepełnienia.
- Rozpoznawanie cofniecia numeracji jako restartu PLC.

## Obslugiwane typy

| Typ | Rozmiar | Interpretacja |
|---|---:|---|
| BOOL | 1 bajt | 0 = false, wartosc niezerowa = true |
| BYTE | 1 bajt | unsigned, 0..255 |
| INT | 2 bajty | signed, -32768..32767 |
| UINT | 2 bajty | unsigned, 0..65535 |
| DINT | 4 bajty | signed |
| UDINT | 4 bajty | unsigned |
| DWORD | 4 bajty | unsigned |
| REAL | 4 bajty | IEEE 754 float |

Wszystkie typy wielobajtowe sa kodowane w kolejnosci little-endian.

Konwersja wartosci liczbowej na typ calkowity wykorzystuje `int()`.
Czesc ulamkowa jest obcinana w kierunku zera.

Przyklad:
- `12.9` -> `12`
- `-12.9` -> `-12`

## Obsluga BOOL

Typ `BOOL` zajmuje zawsze **jeden pelny bajt payload**.

Nie jest stosowane pakowanie zmiennych BOOL w pojedyncze bity bajtu. Kazda zmienna BOOL ma wlasny bajt w buforze danych PLC.

Nie stosuje sie `bit_offset`. Pozycje zmiennych okresla wylacznie parametr `offset`, podawany w bajtach.

### Odczyt BOOL z PLC

W trybie `read` wartosc BOOL jest odczytywana z jednego bajtu payload:

| Wartosc bajtu | Wartosc logiczna |
|---|---|
| `0x00` | `false` |
| `0x01` | `true` |
| Inna wartosc niezerowa | `true` |

W trybie niepakowanym ramka zawierajaca jedna zmienna BOOL ma:
- 20 bajtow naglowka,
- 1 bajt payload,
- lacznie 21 bajtow.

W trybie pakowanym kazda zmienna BOOL zajmuje jeden bajt w buforze calej listy.

### Zapis BOOL do PLC

W trybie `write` Home Assistant koduje wartosc logiczna do jednego bajtu:

| Wartosc logiczna | Bajt wysylany do PLC |
|---|---|
| `false` | `0x00` |
| `true` | `0x01` |

W trybie niepakowanym wysylana ramka zawiera jeden bajt payload dla zmiennej BOOL.

W trybie pakowanym wartosc BOOL jest zapisywana pod odpowiednim offsetem w buforze calej listy. Pozostale bajty bufora nie sa przesuwane ani modyfikowane przez zapis tej zmiennej.

### Rozmieszczenie BOOL w payload

Przykladowa lista:

| Zmienna | Typ | Offset | Rozmiar |
|---|---|---:|---:|
| Pompa | BOOL | 0 | 1 bajt |
| Alarm | BOOL | 1 | 1 bajt |
| Temperatura | REAL | 2 | 4 bajty |
| Licznik | DWORD | 6 | 4 bajty |

Rozmieszczenie bajtow:

```text
Offset:    0       1       2       3       4       5       6       7       8       9
Payload:  BOOL    BOOL    REAL            ...             DWORD
```

W powyzszym przykladzie:
- `Pompa` zajmuje bajt 0.
- `Alarm` zajmuje bajt 1.
- `Temperatura` zajmuje bajty 2-5.
- `Licznik` zajmuje bajty 6-9.
- Calkowity rozmiar payload wynosi 10 bajtow.

Dwie zmienne BOOL zajmuja zatem dwa bajty, a nie jeden bajt z dwoma bitami.

**Wazne:** offset nastepnej zmiennej musi uwzgledniac pelny bajt zajmowany przez kazda zmienna BOOL.

## Instalacja

Skopiuj katalog:

`custom_components/wago_netvar`

do katalogu konfiguracji Home Assistant:

`config/custom_components/wago_netvar`

Nastepnie uruchom ponownie Home Assistant.

## Konfiguracja YAML

### Przyklad listy odczytowej

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    port: 1202
    list_id: 123
    mode: read
    pack_variables: true
    transmit_checksum: false

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

      - name: "Alarm"
        offset: 5
        type: BOOL
        entity: binary_sensor
```

### Przyklad listy zapisu

```yaml
wago_netvar:
  - ip_address: "192.168.17.45"
    port: 1202
    list_id: 124
    mode: write
    pack_variables: false
    transmit_checksum: false

    variables:
      - name: "Pompa"
        offset: 0
        type: BOOL
        entity: switch
        initial_value: false

      - name: "Alarm"
        offset: 1
        type: BOOL
        entity: switch
        initial_value: false

      - name: "Temperatura zadana"
        offset: 2
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
| port | Port UDP, domyslnie 1202 |
| list_id | Identyfikator listy NetVar |
| mode | `read` albo `write` |
| pack_variables | `true` - caly bufor w jednej ramce; `false` - osobna ramka dla zmiennej |
| transmit_checksum | Ustawienie dotyczace checksum w transmisji |

### Parametry zmiennej

| Parametr | Znaczenie |
|---|---|
| name | Nazwa encji |
| offset | Pozycja w buforze w bajtach |
| type | Typ danych PLC |
| entity | `sensor`, `binary_sensor`, `switch` albo `number` |
| initial_value | Poczatkowa wartosc bufora w trybie write |
| min | Minimalna wartosc encji number |
| max | Maksymalna wartosc encji number |
| step | Krok encji number |
| device_class | Klasa urzadzenia |
| state_class | Klasa stanu sensora |
| unit_of_measurement | Jednostka |
| icon | Ikona |
| zero_as_unavailable | Traktowanie zera jako braku wartosci sensora |

Nie uzywa sie `bit_offset` ani `big_endian`.

## Aktualizacja danych i cykle NetVar

Integracja aktualizuje dane po kazdej poprawnej ramce UDP.

W trybie niepakowanym kazda ramka zawiera dane jednej zmiennej. Po jej odebraniu odpowiednia encja jest aktualizowana natychmiast. Nie trzeba czekac na odebranie wszystkich zmiennych z listy.

Pozostale encje zachowuja ostatnie odebrane wartosci. Brak ramki dla danej zmiennej nie powoduje wyzerowania jej wartosci.

W trybie pakowanym jedna ramka zawiera dane calego skonfigurowanego bufora listy. Po odebraniu poprawnej ramki aktualizowane sa encje wszystkich zmiennych.

### Numer sequence

Pole `sequence` jest 16-bitowym numerem cyklu listy.

Wszystkie ramki nalezace do tego samego cyklu maja ten sam numer `sequence`.

Zasady obslugi:

- Pierwsza odebrana ramka rozpoczyna cykl.
- Kolejne ramki z tym samym numerem `sequence` naleza do tego samego cyklu.
- Zmiana numeru `sequence` rozpoczyna nowy cykl.
- Przejscie z `65535` na `0` jest traktowane jako normalne przepełnienie licznika.
- Cofniecie numeracji, ktore nie jest normalnym przepełnieniem, jest traktowane jako restart licznika PLC.
- Po wykryciu restartu rozpoczyna sie nowy cykl diagnostyczny.

Integracja nie wymaga, aby pierwszy odebrany numer cyklu wynosil `0` lub `1`.

Nie jest wymagane odebranie wszystkich ramek poprzedniego cyklu przed rozpoczeciem kolejnego. Jezeli jakas ramka nie dotrze, zmienna zostanie wykazana jako brakujaca w diagnostyce biezacego cyklu.

### Automatyczny sensor diagnostyczny

Dla kazdej listy w trybie `read` integracja tworzy dodatkowy sensor diagnostyczny kompletności listy.

Stan:
- `complete` - odebrano wszystkie zmienne z biezacego cyklu.
- `incomplete` - nie odebrano jeszcze wszystkich zmiennych z biezacego cyklu.

Atrybuty diagnostyczne powinny obejmowac:
- `list_id` - identyfikator listy.
- `sequence` - numer biezacego cyklu.
- `received_count` - liczba odebranych zmiennych w cyklu.
- `expected_count` - liczba skonfigurowanych zmiennych.
- `received_indices` - indeksy odebranych zmiennych.
- `missing_indices` - indeksy brakujacych zmiennych.
- `ever_received_count` - liczba zmiennych odebranych przynajmniej raz.
- `packed` - tryb pakowania.
- `checksum_field` - wartosc pola checksum z ostatniej ramki.

W trybie niepakowanym kompletność cyklu jest obliczana na podstawie liczby roznych indeksow odebranych dla tego samego numeru `sequence`.

Przyklad dla listy zawierajacej 12 zmiennych:

- Po pierwszej ramce: `received_count: 1`, `expected_count: 12`.
- Po odebraniu szesciu roznych zmiennych: `received_count: 6`.
- Po odebraniu wszystkich dwunastu zmiennych: stan `complete`.

Po rozpoczeciu nowego cyklu licznik odebranych zmiennych jest liczony od nowa. Wartosci encji pozostaja bez zmian do czasu odebrania kolejnych ramek.

## Struktura ramki NetVar UDP

Przechwycone ramki maja sygnature:

`00 2D 53 33`

Naglowek ma 20 bajtow.

| Offset | Rozmiar | Znaczenie |
|---:|---:|---|
| 0 | 4 bajty | Sygnatura `00 2D 53 33` |
| 4 | 4 bajty | Pole nieznane / zarezerwowane |
| 8 | 2 bajty | List ID |
| 10 | 2 bajty | Indeks zmiennej |
| 12 | 2 bajty | Liczba zmiennych |
| 14 | 2 bajty | Dlugosc calej ramki |
| 16 | 2 bajty | Numer sequence / cyklu |
| 18 | 2 bajty | Pole checksum lub pole kontrolne |
| 20 | zmienna | Dane zmiennej lub bufor listy |

Wszystkie wielobajtowe pola naglowka sa zapisane little-endian.

### List ID

Identyfikator listy NetVar.

### Indeks zmiennej

W trybie niepakowanym indeks wskazuje pozycje zmiennej na skonfigurowanej liscie. Indeksowanie rozpoczyna sie od zera.

W trybie pakowanym indeks wynosi zero.

### Liczba zmiennych

W trybie pakowanym pole zawiera liczbe wszystkich zmiennych na liscie.

Przyklad:
- 11 zmiennych: `0B 00`
- 12 zmiennych: `0C 00`

W trybie niepakowanym pole ma wartosc `1` w kazdej ramce. Nie oznacza ono liczby wszystkich zmiennych na liscie.

Liczbe oczekiwanych ramek okresla konfiguracja Home Assistant.

### Dlugosc ramki

Pole zawiera calkowita dlugosc ramki UDP, lacznie z 20-bajtowym naglowkiem.

Przyklady:
- BOOL: 21 bajtow.
- BYTE: 21 bajtow.
- INT / UINT: 22 bajty.
- DINT / UDINT / DWORD / REAL: 24 bajty.

W trybie pakowanym dlugosc zalezy od rozmiaru skonfigurowanego bufora.

### Sequence

Pole 16-17 jest numerem cyklu listy, a nie indeksem zmiennej.

Numer jest 16-bitowy i moze zawijac sie z 65535 do 0.

Zmiana numeru sequence rozpoczyna nowy cykl diagnostyczny. Cofniecie numeracji jest traktowane jako restart PLC, z wyjatkiem normalnego przejscia przez granice licznika `65535 -> 0`.

### Dane i rozmiary ramek

Dane zaczynaja sie od offsetu 20.

W trybie niepakowanym:

- BOOL: 1 bajt danych, cala ramka 21 bajtow.
- BYTE: 1 bajt danych, cala ramka 21 bajtow.
- INT / UINT: 2 bajty danych, cala ramka 22 bajty.
- DINT / UDINT / DWORD / REAL: 4 bajty danych, cala ramka 24 bajty.

W trybie pakowanym dane zawieraja skonfigurowany bufor listy.

Pozycje zmiennych okreslaja ich `offset` i `type`.

Kazda zmienna BOOL zajmuje jeden bajt payload. Nie stosuje sie bitowego pakowania zmiennych BOOL.

Przyklad DWORD:

Wartosc PLC:

`16#AABBCCDD`

Dane w ramce:

`DD CC BB AA`

Przyklad REAL jest kodowany jako 32-bit IEEE 754 little-endian.

## Checksum / pole kontrolne

Znaczenie pola 18-19 nie zostalo jeszcze w pelni ustalone.

Nie jest obecnie implementowane obliczanie ani weryfikacja algorytmu checksum.

### Tryb checksum wylaczony

W przechwyconych ramkach z wylaczona checksum pole 18-19 ma wartosc:

`00 00`

### Tryb niepakowany z checksum

W dotychczasowych przechwyceniach zaobserwowano stale wartosci zalezne od typu zmiennej:

| Typ | Bajty 18-19 |
|---|---|
| BOOL | `02 52` |
| BYTE | `02 78` |
| DWORD | `02 28` |

Wartosci pozostawaly takie same dla roznych wartosci danych oraz roznych indeksow zmiennych.

### Tryb pakowany z checksum

Zaobserwowano:

| Liczba zmiennych i typy | Pole 18-19 |
|---|---|
| 11 zmiennych: 5 BOOL, 4 DWORD, 2 BYTE | `02 DB` |
| 12 zmiennych: 5 BOOL, 4 DWORD, 3 BYTE | `02 B3` |

Dla listy 12 zmiennych wartosc `02 B3` pozostawala niezmienna:
- po zmianie wartosci zmiennych,
- przy kolejnych numerach sequence 3, 4 i 5.

Nie wiadomo jeszcze, czy pole zalezy od konfiguracji listy, typow, kolejnosci zmiennych, naglowka lub innego parametru.

Nie nalezy traktowac tych wartosci jako potwierdzonego algorytmu CRC ani sumy kontrolnej.

### Wysylanie ramek z checksum

Generowanie checksum dla ramek wysylanych przez Home Assistant nie jest zaimplementowane, poniewaz algorytm nie zostal potwierdzony.

Ustawienie `transmit_checksum: true` w trybie `write` powoduje odmowe wyslania ramki zamiast wysylania niepoprawnej wartosci pola kontrolnego.

## Ograniczenia

- Algorytm checksum nie jest jeszcze rozpoznany.
- Weryfikacja checksum odebranych ramek nie jest wykonywana.
- Generowanie checksum dla ramek wysylanych nie jest zaimplementowane.
- `initial_value` inicjalizuje bufor zapisu, ale nie jest automatycznie wysylane do PLC podczas uruchamiania Home Assistant.
- Format ramek TX wymaga dalszego potwierdzenia przechwyceniem pakietow wysylanych z Home Assistant do PLC.
- Nie ma potwierdzonego mechanizmu retransmisji brakujacych ramek.
- Diagnostyka kompletności dotyczy odebranych ramek i nie gwarantuje, ze PLC wyslalo wszystkie zmienne.
- BOOL zajmuje jeden bajt payload. Nie jest stosowane bitowe pakowanie zmiennych BOOL.

