3D PHP ANALYZER — WINDOWS (bez instalacji)
===========================================
1. Rozpakuj CALY ZIP (nie uruchamiaj EXE bezposrednio z ZIP).
2. Zostaw obok siebie plik 3DPHPAnalyzer.exe oraz folder _internal.
3. Uruchom 3DPHPAnalyzer.exe dwuklikiem.
4. Wybierz pliki CSV, ZIP z CSV lub folder eksperymentow.
5. W zakladce Wykresy ogladasz temperatury, DeltaT, R/proxy lub RMS.
6. W zakladce Epizody/ON?OFF? sa kandydaci oscylacji i szacowane zmiany cieplne.
7. Po otwarciu pierwszego pomiaru pole Q = [   ] W jest puste.
   Wpisz nominalna moc [W] z notatek i kliknij ON na wykresie.
   Opcjonalnie przycisk Ustaw stale Q konfiguruje caly plik.
8. W zakladce Moc Q/R sa szacowane okresy ON?/OFF?, nawet bez Q.
   Mozesz kliknac "Nadpisz wybrany okres" albo "Dodaj nadpisanie",
   aby zmienic Q na konkretnym fragmencie. Reczne Q ma pierwszenstwo.
9. Wyniki wyeksportuj przyciskami Eksport wybranego lub Eksport calosci.


WAZNE: ON?/OFF? nie pochodzi z logu zasilacza i nie dowodzi stanu grzalki.
Estymowany OFF? = 0 W tylko po Twoim swiadomym wyborze stalego Q.
Okresy z lukami danych maja nieznana Q. Brak okreslonej mocy nie jest rowny Q=0. R_app = DeltaT/Q wyliczamy tylko przy Q>0.
Wzgledny opor R/Rref jest porownywany wyłącznie przy tej samej Q.
Kolory epizodow dotycza oscylacji TEMPERATURY, nie potwierdzaja przeplywu cieczy.
Program nie odczytuje binarnych plikow PicoLog. Eksportuj pomiary jako CSV.

Brak potrzeby instalowania Pythona i pakietow. Internet nie jest potrzebny.
Windows moze pokazac ostrzezenie SmartScreen dla aplikacji bez podpisu cyfrowego.

 
NOWE FUNKCJE
- „Wczytaj konfigurację JSON” przywraca Q i referencję do wybranego pomiaru CSV.
- Nowe konfiguracje porównują odcisk SHA-256 wszystkich próbek.
- P↑? nie otrzymuje automatycznie Q: po wykryciu możliwej zmiany mocy
  wpisz nową wartość ręcznie, jeśli ją znasz.
- R/Rref wymaga jednego ciągłego odcinka dodatniej, stałej Q bez luk i OFF.
- Raport HTML i ostatnia zakładka programu wyjaśniają wszystkie obliczenia.
- Eksport PNG pokazuje typ trzeciego panelu wybrany w aplikacji.


AUTO ODTWARZANIE EKSPERYMENTU (BEZ LOGU ZASILACZA)
1. Wczytaj CSV. Program sam zaproponuje ON?/OFF? (szacowanie z temperatur).
2. W zakladce Wykresy kliknij "Zatwierdz sugestie ON?/OFF?".
   Wpisz moc ON w W. Mozesz tez pominac propozycje i klikac ON, OFF,
   Zmien Q na wykresie - program zapyta o moc tylko przy ON i zmianie Q.
3. Zielony pionowy znacznik to ON/zmiana Q, czerwony to OFF.
   Przeciagnij pionowa linie, aby przesunac czas; albo wybierz znacznik
   z tabeli w "Moc Q / R" i kliknij "Przesun na wykresie".
4. Kazda zmiana od razu przelicza Q, R_app, R/Rref, K2 i raportowe CSV.
   Kliknij "Cofnij", aby cofnac ostatnia zmiane znacznikow.
5. Program automatycznie zapisuje ustawienia dla kazdego pomiaru w
   katalogu uzytkownika: 3DPHPAnalyzer/Sessions. Wczytanie TEGO SAMEGO
   CSV przywroci konfiguracje. Kopia jest tez w eksporcie konfiguracja.json.
6. Eksport wybranego zawiera "reczne_zdarzenia_ON_OFF_Q.csv".
   Reczne przedzialy Q maja pierwszenstwo przed znacznikami, a znaczniki
   przed automatycznym domyslnym Q na okresach ON?/OFF?.

NIE MA pomiaru U/I. Moc Q pochodzi z wpisanych przez Ciebie nastaw.
Akceptacja ON?/OFF? z temperatur NIE potwierdza czasu elektrycznego
przelaczenia - moze on byc opozniony przez bezwladnosc termiczna.
\nKONIEC CSV to tylko koniec danych, NIE automatyczne OFF!\nJesli wiesz, ze grzalka zostala wylaczona przy ostatnim pomiarze,\nuzyj przycisku 'OFF na koncu CSV (potwierdz)'.\nDane PicoLog NIE zawieraja U ani I; wpisuj nominalne Q [W] z notatek.\n