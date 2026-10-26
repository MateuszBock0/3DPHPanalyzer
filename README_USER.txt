3D PHP ANALYZER — WINDOWS (bez instalacji)
===========================================
1. Rozpakuj CALY ZIP (nie uruchamiaj EXE bezposrednio z ZIP).
2. Zostaw obok siebie plik 3DPHPAnalyzer.exe oraz folder _internal.
3. Uruchom 3DPHPAnalyzer.exe dwuklikiem.
4. Wybierz pliki CSV, ZIP z CSV lub folder eksperymentow.
5. W zakladce Wykresy ogladasz temperatury, DeltaT, R/proxy lub RMS.
6. W zakladce Epizody/ON?OFF? sa kandydaci oscylacji i szacowane zmiany cieplne.
7. Po wczytaniu pierwszego pomiaru pojawia sie okno "Ustaw stale Q".
   Wpisz rzeczywista moc [W] i wybierz: tylko wykryte ON?/OFF? lub caly plik.
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
