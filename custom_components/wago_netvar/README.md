# Wago NetVar Integration for Home Assistant

Niestandardowa integracja (**Custom Integration**) dla Home Assistanta umożliwiająca bezpośrednią, dwukierunkową komunikację ze sterownikami PLC (Wago / CoDeSys) za pomocą protokołu **NetVar** po sieci UDP (oparta na nagłówku `.S3`).

---

## 🚀 Kluczowe funkcjonalności

* **Komunikacja lokalna UDP:** Bezpośrednia wymiana danych w czasie rzeczywistym między Home Assistantem a sterownikiem PLC.
* **Obsługa wielu ramek (Wiele COB-ID):** Możliwość niezależnego nasłuchiwania i wysyłania danych dla różnych identyfikatorów `cob_id` na tym samym porcie.
* **Dwukierunkowy przepływ:** 
  * **Odczyt (RX):** Automatyczna aktualizacja stanów encji w Home Assistancie po odebraniu ramki ze sterownika PLC.
  * **Zapis (TX):** Wysyłanie zmian stanu (np. przełączenie switcha w HA) bezpośrednio do sterownika.
* **Wsparcie dla big-endian i little-endian:** Konfigurowalny endianizm zgodny z architekturą sterownika PLC.

---

## 📋 Obsługiwane typy zmiennych PLC (Data Types)

Integracja w pełni wspiera standardowe typy danych CoDeSys/IEC 61131-3 przesyłane w payloadzie ramki:

| Typ PLC | Kategoria | Rozmiar (w bajtach) | Opis / Zastosowanie w HA |
| :--- | :--- | :--- | :--- |
| **`BOOL`** | Logiczny | 1 bit (pakowane) | Stany binarne, przełączniki (`switch`), czujniki otwarcia (`binary_sensor`) |
| **`BYTE` / `USINT` / `SINT`** | Całkowity | 1 bajt | Małe wartości numeryczne, stany, tryby (`sensor`) |
| **`WORD` / `UINT` / `INT`** | Całkowity | 2 bajty | Liczniki, poziomy, temperatury całkowite (`sensor`, `number`) |
| **`DWORD` / `UDINT` / `DINT` / `TIME`** | Całkowity / Czas | 4 bajty | Duże liczniki, znaczniki czasu, zużycie energii (`sensor`) |
| **`REAL`** | Zmiennoprzecinkowy | 4 bajty | Standardowa precyzja: temperatura, ciśnienie, wilgotność (`sensor`, `number`) |
| **`LREAL`** | Zmiennoprzecinkowy | 8 bajtów | Podwójna precyzja: precyzyjne pomiary analityczne (`sensor`) |
| **`STRING(n)`** | Tekstowy | $n + 1$ bajtów | Komunikaty tekstowe, nazwy trybów (`sensor`) |

---

## 📦 Instalacja przez HACS

1. Otwórz **HACS** w swoim panelu Home Assistant.
2. Kliknij w prawym górnym rogu w trzy kropki, a następnie wybierz **Niestandardowe repozytoria** (*Custom repositories*).
3. Wklej adres URL swojego repozytorium GitHub w polu **Kategoria** wybierz **Integracja** (*Integration*).
4. Kliknij **Dodaj**.
5. Wyszukaj integrację **Wago NetVar UDP** na liście HACS, pobierz ją i **zrestartuj Home Assistanta**.

---

## ⚙️ Konfiguracja i obsługa wielu ramek (Wiele COB-ID)

Protokół NetVar pozwala na dzielenie zmiennych na niezależne bloki (ramki) identyfikowane za pomocą unikalnego **COB-ID**. Każda encja w kodzie integracji przypisana jest do konkretnego `cob_id` oraz offsetu bajtowego wewnątrz payloadu.

### Przykład definicji encji dla różnych COB-ID:

#### 1. Ramka sterująca oświetleniem (`cob_id = 1`)
* **Offset 0 (4 bajty, `REAL`):** Temperatura w salonie (`NetVarSensor`)
* **Offset 4 (Bajt 4, Bit 0):** Przełącznik światła głównego (`NetVarSwitch`)

```python
# Rejestracja czujnika temperatury z cob_id = 1
NetVarSensor(coordinator, name="Temperatura Salon", cob_id=1, byte_offset=0, size=4, var_type="REAL")

# Rejestracja przełącznika światła z cob_id = 1
NetVarSwitch(coordinator, name="Światło Salon", cob_id=1, byte_offset=4, bit_offset=0)

# Rejestracja licznika z cob_id = 2
NetVarSensor(coordinator, name="Licznik Energii", cob_id=2, byte_offset=0, size=2, var_type="INT")

🛠️ Specyfikacja techniczna ramki NetVar (.S3)Struktura nagłówka pakietu UDP (pierwsze 20 bajtów):
Pozycja (Bajty) Nazwa pola Opis
0 - 3Magiczny nagłówekStała flaga inicjalizacyjna: 0x00, 0x2D, 0x53, 0x33 (.S3)
8 - 9cob_idIdentyfikator bloku zmiennych (rozpoznawanie ramek)
12 - 13checksumSuma kontrolna pakietu
14 - 15total_lenCałkowita długość pakietu (20 bajtów nagłówka + payload)
16 - 17sequenceLicznik sekwencji pakietów
20+PayloadWłaściwe dane zmiennych PLC (zmienne upakowane binarnie)
