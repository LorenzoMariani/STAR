# Report di passaggio: selettore di componenti per STAR

Data: 2026-10-13. Serve a riprendere il lavoro su un altro computer (e in una nuova conversazione) per integrare il modulo in STAR, aggiungere KPI, renderlo usabile quasi in tempo reale per una demo e disegnare l'interfaccia grafica.

## 0. Modifiche fatte in STAR il 2026-10-15 (progetto per la missione) - da integrare prima della prossima consegna

Su richiesta del responsabile di STAR il selettore progetta il CubeSat che la missione chiede (nuovo `star_selector/mission.py`, 19 test in `tests/test_mission.py`, 144 test in tutto):

1. **Solo i sottosistemi richiesti**, ognuno con il requisito da cui viene: bus sempre (struttura, OBC, EPS, batteria, celle solari, una radio e un'antenna **per ogni banda** nominata: UHF, VHF, S, X); unita' ADCS integrata per stabilizzazione, puntamento o immagini (ruote, magnetorquer, star tracker e sensori solari separati solo se un requisito li nomina, perche' le unita' ADCS del catalogo li contengono); GNSS per posizione, separazione sicura, collisioni o manovre; propulsione solo per manovre o per il delta-v di smaltimento che END-016 calcola nella stessa run; imager; terminale ottico.
2. **La classe piu' piccola** (1U, 3U, 6U, 12U) in cui stanno insieme (massa, volume, pila, ingombro "Fits" o "Undetermined"); una classe scelta dall'utente prevale, quella scritta nei requisiti e' solo riportata.
3. **Requisiti verificati con i dati pubblicati**: GSD e swath riportati alla quota dell'orbita (END-001), precisione di puntamento dell'ADCS, tre assi, bande, delta-v (impulso totale / somma delle masse pubblicate), massa. Se nessun componente li soddisfa: "Does not satisfy REQ-xxx (...): no ... in the database meets it".
4. **Gli altri sottosistemi a parte** ("Not required by this mission"), con il motivo e se entrerebbero insieme al progetto.
5. **Pannello solare della classe** (anche nel selettore per classe): quello fatto per la faccia della classe (`face`: 1U, 3U, 6U; il 12U usa i 6U), dispiegabile se i requisiti lo chiedono; prima il criterio di completezza sceglieva "Solar Panel 1U" anche per 3U e 6U.
6. **Batteria per la missione** (2026-10-16): capacita' >= energia che la batteria da' in un'orbita secondo END-004 della stessa run (scarica peggiore tra i modi volati, con il suo margine) / profondita' di scarica dei requisiti (o della batteria); se basta la batteria integrata in un EPS (`integrated_battery_wh`) la batteria separata va tra i non richiesti (un componente in meno a parita' di classe). Senza END-004 il requisito di profondita' di scarica e' "not verifiable".
7. **Radio per la missione** (2026-10-16): la radio della banda piu' bassa deve avere il ricevitore (telecomandi); con un imager la radio della banda piu' alta scarica le immagini: velocita' >= quella scritta nei requisiti, altrimenti la piu' alta pubblicata tra le radio della sola banda (la velocita' massima di una radio S/X e' della banda X) che entra nel progetto; se la radio comprende l'antenna ("+ ANT" nel nome) l'antenna separata della banda va tra i non richiesti.
8. **ADCS per la missione** (2026-10-16): nuovo campo `specs.form_factor_range_u` delle unita' ADCS (classi dichiarate dai fornitori, scritto da `tools/add_adcs_form_factors.py`, schema rigenerato): si sceglie l'unita' dichiarata per la classe; se nessuna, una per classi piu' grandi o non dichiarata; mai una solo per classi piu' piccole (`selector.adcs_tier`); i prodotti NLA solo se non c'e' altro; poi precisione di puntamento e tre assi dai requisiti. v6 in 6U: XACT-50 invece di XACT-15 (3U).
9. **Propulsore per la missione** (2026-10-16): `min_form_factor_u` dei propulsori rispettato (PM200 da 3U); con `select(..., electric_power_check=True)` (sempre nel progetto per la missione) un propulsore elettrico (gridded_ion, feep, pulsed_plasma) deve avere potenza in accensione <= potenza di picco del pannello scelto (vincolo nella ricerca esatta, `_pareto` tiene conto di potenza e impulso); propellente non tossico se richiesto; delta-v impossibile -> il propulsore con l'impulso piu' alto che entra. v6 in 6U: PM200 (12 W, 850 N s, 105 m/s) invece di NPT30-I2 (ionico, 65 W su un pannello da 18.4 W).
10. **Payload per la missione** (2026-10-16): `min_form_factor_u` rispettato anche per imager e terminali ottici (`selector.MIN_CLASS_SUBSYSTEMS`); tipo di immagine dai requisiti (`mission.IMAGE_TYPES` sulle bande spettrali pubblicate; push-broom esclude le camere "snapshot"), con priorita' tipo > GSD > swath; terminale ottico: tipo di collegamento e velocita'; per ogni sottosistema i prodotti NLA solo se non c'e' altro. Effetto sulla v6: 12U (l'unica camera con GSD <= 4 m, iSIM-90, e' dichiarata da 12U), swath ancora non soddisfatto.

Cambiato: `selector.select()` ha i parametri facoltativi `slots` (posti con componenti ammessi, `Slot`), `dv_m_s`, `mass_limit_kg` (senza parametri il risultato e' identico a prima); `SubsystemResult.subsystem`; `layout.stack_feasible` accetta anche [(sottosistema, altezza)] (due radio); `fit.check_fit` usa il sottosistema del posto (`placed[].slot`); `api.SelectorService.design()` e `selection_to_dict(..., mission=)` (campi `mission`, `subsystems[].subsystem`, `subsystems[].design`); la GUI mostra la ricerca della classe, il riquadro "Mission requirements", motivo e verifiche su ogni scheda e la sezione "Not required by this mission" (senza blocco `mission` e' come prima). In STAR: `BackEnd/runners/end019_runner.py` (`mission_context`: quote di END-001 e riepilogo di END-016 della run), `FrontEnd/star_frontend_v3.py` (`component_selector_design` per la GUI dal vivo), registro (classe facoltativa, END-001 ed END-016 a monte facoltativi) e IDD; le copie in `../star_integration/` sono allineate.

## 1. Come riprendere

1. Copiare l'intera cartella `star_component_selector/` (circa 37 MB, dentro ci sono dati, immagini, test e gli script in `tools/`).
2. Servono Python >= 3.10 e nient'altro per usare il selettore. Pillow e PyMuPDF servono solo agli script in `tools/` (estrazione di immagini e PDF).
3. Verifica che tutto funzioni:

```bash
python -m unittest discover -s tests -t .      # 74 test, circa 17 s
python -m star_selector validate               # 113 componenti
python -m star_selector select --form-factor 12 --mission eo --eo-max-gsd 3 --altitude 500 --mass-override spacemind-sm12=2
python -m star_selector platforms --details    # 8 piattaforme di riferimento (Tyvak e Terran Orbital)
```

4. Primo messaggio suggerito per la nuova conversazione: *"Leggi HANDOFF.md e README.md in star_component_selector. Il modulo e' un selettore di componenti CubeSat gia' funzionante (3U/6U/12U). Voglio integrarlo in STAR [descrivi stack di STAR], aggiungere i KPI della sezione 5, rendere la ricerca interattiva per una demo e fare l'interfaccia della sezione 7."*

**Non e' stato possibile verificare lo stack di STAR** (linguaggio, framework, database): nella conversazione non e' mai stato indicato. Va chiarito per primo, perche' decide se il modulo resta in Python (servizio) o viene riscritto.

## 1 ter. Aggiornamento del 2026-10-14: il selettore e' stato semplificato (leggere prima di tutto il resto)

Questo report descrive la versione precedente (profili di missione, posizionamento, bilanci, esclusioni, 113-158 componenti) e **non e' piu' valido** per selettore, GUI e comandi. Oggi: unico ingresso la classe CubeSat (1U, 3U, 6U, 12U); si rispettano solo i limiti di massa e volume (m3) della CDS Rev. 14.1; si sceglie almeno un componente per sottosistema (17 sottosistemi) privilegiando i dati pubblicati piu' completi; i dati non pubblicati restano "Not publicly available"; GUI sola lettura con riquadro Database (componenti, immagini, datasheet per classe), schede per sottosistema e pannello con immagine e datasheet PDF affiancati (cartelle `images/` e `datasheets/`). Catalogo di 232 componenti (pannelli solari 1U, categorie sensori solari e antenne GNSS, 20 ruote e 3 star tracker aggiunti il 2026-10-15), 125 test; controllo di ingombro e vista **Placement** con forme semplificate (`shape`) e componenti impilati lungo l'asse lungo (`layout.py`) (pannelli solari, antenne, sensori solari e antenne GNSS esterni: regola dichiarata); validazione in `audit/AUDIT_REPORT.md` (dati contro datasheet, selettore contro ricerca esaustiva, confronto con Tyvak Triumph e Renegade). Riferimento aggiornato: `README.md` e `../Orchestrator and gui/README_END019_Component_Selector.md`. Le sezioni sotto restano come storia del lavoro.

## 1 bis. Aggiornamento: GUI e collegamento con STAR (2026-10-14)

Dopo la stesura di questo report sono stati aggiunti: livello dati JSON (`star_selector/api.py`), server locale (`python -m star_selector serve`), GUI con vista esplosa e dettaglio componente (`gui/component_selector.html`), blocco/esclusione di componenti, limite di tempo della ricerca, e il modulo **END-019** per l'orchestratore STAR (registro YAML, documento RAG, runner, tab nei risultati, metodi `StarApi`). Test: 97, tutti passano. Le sezioni 5-7 qui sotto (KPI, tempo reale, GUI) sono in gran parte realizzate: vedi README.md ("Interfaccia grafica e integrazione in STAR") e `../Orchestrator and gui/README_END019_Component_Selector.md`. Restano da fare: provare i metodi `component_selector_*` nella finestra pywebview reale, il formato esatto di `input_power_budget.json` per il passaggio a END-004, una vista 3D (oggi proiezione isometrica in SVG) e i dati mancanti elencati nella sezione 4.

Aggiornamento successivo: aggiunti **6 star tracker** (nuova categoria `star_tracker`) e **5 terminali ottici** (payload `optical_terminal`: CubeLCT, CubeCAT, SCOT20, SCOT30, SCOT80), i profili `isl-optical` e `optical-downlink`, i messaggi dell'API in inglese (`lang: "en"`, regole in `star_selector/i18n.py`), la GUI in inglese con forme semplificate dei componenti. Il catalogo ha ora 124 componenti e 109 test. Il punto 4 della sezione 4 sull'assenza di terminali ottici ISL e' superato: resta valido che solo il SCOT20 entra in un CubeSat.

[RIMOSSO il 2026-10-14, la disposizione dei componenti non si calcola piu'] Livello 1 di posizionamento: `star_selector/placement.py` (regole di montaggio, controlli di campo di vista, baricentro e inerzia contro la CDS Rev. 14.1 Tabella 2), usato dalla vista esplosa. 125 test.

Dimensioni dei componenti raccolte per il livello 2: 104 componenti su 124 (88 dichiarate, 13 da formato normato, 3 derivate dalla taglia nominale), vedi README. Mancano soprattutto i moduli EnduroSat (CAD dietro modulo).

[RIMOSSO il 2026-10-14] Posizionamento livello 2: `placement.place(..., use_dimensions=True)` usa le quote (vedi README, sezione Disposizione livello 2); nuovi controlli fit/overlap/dims_used; test in `tests/test_placement_l2.py`.

Propulsione, antenne e GNSS: tre nuove categorie opzionali (catalogo a 158 componenti), delta-v con l'equazione del razzo, copertura di banda delle antenne, accuratezza GNSS 1-sigma, controllo geometrico di lunghezza e sezione nella ricerca; vedi README, sezione Propulsione, antenne e GNSS; test in `tests/test_extras.py`. Ricerche senza progetti fattibili: limite di tempo di 60 s nell'API.

Dal 2026-10-14 la GUI mostra una galleria di schede (una per componente, con la forma del sottosistema) al posto della vista esplosa: nessun posizionamento, baricentro, inerzia o controllo geometrico. `placement.py` e i suoi test sono stati eliminati; le quote `dimensions` restano nel catalogo come sola informazione. La GUI e' solo in inglese.

## 2. Stato attuale

| Cosa | Stato |
|---|---|
| Catalogo `data/catalog.json` | 113 componenti reali da datasheet pubblici, 8 categorie (structure, obc, eps, battery, solar_panel, comms, adcs, payload), ogni valore con fonte, `verified: false` ovunque, `null` = non dichiarato dal fornitore (mai stimato) |
| Immagini `images/` | 111 PNG `Venditore-NomeComponente.png` (nessuna foto pubblica per le due iSIM-170), piu' 8 delle piattaforme; fonte di ciascuna in `manifest.csv`, nei metadati PNG e nel campo `image` |
| Schema | `schema/component_catalog.schema.json` (generato da `export-schema`, riutilizzabile da qualunque stack) |
| Selettore | taglie 3U, 6U, 12U; profili `generic`, `eo`, `ssa`, `isl-rf` (e `isl-optical`, che risponde con un errore perche' non ci sono terminali ottici); obiettivi `mass`, `cost`, `margin`, `heritage`, `performance`; puntamento richiesto ricavato dal campo di vista del payload e rispettato dall'ADCS |
| Piattaforme | `data/platforms.json`: Tyvak Triumph, Renegade, Nebula e Terran Orbital Voyager, Excelsior, Ambassador, Enterprise, SmallSat GEO. Solo consultazione, non usate dal selettore |
| Test | 74, tutti passano |
| Prestazioni (portatile di sviluppo, avvio Python incluso) | 0.5 s (SSA 12U), 1.4-2.6 s (ISL, EO con `performance`), 6 s (EO con obiettivo `mass`) |

### Mappa dei file

| File | Contenuto |
|---|---|
| `star_selector/models.py` | campi comuni + `SPEC_FIELDS` per categoria (unica definizione), validazione, export JSON Schema, `load_catalog` |
| `star_selector/selector.py` | `Mission` (tutti i parametri e le ipotesi), compatibilita', dimensionamento, `evaluate()`, `search()`, profili, puntamento, obiettivi |
| `star_selector/cli.py` | comandi `select`, `list`, `validate`, `platforms`, `export-schema` |
| `star_selector/report.py` | galleria HTML autonoma dei progetti con immagini e fonti (`--html`) |
| `star_selector/platforms.py` | caricamento e validazione delle piattaforme complete |
| `tests/test_selector.py` | 74 test (catalogo, compatibilita', EO, profili, piattaforme, equivalenza ricerca potata/esaustiva) |
| `tools/` | script che hanno generato il catalogo e le immagini (vedi nota sotto) |

**Nota su `tools/`:** `gen_real.py` e' il generatore storico del catalogo, ma dopo la sua ultima esecuzione `catalog.json` e' stato modificato direttamente (strutture 12U con `add_12u.py`, `min_form_factor_u` delle iSIM-170 con `fix170.py`). **Da qui in poi `catalog.json` e' la fonte di verita'**: rigenerarlo con `gen_real.py` farebbe perdere quelle modifiche. Gli script usano percorsi passati da riga di comando e cartelle di lavoro temporanee: sono documentazione di come sono stati ricavati i dati, non strumenti pronti all'uso.

## 3. Come ragiona il selettore (da conoscere prima di toccarlo)

1. **Pool per categoria**, filtrati per componente singolo: massa dichiarata (o `--mass-override`), non `nla`, TID, taglia della struttura, data rate, radio non solo-TX, puntamento esplicito, requisiti del payload.
2. **Combinazioni potate a coppie attorno all'EPS** (batteria, pannelli, tensioni, interfacce, facce della struttura) e deduplicate (tra componenti identici nei dati modellati si tiene il piu' leggero).
3. **`evaluate()` e' l'arbitro finale**: compatibilita' (taglia, facce, famiglia/tensione batteria, tensione PV e tensione a vuoto, alimentazioni, interfacce dati, ricevitore per l'uplink, TID, `nla`), poi dimensionamento (orbita circolare beta = 0, bilancio energetico medio con fattore di illuminazione 0.4, numero minimo di pannelli, batterie esterne in parallelo max 4 o integrate nell'EPS, margini del 20% su massa e potenza, cicli batteria, massa totale contro il limite della struttura: 3U 6 kg, 6U 12 kg, 12U 24 kg).
4. **Dati mancanti:** compatibilita' con un lato `null` = controllo saltato + avviso; valore necessario al calcolo = ipotesi di `Mission.assumed_*` + avviso; requisito esplicito = componente scartato; `--strict` scarta tutto cio' che usa un dato mancante.
5. **Profili:** il payload e' una camera/telescopio (`eo`, `ssa`) oppure una **seconda radio** scelta tra quelle di comunicazione (`isl-rf`). Il payload viene valutato dopo la piattaforma da sola (un payload aggiunge solo massa, potenza e volume).
6. **Puntamento:** errore massimo = `pointing_fov_fraction` (10%) del campo di vista del payload. Un ADCS senza accuratezza dichiarata (CubeSpace) e' ammesso con avviso solo se il requisito e' piu' largo di 1 deg (`pointing_undeclared_ok_deg`). `--max-pointing` e' esplicito e, se piu' stretto, prevale.
7. **`performance`:** ottimo lessicografico (GSD migliore per EO, apertura maggiore per SSA, data rate maggiore per ISL, poi massa): si cerca per gruppi di payload con la stessa prestazione, dal migliore.
8. **Velocita':** limite inferiore di massa che salta intere combinazioni, cache della piattaforma da sola, valutazione "quiet" (gli avvisi si raccolgono solo per i progetti restituiti). Due test confrontano la ricerca potata con quella esaustiva.

### Formato JSON (`select --json`), base per un'API

```
{ "evaluated": int,
  "designs": [ { "parts": {categoria: id | null}, "n_panels": int, "n_batteries": int,
                 "metrics": { mass_total_kg, mass_free_kg, power_avg_w, power_peak_w, power_margin, battery_dod, battery_cycles,
                              volume_u, eo_gsd_m, eo_swath_km, payload_fov_deg, payload_aperture_mm, isl_data_rate_kbps,
                              pointing_required_deg, pointing_origin, adcs_pointing_deg, perf_score,
                              price, price_currency, min_heritage, all_verified },
                 "warnings": [str] } ],
  "rejections": [[motivo, conteggio]] }
```

## 4. Limiti e decisioni aperte (cose da sapere o da decidere)

**Dati mancanti**
- **Nessun terminale ottico ISL nel catalogo.** I terminali ottici CubeSat trovati (AAC CubeCAT: 1U, circa 1 kg, 10.8 W, 1 Gbit/s) sono per il collegamento con la Terra; per l'ISL ottico non c'e' un datasheet pubblico con massa, consumo e puntamento richiesto. Il profilo `isl-optical` e' pronto a livello di CLI ma risponde con un errore. Servono dati dai fornitori (Tesat CubeLCT, Skyloom, Mynaric, ecc.) via richiesta commerciale.
- **ISL radio:** si usa una seconda radio del catalogo (le S-band bidirezionali; le X-band del catalogo sono solo trasmettitori). Antenne, guadagno, distanza e link budget non sono modellati.
- **Star tracker, ruote di reazione, magnetorquer** non sono componenti singoli (solo ADCS completi: CubeSpace, Pumpkin/MAI, Blue Canyon XACT, Hyperion). Servirebbero tre categorie nuove e una scelta ADCS "componente per componente", citata come possibile passo successivo. I tre star tracker Terran Orbital M10, H6, F4 (annunciati il 25 marzo 2026) non hanno ancora dati pubblici.
- **ADCS:** solo gli XACT dichiarano un puntamento stretto (0.007 deg, 25 arcsec); MAI e iADCS dichiarano 1 deg; CubeSpace non dichiara nulla. Quindi ogni requisito sotto 1 deg seleziona un XACT (RS-422: serve un OBC RS-422).
- **12U:** solo tre strutture (GomSpace, AAC da scheda di terzi su satsearch, Spacemind senza massa). Mancano EnduroSat e ISISpace 12U perche' non hanno dati dal fornitore. L'immagine dello ZAPHOD 12U potrebbe non essere quella giusta (nota nel catalogo).
- **Piattaforme complete** (Tyvak, Terran Orbital): massa e consumi dei singoli moduli non sono pubblici, quindi non entrano nel selettore. Se serve una categoria "piattaforma" va decisa la regola (la piattaforma sostituisce struttura + OBC + EPS + ...?).
- **Prezzi:** solo CubeSpace e Pumpkin (USD) e NanoAvionics e Spacemind (EUR) li pubblicano; il costo di un progetto quasi sempre risulta "n.d.".

**Rischi legali e di qualita'**
- `verified: false` ovunque: nessun valore e' stato ricontrollato da una persona. Prima di usare i risultati in un progetto vero va fatto un controllo a campione sui datasheet.
- I datasheet GomSpace portano un avviso di confidenzialita': serve il loro consenso prima di condividere il catalogo fuori dal gruppo di lavoro.
- Le immagini appartengono ai produttori: sono riferimento visivo; per presentazioni esterne serve il permesso.
- Modello semplificato: orbita circolare con beta = 0, nessun link budget, nessuna analisi termica o vibrazionale, nessun volume interno (dati di ingombro mancanti per quasi tutto). Le ipotesi sono tutte parametri di `Mission`.

## 5. KPI da aggiungere (proposta)

Gia' calcolati e solo da esporre: massa totale e libera (%), potenza media e di picco, margine energetico, DoD e cicli batteria, GSD, swath, campo di vista, apertura, data rate ISL, puntamento richiesto contro quello dell'ADCS, heritage minimo, % di dati verificati.

Nuovi, in ordine di valore per una demo:

| KPI | Come calcolarlo | Dato che manca |
|---|---|---|
| **Margine di puntamento** | accuratezza ADCS / errore richiesto (in dB o in %) | niente |
| **Affidabilita' del progetto** (punteggio di fiducia) | 1 meno la quota di dati usati ma non dichiarati (numero di avvisi, parametri `assumed_*` usati) | niente: gia' nei `warnings` |
| **Maturita'** | TRL e flight heritage minimi e medi dei componenti | niente (campi comuni) |
| **Rischio di fornitura** | numero di componenti `nla` o ITAR, numero di fornitori distinti | flag ITAR da aggiungere nel catalogo (oggi solo nelle note) |
| **Area coperta al giorno** | swath x velocita' al suolo x durata acquisizione x orbite al giorno (`imaging_duty`) | niente (formula nota) |
| **Dati prodotti per orbita** | pixel across-track x righe/s x bit, contro il data rate del downlink | bit per pixel e frame rate (payload) |
| **Volume di dati scaricabile per passaggio** | data rate comms x durata del passaggio in visibilita' (dipende dalla stazione a terra) | modello di stazione e quota |
| **Margine di radiazione** | TID del componente meno TID della missione (quota, durata) | modello di dose (SPENVIS o tabella) |
| **Costo** | somma dei prezzi quando tutti noti, con intervallo se alcuni mancano | prezzi |
| **Compatibilita' del progetto** | numero di controlli saltati per dato mancante | niente |
| **Durata orbitale / decadimento** | quota e rapporto balistico | area e Cd (non nel catalogo) |

Consiglio: presentare **tre KPI di sintesi** (Massa/Potenza, Prestazione di missione, Affidabilita' dei dati) e mostrare gli altri a richiesta.

## 6. Come renderlo quasi in tempo reale per la demo

Oggi ogni `select` parte da zero (circa 0.2 s di avvio Python + 0.3-6 s di ricerca). Per una demo interattiva:

1. **Tenere il processo caldo.** Caricare il catalogo una volta e chiamare `search()` da un servizio (FastAPI/Flask) o direttamente in STAR se e' in Python. L'avvio scompare.
2. **Cache della piattaforma da sola.** `search()` ha gia' una cache interna per chiamata; spostarla a livello di servizio (chiave = componenti + parametri di piattaforma, escluso il payload) rende immediato il cambio di payload o di requisito EO con la stessa piattaforma.
3. **Ricerca "anytime".** Aggiungere un limite di tempo o di valutazioni che restituisce il miglior progetto trovato finora: l'interfaccia mostra subito un risultato e lo migliora in due passate.
4. **Componenti bloccati ed esclusi.** Parametri `locked={categoria: id}` e `excluded=[id]` (e filtro per fornitore) che restringono i pool: e' anche la funzione piu' naturale per l'interfaccia (blocco un componente, ricalcolo il resto) e velocizza molto.
5. **Preset di missione** (EO 3 m 6U, SSA 12U, ISL S-band) con risultati precalcolati: nel peggiore dei casi la demo parte da un risultato gia' pronto.
6. **Risultati incrementali nell'interfaccia:** ricerca con `top` piccolo (3) mentre l'utente muove un cursore, ricerca completa quando lo rilascia.
7. **Misurare prima di ottimizzare:** i tempi attuali sono gia' sotto 3 s per quasi tutto; il costo e' dominato dalle valutazioni della piattaforma (circa 100 µs l'una, 50-270 mila combinazioni). Se serve ancora: parallelizzare per EPS (ogni EPS e' una partizione indipendente) con `multiprocessing`, oppure riscrivere solo `evaluate()` in un linguaggio compilato.
8. **Rendere i controlli dichiarativi:** `compat rules` e `sizing` oggi sono funzioni Python; per STAR in TypeScript conviene tradurre le regole una volta, tenendo come test di non regressione l'insieme di casi di `tests/test_selector.py` (i 74 casi sono la specifica).

## 7. Idee per l'interfaccia grafica

**Struttura della pagina** (due colonne, responsive; stessa sorgente dati del `--json`):

- **Pannello di controllo (sinistra).** Profilo di missione (EO / SSA / ISL radio / ISL ottico, quest'ultimo disabilitato con la spiegazione "nessun terminale nel catalogo"), taglia 3U/6U/12U, quota e durata, requisiti del profilo (GSD, swath, bande; apertura e campo di vista; banda e data rate ISL), puntamento (cursore, con indicazione di cosa lo guida: richiesto dall'utente o ricavato dal campo di vista del payload), obiettivo (massa, prestazione, costo, margine, maturita'), interruttori (ammetti `nla`, solo dati verificati, ammetti radio solo TX, modalita' strict), filtro per fornitore, preset di missione. Un pulsante "perche' non esce niente?" che mostra i motivi di scarto (`rejections`) in italiano.
- **Vista principale (centro): satellite in vista esplosa.** Disegno 3D (three.js) o isometrico SVG del CubeSat con le proporzioni della taglia (3U 1x1x3, 6U 1x2x3, 12U 2x2x3) e i componenti separati lungo l'asse lungo:
  - struttura come telaio trasparente al centro;
  - pannelli solari staccati verso l'esterno sulle facce usate (con il numero scelto, uguale a `n_panels`);
  - pila interna esplosa lungo l'asse: EPS e batteria, OBC, radio (e radio ISL), ADCS, payload verso il lato nadir con l'ottica visibile;
  - per ogni parte: foto del componente (dalla cartella `images/`) come etichetta/miniatura, nome, fornitore e massa; linee guida che collegano il pezzo alla sua etichetta.
  - Interazioni: passaggio del mouse evidenzia il pezzo; **clic su un pezzo apre il pannello di dettaglio**; pulsante "esplodi/ricomponi" animato; rotazione e zoom; interruttore per vista 2D semplice (utile se la demo gira su un portatile senza WebGL).
- **Pannello di dettaglio del componente (cassetto destro).** Foto grande con la sua fonte (link, vedi `image.page_url`); nome, fornitore, famiglia; specifiche principali per categoria (le stesse di `SPEC_FIELDS`); massa, consumo, prezzo, TRL, heritage, TID; stato (`nla`, verificato o no); **link al datasheet** (`source.url`) e al documento di origine; note del catalogo; avvisi su cio' che e' `null` o assunto; **alternative**: i migliori componenti della stessa categoria compatibili col resto del progetto (da `search()` con `locked` sulle altre parti), con pulsante "sostituisci" che ricalcola.
- **Cruscotto KPI (in alto o in basso):** tre schede di sintesi (Massa e potenza, Prestazione di missione, Affidabilita' dei dati), barra di massa impilata per componente, bilancio di potenza media e di picco, grafico energia generata contro consumata nell'orbita (luce/eclisse), indicatori semaforo per puntamento, TID, DoD, margine di massa.
- **Classifica dei progetti:** i primi 3-5 come schede confrontabili (stessi colori per gli stessi componenti), grafico a dispersione massa contro prestazione per vedere il compromesso, confronto affiancato di due progetti (cosa cambia e perche').
- **Esportazione:** la galleria HTML esistente (`report.py`) come base per un report PDF o HTML con immagini, fonti e avvisi; esportazione JSON per STAR.

**Dettagli di usabilita' per la demo:** componenti con dati mancanti marcati in modo visibile (icona e tooltip "dato non dichiarato, assunto X"); un progetto "affidabile" (pochi avvisi) distinto da uno "da verificare"; modalita' "spiega" che racconta in una frase perche' un ADCS e' stato scelto ("serve puntamento 0.15 deg: solo gli XACT lo dichiarano"); colori per categoria coerenti tra vista esplosa, barre di massa e tabelle.

**Stack consigliato (da confermare con lo stack di STAR):** se STAR ha un front-end web, servizio Python (FastAPI) che espone `/select`, `/components/{id}` (JSON del catalogo piu' immagine) e `/rejections`; front-end con three.js per la vista esplosa e un grafico a barre/dispersione (Plotly o Chart.js). Le immagini vanno servite come file statici dalla cartella `images/`. Se STAR e' un'applicazione desktop o in un altro linguaggio, esportare il catalogo con lo JSON Schema e riscrivere le regole (sezione 6, punto 8).

## 8. Ordine di lavoro consigliato

1. Chiarire lo stack di STAR e dove deve vivere il modulo (servizio o libreria).
2. Esporre `search()` come servizio con `locked`/`excluded` e limite di tempo, mantenendo i test attuali come rete di sicurezza.
3. Aggiungere i KPI della sezione 5 (prima quelli senza dati mancanti) alle metriche restituite.
4. Interfaccia: prima il pannello di controllo e la classifica con il cruscotto KPI, poi la vista esplosa con clic sul componente e il cassetto di dettaglio.
5. In parallelo (dati): richiedere ai fornitori i dati mancanti piu' utili (terminali ottici ISL, star tracker/ruote/magnetorquer con datasheet, strutture 12U EnduroSat e ISISpace, masse delle voci a `null`) e far verificare a mano un campione del catalogo.
