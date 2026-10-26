# 3D PHP Analyzer — Python Desktop

Aplikacja desktopowa dla Windows, działająca podobnie do [LiftHeightAnalyzer](https://github.com/MateuszBock0/LiftHeightAnalyzer): **Python + Tkinter + PyInstaller**, lokalne dane, interaktywny wykres Matplotlib, przenośny ZIP z plikiem `.exe`.

## Pobierz wersję dla Windows — bez instalowania Pythona

**[Releases → pobierz 3DPHPAnalyzer_Windows_x64.zip](https://github.com/MateuszBock0/3DPHPanalyzer/releases/tag/latest)**

1. Rozpakuj pobrany plik ZIP.
2. Nie przenoś samego `.exe` poza katalog — folder `_internal` musi zostać obok.
3. Dwukrotnie kliknij `3DPHPAnalyzer.exe`.
4. Wybierz CSV / archiwum ZIP zawierające CSV lub folder pomiarów.
5. Zobacz wykresy, detekcję epizodów, wprowadź ręcznie Q [W], pobierz wyniki.

**Uwaga:** GitHub → „Code → Download ZIP” daje *kod źródłowy*, nie gotowe `.exe`. Gotową aplikację pobiera się z **Releases**. Po każdym pushu do `main`, GitHub Actions buduje nowy pakiet dla Windows i aktualizuje wersję `latest`. Żaden Python nie jest wymagany do użycia gotowego ZIP. Aplikacja działa offline.

## Co jest w środku

- **Oryginalny silnik** `php_analyzer.py` z załączonego `PHP_Analyzer_ON_OFF_przedzialy(1).zip`, z minimalną zmianą przełączania backendu wykresów w trybie GUI.
- `php_desktop.py`: interfejs Tkinter, wybór wielu pomiarów, wykresy na żywo (pan/zoom z Matplotlib), tabela oscylacji O1/O2 i szacowanych reakcji ON?/OFF?, edycja przedziałów Q, eksport.
- `power_model.py`: oddzielny moduł mocy i obliczania oporu.
- `tests`: testy modułów i importu oryginalnych danych.
- `.github/workflows/build-windows.yml`: budowanie paczki Windows automatycznie i publikacja na Releases.

## Metryki i interpretacja

Przypisanie kanałów wynikające z eksperymentu:
- ch1/ch3: parownik Te;
- ch4/ch5: sekcja środkowa Tm;
- ch6/ch7: skraplacz Tc.

**ΔT = Te − Tc [K]**. Możesz zdefiniować różne rzeczywiste etapy grzania w zakładce `Moc Q / R` (od-do minut od początku CSV, Q [W]), w tym okresy Q=0. **Nieznana Q jest niezdefiniowana, nie zero.** Dla Q>0 aplikacja liczy **R_app = ΔT/Q [K/W]**; jest to *pozorny* opór w odniesieniu do zadanej mocy elektrycznej. Nie należy interpretować go jako bezpośredniego pomiaru strumienia ciepła rzeczywiście przenoszonego przez PHP w stanach przejściowych.

R/Rref wymaga okna referencyjnego z co najmniej pięcioma próbkami i jedną dodatnią, niezmienną Q. Jest wyświetlane tylko tam, gdzie Q zgadza się z referencją.

Dawny sygnał `R proxy ΔT/ΔTref` jest dostępny **osobno** w rozwijanym menu wykresu. **Nie ma jednostki K/W** i nie może być interpretowany jako zmierzony opór cieplny przy zmianach mocy.

O1/O2 to kandydaci oscylacji **temperatur ścianek**, nie dowód ruchu czynnika. ON?/OFF? to **szacowane reakcje temperaturowe**, a nie zarejestrowane stany elektryczne. Szare pasma oznaczają prawdziwe luki w rejestracji, bez łączenia wykresów przez brakujące dane.

## Eksport

- `Eksport wybranego`: wykresy PNG (ogólny i zbliżenia epizodów), dane pomocnicze CSV, `moc_i_opor.csv`, `przedzialy_Q.csv`, `konfiguracja.json`, zapis aktualnego widoku wykresu.
- `Eksport całości`: analogiczny komplet dla wszystkich wczytanych plików, raport `Raport.html` i zestawienie CSV.

## Uruchomienie ze źródeł (dla programistów)

Wymaga Python 3.10+:

```bash
python -m pip install "matplotlib>=3.8,<4"
python php_desktop.py
```

Zbudowanie Windows EXE lokalnie:

```bash
python -m pip install -r requirements.txt
pyinstaller --noconfirm --onedir --windowed --name 3DPHPAnalyzer --collect-all matplotlib php_desktop.py
```

Weryfikacja:

```bash
python -m unittest discover -s tests -v
```

### Ograniczenia

Współczynnik R_app nie uwzględnia automatycznie strat i akumulacji ciepła. Żadna detekcja oscylacji nie jest bezpośrednim pomiarem przepływu płynu. Natywne pliki `.picolog` nie są czytane — wymagany eksport CSV. Podczas pierwszego uruchomienia niepodpisana aplikacja może uruchomić ostrzeżenie Windows SmartScreen. Wersja przenośna przeznaczona jest dla Windows x64.

MIT.
