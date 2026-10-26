# 3D PHP Analyzer

**Offline browser app for pulsating heat pipe temperature experiments.**

## Uruchomienie bez instalacji

1. Pobierz repozytorium: Code → Download ZIP.
2. Rozpakuj cały ZIP.
3. Otwórz dwuklikiem **index.html** w aktualnej wersji Chrome, Firefox lub Edge.
4. Wczytaj pliki CSV wyeksportowane z PicoLog.
5. Sprawdź przyporządkowanie kanałów, wprowadź harmonogram mocy Q(t), pobierz wykresy.

**Brak wymagań: Python, pip, npm, serwer i internet nie są potrzebne.** Wszystkie pliki HTML, JS i CSS muszą pozostać razem w jednym folderze. Dane nie są przesyłane do sieci.

## Funkcje wersji 0.1

- Import wielu plików CSV z PicoLog (separator przecinkowy/średnik/tabulator, polski przecinek dziesiętny).
- Identyfikacja kanałów 1, 3, 4, 5, 6, 7; ręczna zmiana konfiguracji termopar.
- Średnie temperatury: parownik ch1/ch3, środek ch4/ch5, skraplacz ch6/ch7.
- Wykresy temperatur, ΔT, zdefiniowanej mocy Q, R_app [K/W] oraz R/R_ref [−].
- Wykrywanie luk w rejestracji na podstawie czasu: szare obszary, bez interpolowania.
- Ręczna edycja przedziałów Q(t), w tym 0 W, bez odgadywania ON/OFF z temperatur.
- Eksport wykresów SVG i PNG, tabeli CSV i zbiorczego raportu ZIP z konfiguracją.
- Zmiana zakresu czasu; działa całkowicie lokalnie, bez bibliotek CDN.

## Wprowadzanie Q

W harmonogramie każdemu przedziałowi przypisz początek i koniec w minutach od startu rejestracji i Q [W]. Nie dopuszczamy nakładających się przedziałów. **Poza zdefiniowanymi przedziałami Q jest nieznane**, a nie 0. Przy Q = 0 W lub bez przypisanej Q nie liczymy R [K/W]. Moc nie jest odczytywana z nazwy pliku.

## Wzory i interpretacja

- Te = średnia temperatura termopar przypisanych do parownika;
- Tm = średnia temperatura termopar sekcji środkowej;
- Tc = średnia temperatura termopar skraplacza;
- ΔT = Te − Tc [K];
- **R_app = (Te − Tc) / Q [K/W]**, jeśli Q > 0 i jest znana;
- **R/R_ref**: względem mediany R_app w ręcznie zadanym oknie odniesienia, minimum 5 próbek, tylko przy tej samej stałej dodatniej Q.

R_app jest **pozornym oporem odniesionym do zadanej mocy elektrycznej**. Nie musi być równoważny oporowi przy rzeczywistym strumieniu ciepła przenoszonym przez PHP — szczególnie w stanach nieustalonych, przy magazynowaniu energii i stratach.

**Oscylacje temperatur nie są bezpośrednim dowodem ruchu czynnika.** Wersja 0.1 nie zawiera jeszcze zwalidowanego wykrywania O1/O2 i automatycznego odczytu elektrycznego ON/OFF.

## Przykładowe dane PicoLog

~~~csv
"","Kanał 1 Ostatni (C)","Kanał 3 Ostatni (C)","Kanał 4 Ostatni (C)","Kanał 5 Ostatni (C)","Kanał 6 Ostatni (C)","Kanał 7 Ostatni (C)"
"00:00:01","23,477","23,408","23,323","23,283","23,386","23,444"
~~~

Natywny format .picolog nie jest czytany — najpierw wykonaj eksport CSV w PicoLog. Obsługiwane są także UTF-8 BOM i UTF-16 BOM. Nietypowe eksporty mogą wymagać rozszerzenia parsera; wynik sprawdzaj przed użyciem naukowym.

## Pliki i testy

- index.html — start aplikacji
- style.css — wygląd
- core.js — parser i obliczenia
- app.js — interakcje, wykresy SVG, eksport PNG/CSV/ZIP
- tests/core.test.cjs — testy automatyczne
- .github/workflows/test.yml — weryfikacja w GitHub Actions

Programista może opcjonalnie uruchomić testy komendą:

~~~sh
node --test tests/core.test.cjs
~~~

Instalacja Node **nie jest potrzebna użytkownikowi aplikacji**.

## Dalszy rozwój

Walidacja na wszystkich oryginalnych seriach pomiarowych, porównywanie testów przy rzeczywistej Q, import zsynchronizowanych pomiarów mocy, ocena niepewności pomiarowej, zapis sesji, automatyczna detekcja epizodów oscylacyjnych dopiero po walidacji algorytmu.

MIT License.
