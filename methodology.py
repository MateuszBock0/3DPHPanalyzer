"""One authoritative description of implemented calculations for GUI and HTML."""
from html import escape
import php_analyzer as engine

def sections():
    return [
        ('Zakres eksperymentu',
         'Badane urządzenie: pozioma pulsacyjna rurka ciepła 3D (PHP), parownik '
         'z drutem oporowym i izolacją, odkryta sekcja środkowa oraz skraplacz '
         'z pustym pojemnikiem na przyszły PCM. Chłodzenie przez otaczające '
         'powietrze. Dane temperatur nie są pomiarem przepływu cieczy ani pary.'),
        ('Kanały i czas',
         'Te=(T_ch1+T_ch3)/2 [°C]; Tm=(T_ch4+T_ch5)/2 [°C]; '
         'Tc=(T_ch6+T_ch7)/2 [°C]. Czas [min] jest liczony od pierwszej '
         'próbki CSV. Nieznane i błędne próbki nie są interpolowane. '
         'Jeśli zegar dobowy cofa się z okolic 23:59 na 00:00, '
         'program dodaje 24 h, zachowując kolejność próbek; inne cofnięcia '
         'czasu nie są domyślnie interpretowane jako nowa doba. '
         'Brak rejestracji jest rozpoznawany, gdy odstęp czasowy > '
         'max(10 s; 5×mediana odstępów). Wykresy są wówczas rozcinane.'),
        ('ΔT i wygładzanie',
         'ΔT(t)=Te(t)−Tc(t) [K]. Program pokazuje ΔT chwilowe oraz '
         f'jego wygładzenie średnią ruchomą około {engine.WINDOW_DELTA_S} s. '
         'R_app jest obliczane z wartości chwilowych, nie z wygładzonych.'),
        ('RMS, K1 i epizody',
         f'Z obu termopar parownika odejmowany jest lokalny trend (~{engine.WINDOW_TREND_S} s). '
         f'RMS reszt liczy się w oknie ~{engine.WINDOW_ACTIVITY_S} s; '
         'aktywność = min(RMS_ch1,RMS_ch3). '
         f'Próg K1 = max({engine.RMS_THRESHOLD_C:g} °C; 3×P90 aktywności '
         'na początkowym spokojnym odcinku). '
         f'Epizod musi trwać co najmniej {engine.MIN_EPISODE_S} s '
         f'(przerwy do {engine.MAX_GAP_S} s mogą być scalane). '
         f'Potwierdzenie kształtu oscylacyjnego wymaga ≥{engine.MIN_PEAKS} '
         f'maksimów i minimów z prominencją ≥{engine.PEAK_PROMINENCE_C:g} °C '
         'na obu czujnikach parownika. Pojedynczy skok grzania nie wystarcza.'),
        ('K2 — zmniejszenie ΔT',
         f'Lokalna baza to mediana ΔT od {engine.PRE_BASELINE_START_S/60:g} '
         f'do {engine.PRE_BASELINE_END_S/60:g} min przed epizodem, z przynajmniej '
         f'{engine.MIN_BASELINE_S} s obserwacji i bazą ≥5 K. '
         f'K2: wygładzone ΔT ≤(1−{engine.DELTA_IMPROVEMENT:g})×baza '
         f'przez łącznie ≥{engine.MIN_IMPROVEMENT_S/60:g} min. '
         'Mniejsze ΔT może świadczyć o korzystnej zmianie, lecz przy zmianie Q '
         'albo chłodzenia nie dowodzi poprawy transportu ciepła przez PHP. '
         'Jest to wyłącznie TERMICZNY KANDYDAT K2, oznaczany bez znajomości Q.'),
        ('Kwalifikacja K2 po ustaleniu Q i chłodzenia',
         'Po przypisaniu mocy operatora badany jest cały przedział od początku '
         f'okna referencyjnego ({engine.PRE_BASELINE_START_S/60:g} min przed O1/O2) '
         'do końca epizodu. Wymagamy nieprzerwanej rejestracji oraz dodatniej, '
         'znanej i niezmiennej Q bez OFF ani luk w harmonogramie. '
         'Przy braku Q lub jej zmianie K2 pozostaje NIEZWERYFIKOWANY. '
         'Jeśli Q jest stała, ale warunki chłodzenia nie zostały potwierdzone '
         'w dzienniku eksperymentu, status to K2 termiczne; chłodzenie?. '
         'Dopiero zaznaczenie deklaracji operatora o porównywalnych warunkach '
         'chłodzenia pozwala oznaczyć K2 jako WARUNKOWO PORÓWNYWALNE. '
         'Deklaracja nie jest niezależnym pomiarem warunków chłodzenia, '
         'a nawet takie K2 nie stanowi dowodu ruchu czynnika ani wzrostu '
         'sprawności PHP. Zielony kolor wykresu dotyczy wyłącznie tego '
         'warunkowego statusu; pozostałe epizody są pomarańczowe.'),
        ('Przesłanki aktywności PHP — oddzielna diagnoza',
         'Zakładka Czy PHP pracuje? rozpatruje jedynie epizody oscylacyjne K1. '
         'Porównuje medianę Te i Tc z 6–1 min przed początkiem O1/O2 '
         'z medianą od około 30 s po początku do maksymalnie 10 min '
         'aktywności. Brak co najmniej 90 s odniesienia albo luka '
         'uniemożliwiają weryfikację tej reakcji. '
         'Spadek Te o co najmniej 1°C i wzrost Tc o co najmniej 0,5°C '
         'stanowią roboczą przesłankę zgodnego transportu ciepła; '
         'nie są pomiarem przepływu. K2 wymaga co najmniej 15% '
         'zmniejszenia ΔT przez 5 min. Do silnych przesłanek potrzebne '
         'są dodatkowo K2, ręcznie zadeklarowana stała moc Q dla całego '
         'porównania lub wyraźna deklaracja stałego Q w całym CSV, '
         'potwierdzenie z dziennika podobnych warunków chłodzenia '
         'i brak skoków termopar >5°C/próbkę. Q przypisana na podstawie '
         'ON? nie wystarcza do tego statusu. Wahania przy zmianie Q, '
         'brakach danych lub anomaliach czujników są niejednoznaczne. '
         'Statusy to jakościowe przesłanki, a nie skalibrowane '
         'prawdopodobieństwa ani potwierdzenie ruchu czynnika.'),
        ('Szacowanie ON?, OFF? i P↑?',
         f'Analizowane są spójne trendy Te i Tc w oknie około '
         f'{engine.HEAT_CHANGE_WINDOW_S} s; mocniejszy wzrost sugeruje ON?, '
         'spadek OFF?, dodatkowy wzrost przy ciepłym parowniku P↑?. '
         'Granice i pasma zdarzeń to odpowiedź termiczna, nie elektryczny '
         'zapis przełączeń. Po przerwie danych stan jest ponownie nieznany.'),
        ('Harmonogram mocy Q [W]',
         'Moc pochodzi wyłącznie z deklaracji operatora. W trybie szacowanym '
         'ON? otrzymuje zadane Q, OFF? jest założone jako 0 W, a '
         'UNKNOWN/GAP/P↑? pozostają bez Q. Podejrzewany wzrost P↑? wymaga '
         'ręcznego nadpisania, jeśli znasz nowe Q. Tabela ON?/OFF? pokazuje '
         'końcową Q po nadpisaniach, w tym informację o różnych lub nieznanych '
         'wartościach w obrębie jednego okresu. Opcja „cały plik” '
         'przypisuje stałą Q również poza ON? i jest poprawna tylko jeśli '
         'tak faktycznie pracowała grzałka. Ręczne etapy są nadrzędne.'),
        ('Interaktywna rekonstrukcja grzania i automatyczny zapis sesji',
         'Po odczycie CSV program generuje szacowane z temperatur ON?/OFF? '
         'oraz ewentualne P↑?. Operator może zaakceptować sugestie ON?/OFF? '
         'jednym przyciskiem lub klikać ręcznie ON, OFF i zmianę Q w osi '
         'czasu Matplotlib. Po zdarzeniu ON / zmianie Q wpisuje prawdziwą '
         'nastawę elektryczną Q>0, OFF ustawia Q=0. Znacznik definiuje '
         'Q od jego czasu do następnego znacznika lub końca pomiaru. '
         'Wartość przed pierwszym znacznikiem nie jest automatycznie znana. '
         'Priorytet: ręczny przedział Q > ręczny znacznik > automatyczny '
         'harmonogram oparty na szacowanych okresach ON?/OFF?. '
         'Zaakceptowane sugestie pozostają oznaczone jako '
         'accepted_thermal_estimate, a samodzielne kliknięcie operatora '
         'jako operator. Żadne z tych oznaczeń nie jest potwierdzeniem '
         'elektrycznym lub pomiarem U/I. Wykres nie pozwala tworzyć '
         'znaczników w dużych lukach rejestracji bez sąsiednich próbek. '
         'Zmiany powodują ponowne obliczenie Q, R i ocen aktywności. '
         'Program zapisuje atomowo konfigurację JSON z odciskiem SHA-256 '
         'danych w lokalnym folderze 3DPHPAnalyzer/Sessions w katalogu '
         'użytkownika i automatycznie ją przywraca dla identycznego CSV.'),
        ('Pozorny opór cieplny R_app',
         'R_app(t)=[Te(t)−Tc(t)]/Q(t) [K/W] tylko przy znanej dodatniej mocy Q. '
         'Dla Q=0 lub Q nieznanej wynik jest pusty. '
         'Q to zadana moc elektryczna, nie zmierzona moc przeniesiona wewnątrz '
         'PHP. Akumulacja energii, bezwładność i straty do otoczenia powodują, '
         'że R_app nie jest bezpośrednio rzeczywistym oporem PHP w stanach '
         'przejściowych. Do porównań wybieraj okresy quasi-ustalone.'),
        ('Referencja R_ref i R/R_ref',
         'Okno [od,do) musi w całości mieścić się w jednym ciągłym etapie '
         'stałego Q>0, zawierać ≥5 poprawnych próbek i nie przecinać '
         'braków danych. Nawet krótki OFF, zmiana Q lub Q nieznane '
         'unieważniają referencję. R_ref=mediana R_app w oknie [K/W]. '
         'R/R_ref(t)=R_app(t)/R_ref tylko przy tym samym Q co okno referencji. '
         'Kryterium ciągłości nie gwarantuje fizycznego stanu ustalonego.'),
        ('Proxy względne i RMS',
         'Proxy=ΔT_wygładzone/ΔT_ref z lokalnej bazy w oszacowanym cyklu. '
         'Referencją jest baza przed oscylacją albo 90. percentyl spokojnego '
         'fragmentu, po pominięciu rozgrzewania. Proxy nie ma jednostki K/W '
         'i nie jest tym samym co R_app. Wskaźnik równoważny R/R_ref wymaga '
         'stałej Q oraz zgodnej definicji odniesienia. RMS pozostaje '
         'diagnostyką oscylacji K1, a nie oporem cieplnym.'),
        ('Eksport i wznowienie',
         'Dolny panel eksportowanego PNG odpowiada wybranej metryce '
         '(R_app, R/R_ref, Q, proxy albo RMS). Raport HTML zawiera metodykę '
         'na końcu, a Metodyka_obliczen.html jest samodzielną stroną. '
         'Dodatkowo eksportowane są ocena_K2.csv i Q_w_okresach_ON_OFF.csv. '
         'wszystkie_epizody.csv zawiera wyłącznie oscylacje, natomiast '
         'wszystkie_zdarzenia_termiczne.csv także przejścia T1/T2. '
         'Zapis konfiguracja.json zawiera ustawienia mocy, deklarację '
         'porównywalnych warunków chłodzenia oraz SHA-256 '
         'wszystkich czasów i odczytów. Stare konfiguracje bez SHA-256 '
         'wymagają potwierdzenia zgodności z CSV.'),
        ('Ograniczenia i niepewności',
         'Algorytmy K1/K2 i ON?/OFF? są heurystyczne, nie stanowią '
         'normatywnego dowodu rozruchu PHP. Niepewność termopar, '
         'pozycjonowanie czujników, straty przez izolację i naturalną '
         'konwekcję, nieznany rozkład strumienia ciepła oraz bezwładność '
         'wpływają na interpretację. Nie wykonuje się automatycznej '
         'propagacji niepewności ani bilansu energii. '
         'Wyniki należy potwierdzać powtarzalnymi próbami i niezależnym '
         'logiem zasilacza, jeśli dostępny.')
    ]

def as_text():
    return '\n\n'.join(title.upper() + '\n' + body for title,body in sections())

def as_html(*, embedded=False):
    inner = '\n'.join(f'<section><h3>{escape(title)}</h3><p>{escape(body)}</p></section>'
                      for title,body in sections())
    if embedded:
        return '<section class="panel" id="metodyka"><h2>Metodyka i obliczenia</h2>' + inner + '</section>'
    return ('<!doctype html><html lang="pl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Metodyka obliczeń 3D PHP Analyzer</title>'
            '<style>body{font:16px/1.65 Segoe UI,Arial,sans-serif;max-width:1000px;'
            'margin:auto;padding:30px;color:#243a4c;background:#f6f8fa}'
            'section{background:white;padding:14px 22px;margin:15px 0;border-radius:10px}'
            'h3{color:#135c79}p{white-space:pre-line}</style></head><body>'
            '<h1>3D PHP Analyzer — metodyka obliczeń</h1>' + inner + '</body></html>')
