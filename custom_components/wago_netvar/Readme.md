# Wago NetVar Integration for Home Assistant

Niestandardowa integracja (**Custom Integration**) dla Home Assistanta umożliwiająca bezpośrednią, dwukierunkową komunikację ze sterownikami PLC (Wago / CoDeSys) za pomocą protokołu **NetVar** po sieci UDP (oparta na nagłówku `.S3`).

---

## 🚀 Kluczowe funkcjonalności

* **Komunikacja lokalna UDP:** Bezpośrednia wymiana danych w czasie rzeczywistym między Home Assistantem a sterownikiem PLC.
* **Obsługa wielu ramek (Wiele COB-ID):** Możliwość nasłuchiwania i wysyłania danych dla różnych grup zmiennych rozróżnianych po identyfikatorze `cob_id`.
* **Dwukierunkowy przepływ:** 
  * **Odczyt (RX):** Automatyczna aktualizacja stanów encji w Home Assistancie po odebraniu ramki ze sterownika.
  * **Zapis (TX):** Wysyłanie zmian stanu (np. przełączenie switcha w HA) bezpośrednio do sterownika PLC.
* **Wsparcie dla wielu typów danych PLC:** `BOOL`, `REAL` (zmiennoprzecinkowe), `INT`, `DINT` i inne.

---

## 📦 Instalacja przez HACS

1. Otwórz **HACS** w swoim panelu Home Assistant.
2. Kliknij w prawym górnym rogu w trzy kropki, a następnie wybierz **Niestandardowe repozytoria** (*Custom repositories*).
3. Wklej adres URL swojego repozytorium GitHub w polu **Kategoria** wybierz **Integracja** (*Integration*).
4. Kliknij **Dodaj**.
5. Wyszukaj integrację **Wago NetVar UDP** na liście HACS, pobierz ją i **zrestartuj Home Assistanta**.

---

## ⚙️ Konfiguracja i obsługa wielu ramek (COB-ID)

Protokół NetVar pozwala na dzielenie zmiennych na niezależne bloki (ramki) identyfikowane za pomocą unikalnego **COB-ID**. Każda ramka posiada swój własny nagłówek `.S3` oraz payload zawierający zmienne przypisane do konkretnego blokowego offsetu pamięci.

### Przykład konfiguracji dla dwóch różnych ramek (COB-ID: 1 oraz COB-ID: 2)

Poniższy przykład przedstawia konfigurację integracji obsługującą dwa niezależne urządzenia lub bloki logiczne w sterowniku PLC:

#### 1. Ramka sterująca oknami i oświetleniem (`cob_id: 1`)
* **Adres IP PLC:** `192.168.1.10`
* **Port UDP:** `1202`
* **COB-ID:** `1`
* **Zawartość payloadu:**
  * Offset `0` (1 bajt): Przełącznik światła w salonie (`BOOL`)
  * Offset `1` (4 bajty): Aktualna temperatura w pokoju (`REAL`)

#### 2. Ramka systemowa i liczniki (`cob_id: 2`)
* **Adres IP PLC:** `192.168.1.10`
* **Port UDP:** `1202`
* **COB-ID:** `2`
* **Zawartość payloadu:**
  * Offset `0` (4 bajty): Całkowite zużycie energii (`REAL` / `DINT`)
  * Offset `4` (1 bajt): Tryb pracy systemu (`BOOL`)

---

## 📝 Przykłady wykorzystania w Home Assistancie

### Odczyt zmiennych (Sensor)
Aby odczytać wartość numeryczną (np. typ `REAL` o długości 4 bajtów pod konkretnym offsetem bajtowym w danej ramce):

```python
# Przykład encji sensor odbierającej dane z ramki o określonym offsetcie
NetVarSensor(
    coordinator=coordinator, 
    name="Temperatura PLC", 
    byte_offset=1,   # Offset wewnątrz payloadu
    size=4,          # Rozmiar w bajtach (REAL = 4 bajty)
    var_type="REAL"
)
