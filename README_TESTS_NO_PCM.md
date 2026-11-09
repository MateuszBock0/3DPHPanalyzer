# TESTS_NO_PCM — praca na całym folderze

Instrukcja dla rzeczywistej struktury `C:\\Users\\Mateusz\\Desktop\\3D_PHP\\TESTS_NO_PCM` opisanej w `structure_tree_output.txt` z 9.11.2026.

## Struktura istniejącego folderu

```text
3D_PHP/
├── 3DPHPAnalyzer_wersje/      # wersje aplikacji (nie są surowymi pomiarami)
└── TESTS_NO_PCM/             # TEN katalog wybierasz w analizatorze
    ├── test-12_10.csv
    ├── ...                  # 12 źródłowych CSV z października
    ├── Nowy folder.zip      # nowe pomiary 3–6 listopada (CSV i PNG)
    ├── drut(Arkusz1).csv    # notatki i U/I; NIE sygnał PicoLog
    ├── drut_23_10-zestawienie.xlsx
    ├── zestawienie-wykresy(Arkusz1).csv
    ├── *.picolog            # oryginalne pliki PicoLog
    └── Results/             # stare przebiegi, wykresy i raporty
        ├── przebiegi/
        └── wykresy/
```

**Nie przenoś, nie zmieniaj nazw i nie usuwaj plików źródłowych.**

## Co zrobić

1. Uruchom aktualny `3DPHPAnalyzer.exe` (albo najpierw aktualizator BAT).
2. Kliknij **Otwórz folder** i wybierz `...\\3D_PHP\\TESTS_NO_PCM`.
3. Program rekurencyjnie znajdzie tylko źródłowe CSV PicoLog z kanałami 1, 3, 4, 5, 6 i 7. Odczyta także ich kopie w `Nowy folder.zip`, nie rozpakowując ani nie modyfikując archiwum. Zignoruje `Results`, arkusze, notatniki CSV, pliki `.picolog` i inne formaty.
4. Identyczne pliki zostaną wczytane tylko raz. Krótszy CSV, którego cały przebieg jest prefiksem dłuższego, będzie pominięty **jako niezależny pomiar**; zachowany zostanie dłuższy zapis, obejmujący oba etapy. Uważaj: **jeden CSV może zawierać kilka kolejnych nastaw Q**.
5. Wybierz eksperyment na liście, sprawdź `Podsumowanie`, skoryguj `ON?/OFF?` jeśli trzeba.
6. W `Wykresy` wybierz **Surowe** (domyślnie) lub **Skorygowane** i porównaj sygnały. Profil kalibracji pochodzi z `zestawienie-wykresy(Arkusz1).csv`. Zweryfikowany zakres punktów dopasowania: **20–105°C**. Wysokie temperatury parownika mogą być poza zakresem — to **ekstrapolacja, nie zwalidowana korekcja**.
7. Jeśli w danej próbie czujnik T4 jest uszkodzony, zaznacz **Wyklucz T4 z Tm**. Wtedy wyświetlany wskaźnik Tm jest **wyłącznie zmierzonym T5**, nie średnią ani syntetycznie uzupełnionym T4. Surowy T4 pozostaje w CSV. Dla innych prób nie wyłączaj T4 bez przyczyny.
8. Zaznacz **Termopary pojedyncze**. T6 i T7 są widoczne osobno; ich rozbieżności >20 K raportowane są w QA. Nie interpretuj dużego rozrzutu automatycznie jako awarii — najpierw sprawdź pozycje i kontakt czujników.
9. Jeśli chcesz dodać moc z dziennika: `Moc Q / R` → **Dziennik U/I → Q…** → wybierz `drut(Arkusz1).csv`, wskaż **konkretny wiersz U/I**, i ręcznie podaj przedział **od/do [min od początku wybranego CSV]**. `Q=U×I` jest obliczona z odczytu punktowego, nie jest synchronicznym pomiarem ani netto mocą przekazaną do PHP. Możesz także nadal zwyczajnie ręcznie wpisać Q.
10. Kliknij **Eksport wybranego** lub **Eksport całości**. Jako katalog docelowy wskaż `...\\TESTS_NO_PCM` albo osobny folder analiz. `Eksport całości` zapisuje pod `PHP_Results` (oddzielnie od starszego `Results`) — oba są wyłączone z kolejnego skanowania.

## Kontrola jakości i powtarzalność

- Domyślny tryb jest zawsze **raw**. Włączenie korekcji liczy od surowych próbek, nie nadpisuje pliku CSV i nie kumuluje kalibracji po kilkukrotnym przełączeniu.
- `kontrola_termopar.csv`: liczby punktów poza zakresem korekcji, T4 z wartościami odstającymi, różnice T6/T7.
- `termopary_raw_vs_corrected.csv`: osobno wszystkie surowe oraz poprawione kanały (gdy korekcja była aktywna).
- `zrodla_Q_z_dziennika.csv`: wybrane U, I, Q, wiersz dziennika, okres i opis.
- `konfiguracja.json` i lokalny autosave pamiętają tryb kalibracji i wykluczenie T4. Sesje starszych wersji są czytane jako **raw**.
- `ON?/OFF?` są wywnioskowane z temperatur, nie zmierzone elektrycznie. Wyniki K1/K2 to przesłanki termiczne, a nie bezpośredni pomiar przepływu w rurce.
- **Przed porównywaniem** października z listopadem jawnie sprawdź, czy dane miały chłodzenie wodne, izolację, wspólny montaż czujników i tę samą definicję mocy. W notatniku 3.11 występują zarówno odcinki z wodą, jak i bez.

## Co program celowo NIE robi

Nie wylicza Q z temperatur. Nie dopasowuje godzin z nieustrukturyzowanego arkusza `drut` do osi czasu PicoLog bez Twojego wyboru. Nie imputuje T4 ani luk rejestracji. Nie uznaje dwóch nakładających się eksportów jednego rejestratora za niezależne eksperymenty.


## Porównanie wielu eksperymentów

Po wczytaniu folderu wejdź w **Porównanie**. Zaznacz w tabeli 2–8 eksperymentów (Ctrl/Shift), wybierz `ΔT`, `Te`, `Tc`, `T6`, `T7`, `R_app` lub `RMS`, następnie kliknij `Porównaj zaznaczone`. Wyrównanie `csv` liczy od początku pliku; `on` wymaga ręcznego, potwierdzonego znacznika ON, a `on_estimate` dopuszcza osobno oznaczony szacunek ON? z temperatur. Serie bez wymaganego ON są pomijane z ostrzeżeniem. Luki pomiarowe nie są łączone liniami.

Program **ostrzega**, gdy próby mają różne Q, wiele etapów Q, mieszane kalibracje lub niepotwierdzone podobne chłodzenie. To porównanie **opisowe**, nie automatyczna kwalifikacja statystycznej powtarzalności lub udowodnienia przepływu. Możesz zapisać wykres PNG.
