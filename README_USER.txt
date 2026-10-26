3D PHP ANALYZER — WINDOWS (bez instalacji)
===========================================
1. Rozpakuj CALY ZIP (nie uruchamiaj EXE bezposrednio z ZIP).
2. Zostaw obok siebie plik 3DPHPAnalyzer.exe oraz folder _internal.
3. Uruchom 3DPHPAnalyzer.exe dwuklikiem.
4. Wybierz pliki CSV, ZIP z CSV lub folder eksperymentow.
5. W zakladce Wykresy ogladasz temperatury, DeltaT, R/proxy lub RMS.
6. W zakladce Epizody/ON?OFF? sa kandydaci oscylacji i szacowane zmiany cieplne.
7. W zakladce Moc Q/R dodaj rzeczywiste przedzialy Q (W), ktore znasz z zasilacza.
8. Wyniki wyeksportuj przyciskami Eksport wybranego lub Eksport calosci.

WAZNE: ON?/OFF? nie pochodzi z logu zasilacza i nie dowodzi stanu grzalki.
Brak okreslonej mocy nie jest rowny Q=0. R_app = DeltaT/Q wyliczamy tylko przy Q>0.
Wzgledny opor R/Rref jest porownywany wyłącznie przy tej samej Q.
Kolory epizodow dotycza oscylacji TEMPERATURY, nie potwierdzaja przeplywu cieczy.
Program nie odczytuje binarnych plikow PicoLog. Eksportuj pomiary jako CSV.

Brak potrzeby instalowania Pythona i pakietow. Internet nie jest potrzebny.
Windows moze pokazac ostrzezenie SmartScreen dla aplikacji bez podpisu cyfrowego.
