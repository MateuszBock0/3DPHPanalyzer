# 3D PHP Analyzer — Python Desktop

Aplikacja desktopowa dla Windows, działająca podobnie do [LiftHeightAnalyzer](https://github.com/MateuszBock0/LiftHeightAnalyzer): **Python + Tkinter + PyInstaller**, lokalne dane, interaktywny wykres Matplotlib, przenośny ZIP z plikiem `.exe`.

## Pobierz wersję dla Windows — bez instalowania Pythona

**[Releases → pobierz 3DPHPAnalyzer_Windows_x64.zip](https://github.com/MateuszBock0/3DPHPanalyzer/releases/latest)**

1. Rozpakuj pobrany plik ZIP.
2. Nie przenoś samego `.exe` poza katalog — folder `_internal` musi zostać obok.
3. Dwukrotnie kliknij `3DPHPAnalyzer.exe`.
4. Wybierz CSV / archiwum ZIP zawierające CSV lub folder pomiarów.
5. Przy pierwszym wykresie możesz wybrać „Ustaw stałe Q…”.
6. Sprawdź wykryte okresy ON?/OFF? oraz popraw przedziały Q ręcznie.
7. Zobacz wykresy i pobierz wyniki.

**Uwaga:** GitHub → „Code → Download ZIP” daje *kod źródłowy*, nie gotowe `.exe`. Gotową aplikację pobiera się z **Releases**. Po każdym pushu do `main`, GitHub Actions buduje nowy pakiet dla Windows i publikuje nowe wydanie Windows jako „Latest”. Żaden Python nie jest wymagany do użycia gotowego ZIP. Aplikacja działa offline.

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

**Konfiguracja stałej Q na pierwszym wykresie:** po wczytaniu pierwszego pomiaru pokazuje się okno z możliwością wpisania mocy w watach. Można wybrać zastosowanie Q tylko do szacowanych okresów `ON?` (wtedy `OFF?` otrzymuje założone `0 W`, a przed rozpoznaniem `ON?` i w lukach Q pozostaje nieznane) albo do **całego pliku** — ta druga opcja jest poprawna tylko przy fizycznie stałej mocy przez cały pomiar. Podczas otwierania kolejnych pomiarów można wywołać okno przyciskiem `Ustaw stałe Q…`.

**Tabela w zakładce `Moc Q / R`:** szacowane `ON?`, `OFF?` i `P↑?` są widoczne automatycznie jako okresy robocze; przy `P↑?` zaznaczono możliwość zmiany obciążenia. Nie są to rzeczywiste dane elektryczne. Po podaniu stałej Q pojawią się wstępne wartości Q. `Nadpisz wybrany okres…` i `Dodaj nadpisanie` pozwalają zmienić Q także dla podprzedziału; ręczny wpis zawsze ma priorytet, nawet w szacowanym okresie OFF. Wykryta przerwa rejestracji kończy dotychczasową estymację stanu i następny okres pozostaje nieznany aż do nowego zdarzenia.

**ΔT = Te − Tc [K]**. Możesz zdefiniować różne rzeczywiste etapy grzania w zakładce `Moc Q / R` (od-do minut od początku CSV, Q [W]), w tym okresy Q=0. **Nieznana Q jest niezdefiniowana, nie zero.** Dla Q>0 aplikacja liczy **R_app = ΔT/Q [K/W]**; jest to *pozorny* opór w odniesieniu do zadanej mocy elektrycznej. Nie należy interpretować go jako bezpośredniego pomiaru strumienia ciepła rzeczywiście przenoszonego przez PHP w stanach przejściowych.

R/Rref wymaga okna referencyjnego z co najmniej pięcioma próbkami i jedną dodatnią, niezmienną Q. Jest wyświetlane tylko tam, gdzie Q zgadza się z referencją.

Dawny sygnał `R proxy ΔT/ΔTref` jest dostępny **osobno** w rozwijanym menu wykresu. **Nie ma jednostki K/W** i nie może być interpretowany jako zmierzony opór cieplny przy zmianach mocy.

O1/O2 to kandydaci oscylacji **temperatur ścianek**, nie dowód ruchu czynnika. ON?/OFF? to **szacowane reakcje temperaturowe**, a nie zarejestrowane stany elektryczne. Szare pasma oznaczają prawdziwe luki w rejestracji, bez łączenia wykresów przez brakujące dane.

## Eksport

- `Eksport wybranego`: wykresy PNG (ogólny i zbliżenia epizodów), dane pomocnicze CSV, `moc_i_opor.csv`, `przedzialy_Q.csv`, `wykryte_okresy_ON_OFF.csv`, `nadpisania_Q.csv`, `konfiguracja.json`, zapis aktualnego widoku wykresu.
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


## Nowa kontrola R_ref
Okno referencyjne musi obejmować wyłącznie jeden ciągły okres dodatniej, stałej mocy Q, bez OFF i braków rejestracji.


## Weryfikacja referencji, eksport i metodyka

- Przedział referencyjny \`R/Rref\` jest półotwarty \`[Od, Do)\` i musi całkowicie mieścić się w jednym nieprzerwanym etapie znanej, stałej, dodatniej Q. Nie może zawierać OFF, nieznanej Q ani luki rejestracji; wymagane jest co najmniej 5 próbek. Wybierz okres quasi-ustalony.
- Oszacowany \`P↑?\` nie dziedziczy automatycznie Q w trybie przedziałów ON?/OFF?. Jeśli rzeczywiście zmieniła się moc, wprowadź ręczne Q. W trybie „cały plik” program stosuje zadane przez operatora Q przez cały czas.
- Dolny panel zapisany do PNG w eksporcie zbiorczym odpowiada metryce wybranej w interfejsie (R_app, R/Rref, proxy, RMS lub Q). Raport HTML nazywa panel, zawiera działające linki do CSV i końcową sekcję metodyki.
- \`Wczytaj konfigurację JSON\` przywraca Q i referencję do aktualnie wybranego CSV. Nowa konfiguracja zapisuje SHA-256 wszystkich próbek oraz czasów, co blokuje import ustawień do innego pomiaru. Stary JSON bez tej sumy wymaga potwierdzenia.
- Ostatnia zakładka \`Metodyka i obliczenia\` i końcowa część \`Raport.html\` opisują wzory, progi K1/K2, detekcję ON?/OFF?, sposób liczenia Q i oporu, normalizację, proxy oraz niepewności. Dostępny jest też plik \`Metodyka_obliczen.html\`.

Parametry detekcji mają charakter roboczy i wymagają walidacji naukowej. R_app=ΔT/Q [K/W] to wskaźnik pozorny względem mocy elektrycznej, nie bezpośredni pomiar mocy transportowanej przez PHP.

**Automatyczny zapis konfiguracji:** po zmianie Q albo referencji aplikacja zapisuje ustawienia w katalogu użytkownika `~/.3dphpanalyzer/configurations/`. Przy ponownym wczytaniu identycznego pomiaru automatycznie przywraca ręczne przedziały Q, wybraną moc i okno odniesienia. Zgodność jest sprawdzana odciskiem SHA-256 wszystkich próbek. Działa też po przeniesieniu pliku do innego folderu. Nieprawidłowy zapis nie jest stosowany.

**Referencja quasi-ustalona:** w interfejsie wymagany jest ciągły okres stałej dodatniej Q, co najmniej 2 minuty oraz trendy Te i Tc nie większe niż 0,50°C/min (roboczy próg do walidacji). Odrzucone okno nie generuje R/Rref.
