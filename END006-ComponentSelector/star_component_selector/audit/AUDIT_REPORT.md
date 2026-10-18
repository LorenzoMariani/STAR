# Validazione del selettore e del catalogo (2026-10-15)

Tre controlli: **A** dati del catalogo contro i datasheet locali, **B** correttezza del selettore contro una ricerca esaustiva indipendente (con un errore trovato e corretto), **C** plausibilita' rispetto alle piattaforme Tyvak Triumph 6U e Renegade 12U.

## A. Dati del catalogo contro i datasheet locali

Script: `python tools/audit_datasheets.py` (solo lettura; scrive `audit/audit_datasheets.csv` e `audit/audit_summary.json`). Per ognuno dei **150 componenti con datasheet locale** (90 PDF in `datasheets/`) cerca nel testo del PDF (nelle sole pagine che nominano il prodotto, se il documento ne contiene molti): la massa, le tre dimensioni e ogni specifica numerica del catalogo. Non tocca `verified`: quel campo resta `false` finche' una persona non ha controllato.

## Risultati

| Controllo | Esito |
|---|---|
| PDF senza testo estraibile | 0 |
| Massa | 99 trovate con l'unita' (g o kg); 39 trovate come numero in una tabella (unita' nell'intestazione); 7 non trovate; 5 non pubblicate (null) |
| Dimensioni | 116 componenti con tutte e tre le quote trovate; 5 parziali e 6 non trovate; 23 non controllabili (quote derivate dalla taglia o assenti). Le due non trovate in piu' sono i DHV-1U, le cui quote (82.8 x 97.8 e 97.8 x 97.8 mm) sono in un disegno e le ho lette a vista |
| Specifiche numeriche | 413 trovate su 435 controllate (811 voci non numeriche o booleane non cercate) |

**Nessun valore del catalogo e' risultato in contraddizione con il suo datasheet, tranne un caso documentato.** Ho letto nel PDF ogni voce non trovata:

- **Massa non trovata (7).** Tra queste anche NanoCom Link SX (629 g = 315 + 123 + 150 + 41 g, somma derivata dei moduli e dei cavi, dichiarata nelle note); le altre due varianti Link (S e X) e le dimensioni di Link S (spessore 23.85 mm solo nel disegno) sono dello stesso tipo, e la potenza a riposo di Link SX (8.8 W) e' una somma derivata dei moduli.
  - OPTIMUS-30/-40/-80: il catalogo usa la pagina prodotto attuale (288 / 360 / 720 g, scelta dichiarata nelle note come piu' prudente), il PDF del 2020 riporta 268 / 335 / 670 g. **E' l'unica vera discrepanza**: nel pannello il datasheet mostra i valori piu' bassi.
  - XACT-100 (0.52 kg + 1 kg di ruote = 1.52 kg), BIT-3 (1.28 kg a secco + 1.50 kg di propellente = 2.78 kg) e PM200 (1100 g + 310 g = 1.41 kg): somme, dichiarate nelle note.
- **Massa trovata solo come numero (26).** Confermate leggendo il contesto: tabelle con l'unita' nell'intestazione (L3Harris MPS, CU Aerospace CHIPS, VACCO, AAC RW210, CubeADCS "<500"), oppure somme dichiarate nelle note (Pumpkin PPM A2-D2, MAI-100 = 865 + 20 g, MAI-200, GomSpace P60 = 80 + 54 + 47 g).
- **Dimensioni non trovate (8).** Spiegate: Blue Canyon batteries in pollici (1.8 x 4.2 x 3.5 in = 45.7 x 106.7 x 88.9 mm), Pumpkin PPM con ingombro PC/104 (`basis: standard`) e GomSpace P60 (quote dalla pagina del fornitore, indicato nella nota).
- **Specifiche non trovate (17).** Cambi di unita' (precisione XACT 25 arcsec = 0.00694 deg; SRX-8 1.4 Gbit/s = 1,400,000 kbps), valori derivati e dichiarati come tali (swath NanoCam, impulso totale BIT-3, potenza GST-600 e GSW-600, TX AX100 = 0.8 A x 3.3 V, forma minima di SCOT30/80), Isp VACCO 40 s (scritto "40 sec" con puntini), 128 W del P60 (pagina del fornitore).

## Limiti del controllo

- Trovare un numero nel testo non prova che sia la stessa grandezza: e' un controllo di coerenza, non una rilettura. Le 26 masse "solo numero" le ho riguardate a mano; le specifiche trovate (240) e le dimensioni (78) no.
- Copre solo i 150 componenti con PDF. Gli altri 82 hanno come fonte una pagina web (o un PDF non raggiungibile) e non sono stati controllati.
- Valori dei cataloghi con piu' prodotti (EnduroSat, Blue Canyon) sono cercati nelle pagine che nominano il prodotto, quando si riescono a individuare.
- Il campo `verified` resta `false` per tutti i componenti.

## B. Correttezza del selettore (`tests/test_validation.py`, 7 test)

- **Confronto con una ricerca esaustiva.** 240 cataloghi casuali (classi 1U, 3U e 6U, 6 sottosistemi, 2-4 candidati ciascuno, valori non pubblicati a caso): per ognuno una funzione indipendente prova tutte le combinazioni e il risultato di `select()` deve avere la stessa completezza totale e la stessa massa. Include i casi in cui i limiti non ammettono soluzione (il selettore deve dichiararlo).
- **Errore trovato e corretto.** La ricerca esatta (usata solo quando la scelta migliore di ogni sottosistema supera i limiti) non controllava i limiti sull'ultima combinazione completa: poteva restituire `within_limits = True` con una massa oltre il limite (visto con un 1U sintetico: 2.52 kg contro 2 kg). Corretto in `star_selector/selector.py`. Sul catalogo reale il risultato non cambia (1U: non entra tutto, segnalato; 3U, 6U, 12U: entra tutto con la prima scelta), quindi nessun risultato mostrato finora era sbagliato.
- **Invarianti sul catalogo reale, per 1U, 3U, 6U e 12U.** I componenti scelti rispettano massa e ingombro; massa, volume e potenza totali sono la somma dei valori del catalogo; la struttura e' della classe; due esecuzioni danno lo stesso risultato; le alternative entrano tutte e non contengono il componente scelto; cio' che entra in una classe entra in quella piu' grande; ogni sottosistema senza componente ha una scheda con il motivo; nessun numero e' inventato (massa e potenza coincidono con quelle del catalogo).
- Totale test del progetto: **125**, tutti passano (dopo il controllo di ingombro, le forme e la pila, sezione D). L'oracolo include ora anche la pila a serpentina.

## C. Confronto con le piattaforme di riferimento (`tools/validate_platforms.py`, `audit/platform_comparison.json`)

Solo due piattaforme sono confrontabili: **Tyvak Triumph (6U)** e **Tyvak Renegade (12U)**. Terran Orbital Voyager e' un 16U (fuori dalle classi 1U/3U/6U/12U) e le altre cinque piattaforme sono molto piu' grandi.

| | Triumph 6U | Renegade 12U |
|---|---|---|
| Massa di lancio massima dichiarata | 14 kg | 25 kg |
| Limite CDS Rev. 14.1 della classe | 12 kg | 24 kg |
| Massa di bus della piattaforma (lancio − payload massimo) | 9 kg | 15 kg |
| Selettore: massa dei sottosistemi di bus, un componente ciascuno | 1.95 kg | 2.67 kg |
| Selettore: stesso, con le quantita' della piattaforma (2 star tracker, 3 ruote, 2-3 batterie) | 2.33 kg | 3.34 kg |
| Rapporto con la massa di bus | 22-26 % | 18-22 % |
| Selettore: massa totale, 17 sottosistemi con payload | 4.16 kg (30 % della massa di lancio) | 4.88 kg (20 %) |
| Potenza dichiarata dei componenti scelti | 32.4 W | 32.4 W |
| Potenza dell'array solare della piattaforma | 100 W | 100 W |

Letture e limiti:

- **Le due piattaforme dichiarano masse di lancio sopra il limite CDS Rev. 14.1 della loro classe** (14 kg contro 12 kg, 25 kg contro 24 kg): sono valori del fornitore per i loro dispenser. Il selettore usa il limite CDS, come richiesto.
- **La selezione e' molto piu' leggera del bus delle piattaforme (circa un quarto).** E' coerente con la direzione attesa (un componente per sottosistema e' un'approssimazione per difetto: mancano cablaggio, minuteria, redundanza, margini, struttura e array solare di una piattaforma di 100 W: il selettore sceglie un solo pannello), ma non lo dimostra: **non esiste una massa di riferimento misurata** con cui chiudere il conto e la differenza di circa 6-12 kg non e' spiegata da dati.
- **Moduli della piattaforma senza categoria nel catalogo:** backplane, sensori solari grossolani, IMU. Sono lacune del catalogo da valutare (il selettore oggi non li cerca).
- **Sottosistemi del selettore non elencati tra i moduli:** struttura, pannelli solari, antenna, ADCS integrato, propulsione e payload (la piattaforma li tratta come opzioni o parti a parte).
- **Sovrapposizione funzionale non controllata:** la scelta dell'ADCS (es. un'unita' integrata con ruote e magnetorquer) insieme a ruote, magnetorquer e star tracker separati duplica funzioni. Il selettore non lo controlla perche' verifica solo massa e volume.
- La potenza dichiarata (32.2 W) e' la somma dei massimi dichiarati dai fornitori dei componenti scelti, con un componente senza dato (Pumpkin Linear EPS 11 Wh): non e' confrontabile in modo stretto con i 100 W di un array, che e' una capacita' di generazione e non un consumo.
- I valori delle piattaforme sono `verified: false`.

## D. Controllo di ingombro (aggiunto il 2026-10-15, `tests/test_fit.py`, 9 test)

Il volume del selettore ora conta solo i componenti interni (pannelli solari, antenne, sensori solari e antenne GNSS sono esterni: **regola dichiarata**) e un controllo separato dice se le scatole con le quote pubblicate entrano nell'ingombro CDS. Test: disposizioni trovate valide (dentro l'ingombro, senza sovrapposizioni, rotazioni di 90 gradi: 150 casi casuali), casi noti, i quattro stati, componenti esterni appoggiati a una faccia con le quote pubblicate.

| Classe | Volume interno / ingombro | Esito |
|---|---|---|
| 1U | 236 % | Does not fit |
| 3U | 56 % (dopo la pila; prima 97 %) | Fits (pila) |
| 6U | 40 % | Fits (12 componenti interni) |
| 12U | 18 % | Fits (12 componenti interni) |

Il 3U, prima dato come "entra" al 99 % del volume e poi "Not shown to fit" al 97 %, ora sceglie una combinazione che entra nella pila (2.449 kg, volume interno 56 %): la lunghezza della pila e' diventata un vincolo della selezione. Limite: l'euristica puo' dimostrare che i pezzi entrano, non che non entrano; pareti, guide, connettori e zone di rispetto non sono pubblicati e non sono modellati.

## Cosa non e' stato possibile validare

Non ci sono dati di volo o di collaudo con cui confrontare la scelta, ne' una massa misurata di un CubeSat completo costruito con questi componenti. I tre controlli dicono che i dati sono fedeli ai documenti (dove il documento e' stato scaricato), che le regole sono applicate correttamente e che il risultato e' plausibile in ordine di grandezza; non dicono che la scelta sia ottimale per una missione.
