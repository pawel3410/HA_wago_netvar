# Wago NetVar UDP - Home Assistant

Integracja Home Assistant do komunikacji UDP ze sterownikami
WAGO / CoDeSys wykorzystujacymi protokol NetVar UDP (.S3).

## Funkcje

- Odbieranie danych z PLC.
- Wysylanie danych z Home Assistant do PLC.
- Tryb `read` oraz `write`.
- Pakiety pakowane i niepakowane.
- Obsluga wielu list NetVar.
- Obsluga wielu sterownikow.
- Konfiguracja YAML.
- Konfiguracja przez interfejs Home Assistant.
- Kodowanie little-endian.
- Aktualizacja encji po kazdej poprawnej ramce UDP.
- Automatyczny sensor diagnostyczny kompletności listy.
- Informacja o numerze cyklu i brakujacych indeksach zmiennych.

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

## Instalacja

Skopiuj katalog:

`custom_components/wago_netvar`

do katalogu konfiguracji Home Assistant:

`config/custom_components/wago_netvar`

Nastepnie uruchom ponownie Home Assistant.

## Konfiguracja YAML

Przyklad listy odczytowej:

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
```

Przyklad listy zapisu:
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

Parametry listy
Parametr	Znaczenie
ip_address	Adres IP PLC
port	Port UDP, domyslnie 1202
list_id	Identyfikator listy NetVar
mode	read albo write
pack_variables	true - caly bufor w jednej ramce; false - osobna ramka dla zmiennej
transmit_checksum	Ustawienie dotyczace checksum w transmisji

Parametry zmiennej
Parametr	Znaczenie
name	Nazwa encji
offset	Pozycja w buforze w bajtach
type	Typ danych PLC
entity	sensor, binary_sensor, switch albo number
initial_value	Poczatkowa wartosc bufora w trybie write
min	Minimalna wartosc encji number
max	Maksymalna wartosc encji number
step	Krok encji number
device_class	Klasa urzadzenia
state_class	Klasa stanu sensora
unit_of_measurement	Jednostka
icon	Ikona
zero_as_unavailable	Traktowanie zera jako braku wartosci sensora

Nie uzywa sie bit_offset ani big_endian.
Automatyczny sensor diagnostyczny
Dla kazdej listy w trybie read integracja tworzy dodatkowy sensor:

sensor.netvar_list_<list_id>_packet_status

Rzeczywisty identyfikator encji zalezy od nazwy nadanej przez Home Assistant.

Stan:
- complete - odebrano wszystkie zmienne z biezacego cyklu.
- incomplete - nie odebrano jeszcze wszystkich zmiennych z biezacego cyklu.
Atrybuty:
- list_id - identyfikator listy.
- sequence - numer cyklu.
- received_count - liczba odebranych zmiennych w cyklu.
- expected_count - liczba skonfigurowanych zmiennych.
- received_indices - indeksy odebranych zmiennych.
- missing_indices - indeksy brakujacych zmiennych.
- ever_received_count - liczba zmiennych odebranych przynajmniej raz.
- packed - tryb pakowania.
- checksum_field - wartosc pola checksum z ostatniej ramki.
W trybie niepakowanym kazda poprawna ramka aktualizuje odpowiednia encje
natychmiast po odbiorze. Pozostale encje zachowuja ostatnia odebrana wartosc.

Kompletnosc cyklu jest obliczana na podstawie liczby roznych indeksow
odebranych dla tego samego numeru sequence.

Jesli zmieni sie numer sequence, rozpoczyna sie nowy cykl.
Nieodebrane zmienne poprzedniego cyklu pozostaja widoczne jako brakujace
w diagnostyce tego cyklu.
Struktura ramki NetVar UDP
Przechwycone ramki maja sygnature:

00 2D 53 33

Naglowek ma 20 bajtow.
Offset	Rozmiar	Znaczenie
0	4 bajty	Sygnatura 00 2D 53 33
4	4 bajty	Pole nieznane / zarezerwowane
8	2 bajty	List ID
10	2 bajty	Indeks zmiennej
12	2 bajty	Liczba zmiennych
14	2 bajty	Dlugosc calej ramki
16	2 bajty	Numer sequence / cyklu
18	2 bajty	Pole checksum lub pole kontrolne
20	zmienna	Dane zmiennej lub bufor listy

Wszystkie wielobajtowe pola naglowka sa zapisane little-endian.
List ID
Identyfikator listy NetVar.
Indeks zmiennej
W trybie niepakowanym indeks wskazuje pozycje zmiennej na skonfigurowanej
liscie. Indeksowanie rozpoczyna sie od zera.

W trybie pakowanym indeks wynosi zero.
Liczba zmiennych
W trybie pakowanym pole zawiera liczbe wszystkich zmiennych na liscie.

Przyklad:
- 11 zmiennych: 0B 00
- 12 zmiennych: 0C 00
W trybie niepakowanym pole ma wartosc 1 w kazdej ramce.
Nie oznacza ono liczby wszystkich zmiennych na liscie.
Liczbe oczekiwanych ramek okresla konfiguracja Home Assistant.
Dlugosc ramki
Pole zawiera calkowita dlugosc ramki UDP, lacznie z 20-bajtowym naglowkiem.

Przyklady:
- BOOL: 21 bajtow.
- BYTE: 21 bajtow.
- DWORD: 24 bajty.
W trybie pakowanym dlugosc zalezy od rozmiaru skonfigurowanego bufora.
Sequence
Pole 16-17 jest numerem cyklu listy, a nie indeksem zmiennej.

Przyklady zaobserwowane w przechwyceniach:
- 18 00 = sequence 24.
- 19 00 = sequence 25.
- 01 00 = sequence 1.
- 02 00 = sequence 2.
- 03 00 = sequence 3.
- 04 00 = sequence 4.
- 05 00 = sequence 5.
Numer jest 16-bitowy i moze zawijac sie z 65535 do 0.

Wszystkie zmienne z jednego cyklu maja ten sam numer sequence.
Dane i rozmiary ramek
Dane zaczynaja sie od offsetu 20.

W trybie niepakowanym:
- BOOL: 1 bajt danych, cala ramka 21 bajtow.
- BYTE: 1 bajt danych, cala ramka 21 bajtow.
- INT / UINT: 2 bajty danych, cala ramka 22 bajty.
- DINT / UDINT / DWORD / REAL: 4 bajty danych, cala ramka 24 bajty.
W trybie pakowanym dane zawieraja skonfigurowany bufor listy.
Pozycje zmiennych okreslaja ich offset i type.

Przyklad DWORD:

Wartosc PLC:

16#AABBCCDD

Dane w ramce:

DD CC BB AA

Przyklad REAL jest kodowany jako 32-bit IEEE 754 little-endian.
Checksum / pole kontrolne
Znaczenie pola 18-19 nie zostalo jeszcze w pelni ustalone.
Nie jest obecnie implementowane obliczanie ani weryfikacja algorytmu checksum.
Tryb checksum wylaczony
W przechwyconych ramkach z wylaczona checksum pole 18-19 ma wartosc:

00 00
Tryb niepakowany z checksum
W dotychczasowych przechwyceniach zaobserwowano stale wartosci zalezne
od typu zmiennej:
Typ	Bajty 18-19
BOOL	02 52
BYTE	02 78
DWORD	02 28

Wartosci pozostawaly takie same dla roznych wartosci danych oraz roznych
indeksow zmiennych.
Tryb pakowany z checksum
Zaobserwowano:
Liczba zmiennych i typy	Pole 18-19
11 zmiennych: 5 BOOL, 4 DWORD, 2 BYTE	02 DB
12 zmiennych: 5 BOOL, 4 DWORD, 3 BYTE	02 B3

Dla listy 12 zmiennych wartosc 02 B3 pozostawala niezmienna:
- po zmianie wartosci zmiennych,
- przy kolejnych numerach sequence 3, 4 i 5.
Wyniki wskazuja, ze pole nie zalezy bezposrednio od samych wartosci payload
ani od numeru sequence w zaobserwowanych probach.

Nie wiadomo jeszcze, czy pole zalezy od konfiguracji listy, typow,
kolejnosci zmiennych, naglowka lub innego parametru.

Nie nalezy traktowac tych wartosci jako potwierdzonego algorytmu CRC
ani sumy kontrolnej.
Wysylanie ramek z checksum
Generowanie checksum dla ramek wysylanych przez Home Assistant nie jest
zaimplementowane, poniewaz algorytm nie zostal potwierdzony.

Ustawienie transmit_checksum: true w trybie write powoduje odmowe
wyslania ramki zamiast wysylania niepoprawnej wartosci pola kontrolnego.
Konfiguracja przez UI
W formularzu integracji podaj:
- adres IP sterownika,
- port UDP,
- List ID,
- tryb read lub write,
- ustawienie pack_variables,
- ustawienie transmit_checksum,
- zmienne wraz z ich typami, offsetami i encjami.
Ograniczenia
- Algorytm checksum nie jest jeszcze rozpoznany.
- Weryfikacja checksum odebranych ramek nie jest wykonywana.
- Generowanie checksum dla ramek wysylanych nie jest zaimplementowane.
- initial_value inicjalizuje bufor zapisu, ale nie jest automatycznie
  wysylane do PLC podczas uruchamiania Home Assistant.
- Format ramek TX wymaga dalszego potwierdzenia przechwyceniem pakietow
  wysylanych z Home Assistant do PLC.

Ważne uwagi przed uruchomieniem
1. Sensor diagnostyczny będzie tworzony automatycznie dla każdej listy read. Nie trzeba dodawać go ręcznie do konfiguracji.
2. Po pierwszej ramce niepakowanej sensor pokaże incomplete, np. received_count: 1, expected_count: 12.
3. Po odebraniu wszystkich 12 indeksów tego samego cyklu pokaże complete.
4. Gdy rozpocznie się następny cykl, diagnostyka zacznie liczyć odebrane zmienne od nowa. Encje zachowają ostatnie wartości, dopóki nie nadejdą ich nowe ramki.
