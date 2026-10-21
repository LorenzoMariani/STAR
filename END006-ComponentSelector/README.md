# END-006 — Component Selector

END-006 progetta il satellite di una missione STAR come CubeSat (1U, 3U, 6U, 12U), scegliendo i componenti da un catalogo di prodotti reali costruito da documenti pubblici dei fornitori.
Sceglie solo i sottosistemi che la missione chiede.
Cerca la classe più piccola che li porta nel rispetto dei limiti di massa e volume della CubeSat Design Specification (CDS Rev. 14.1).
Verifica i requisiti con i dati pubblicati.

In STAR lavora due volte:
- **all'inizio del workflow (progetto iniziale):** definisce il satellite che usano tutti gli altri moduli;
- **alla fine (progetto finale):** ripete la scelta con i risultati degli altri moduli e dice cosa cambia.

> La guida completa (regole di scelta, catalogo, interfaccia grafica, note sui dati per fornitore) è [star_component_selector/README.md](star_component_selector/README.md); per riprendere il lavoro sul modulo, [star_component_selector/HANDOFF.md](star_component_selector/HANDOFF.md).

## In breve

| | |
|---|---|
| Linguaggio | Python ≥ 3.10, solo libreria standard (Pillow solo per alcuni test e per gli strumenti delle immagini) |
| Pacchetto | `star_component_selector/star_selector/` (`SelectorService` in `api.py`) |
| In STAR | `BackEnd/runners/end006_runner.py` (`run_end006`) |
| Catalogo | `star_component_selector/data/catalog.json`, 236 componenti di 16 categorie |
| Durata in STAR | pochi secondi |

## Cosa fa

- **Sottosistemi chiesti dalla missione:**
  - il bus sempre: struttura, computer di bordo, EPS, batteria, pannelli solari;
  - una radio e un'antenna per banda;
  - l'unità ADCS per puntamento o immagini; ruote, magnetorquer, star tracker e sensori solari separati solo se nominati;
  - GNSS per posizione, separazione o manovre;
  - propulsione per manovre o per il Δv di smaltimento;
  - imager e terminale ottico.
- **Classe più piccola** che porta quei sottosistemi: massa, volume, pila dei componenti interni, ingombro. Nella classe vince la massa minima, poi la completezza dei dati pubblicati. Una classe scelta dall'utente prevale; una classe scritta nei requisiti viene solo riportata.
- **Verifica dei requisiti con i dati dei fornitori:**
  - GSD e swath alla quota dell'orbita;
  - puntamento, Δv, bande e velocità dei collegamenti, massa;
  - capacità della batteria;
  - interfacce comuni tra il computer di bordo e gli altri componenti;
  - tensioni e potenze dell'EPS;
  - momento delle ruote e dipolo dei magnetorquer necessario a scaricarle in un'orbita.

  Quando nessun componente soddisfa un requisito lo scrive ("Does not satisfy REQ-xxx …").
- **Nessuna stima:** un dato non pubblicato resta `null` e la scheda scrive "Not publicly available".
- **Controllo d'ingombro:** dispone i componenti nella pila e dice se il progetto entra nell'ingombro CDS.

## Come funziona

1. **Requisiti → parametri** (`requirements_to_params`): dal testo dei requisiti ricava cosa serve, senza inventare valori. Una missione fuori dal dominio, cioè senza CubeSat o con un requisito non realizzabile da un CubeSat, viene saltata.
2. **Progetto** (`SelectorService.design`, `star_selector/mission.py`): sceglie i sottosistemi, la classe e i componenti con una ricerca esatta sulle combinazioni.
3. **Ingombro** (`star_selector/layout.py`, `fit.py`): pila dei componenti interni lungo l'asse lungo, poi disposizione generica se la pila non entra. Esito: "Fits", "Does not fit", "Not shown to fit" o "Undetermined".
4. **Satellite per gli altri moduli** (solo progetto iniziale): `spacecraft_definition.json`.
   - Classe e involucro.
   - Massa, con le inerzie di una scatola uniforme.
   - Aree delle facce e area media proiettata; Cd e Cr predefiniti di STAR.
   - Pannelli solari sulle facce, batteria, potenze dichiarate dei componenti, radio.
   - Controllo d'assetto: ruote, star tracker, magnetorquer.
5. **Progetto finale:** stessa scelta con le quote delle orbite di END-001, il bilancio di END-004 (energia che la batteria deve dare in un'orbita) e il Δv di smaltimento di END-016. Elenca le differenze rispetto al progetto iniziale.

## Input

- **Requisiti di STAR:** il testo dei requisiti della missione; è l'ingresso principale.
- **Classe del CubeSat (`form_factor_u`, 1/3/6/12):** se l'utente la sceglie nel passo di risoluzione degli input, prevale su tutto. I valori predefiniti del registro non sostituiscono mai i requisiti.
- **Valori predefiniti del modulo:** `Input/input_component_selector.json`.
- **Solo per il progetto finale,** i prodotti della stessa run:
  - le orbite di END-001 (`satellite_NN.json`);
  - `power_budget_summary.json` di END-004;
  - `space_safety_summary.json` di END-016.

Fuori da STAR il selettore lavora sulla sola classe:

```bash
cd END006-ComponentSelector/star_component_selector
python -m star_selector select --form-factor 6           # testo, una sezione per sottosistema
python -m star_selector select --form-factor 1 --json    # JSON
python -m star_selector serve --open                     # interfaccia grafica su http://127.0.0.1:8765
```

## Collegamenti con gli altri moduli

A monte:

| Da | Cosa |
|---|---|
| STAR (requisiti, input approvati) | sottosistemi richiesti, prestazioni, eventuale classe scelta dall'utente |
| END-001 Constellation Optimizer (solo progetto finale) | quote delle orbite (GSD e swath degli strumenti) |
| END-004 Power Budget (solo progetto finale) | energia che la batteria deve dare in un'orbita (capacità della batteria) |
| END-016 Collision Avoidance (solo progetto finale) | Δv di smaltimento (propulsione) |

A valle, il progetto iniziale (`spacecraft_definition.json`):

| Modulo | Cosa usa di END-006 |
|---|---|
| END-001 Constellation Optimizer | massa, area di resistenza, coefficiente di resistenza |
| END-003 Attitude Propagation | massa, inerzie, area media, Cd, Cr, dimensioni, ruote, star tracker, magnetorquer |
| END-004 Power Budget | sottosistemi con le potenze dichiarate, batteria, pannelli solari e facce su cui sono montati |
| END-010 Reflectance Determination | classe del CubeSat (modello 3D per Unity) e area di riferimento |
| END-016 Collision Avoidance | massa, area e Cd, attraverso l'input di END-001 |
| END-018 Components Thermal Analysis | classe del CubeSat |
| STAR (scheda dei risultati END006) | progetto iniziale e finale, distinta dei componenti, budget |

## Output

In STAR i file vanno in `Output/RUN_<data>/modules_output/END-006/`. I file del progetto iniziale hanno il suffisso `_initial`, quelli del progetto finale nessun suffisso.

| File | Contenuto |
|---|---|
| `output_component_selector/spacecraft_definition.json` | il satellite del progetto iniziale per gli altri moduli (vedi "Come funziona") |
| `output_component_selector/spacecraft_definition_final.json` | il satellite del progetto finale con `changes_from_initial` |
| `output_component_selector/component_selector_results[_initial].json` | esito, parametri, note, sottosistemi scelti con i dati pubblicati, totali, budget, requisiti verificati |
| `output_component_selector/component_selector_requirements_mapping[_initial].json` | come i requisiti sono diventati parametri |
| `output_component_selector/component_selector_bom[_initial].csv` | distinta dei componenti scelti |
| `output_component_selector/component_selector_power_handoff[_initial].json` | potenze dichiarate dai fornitori dei componenti scelti |
| `results_component_selector/component_selector_data[_initial].js` | dati della scheda di STAR |
| `results_component_selector/component_selector_report[_initial].html` | report autonomo, la stessa interfaccia con i dati inclusi |

## Come si lancia

In STAR il modulo è il passo 0 del workflow (progetto iniziale) e l'ultimo (progetto finale). Test: `python run_all_tests.py END-006`, oppure dalla cartella `star_component_selector`:

```bash
python -m unittest discover -s tests -t .
```

I test che controllano i file dei datasheet vengono saltati quando la libreria PDF non c'è. I datasheet non sono nel repository, perché alcuni portano una nota di riservatezza.

## Limiti

- **Mancano:** bilancio energetico (lo fa END-004), compatibilità di tensioni e interfacce oltre a quelle verificate, layout di progetto (cablaggi, baricentro, zone di rispetto).
- **Pila dei componenti interni:** è una convenzione di visualizzazione dichiarata, non un dato dei fornitori.
- **Catalogo:** i valori sono trascritti dai documenti pubblici e non sono stati ricontrollati da una persona (`verified=false`).
- **Satellite per gli altri moduli:** scatola uniforme dell'involucro della classe con la massa dei componenti scelti; Cd e Cr sono valori predefiniti.

## Struttura della cartella

| Cartella | Contenuto |
|---|---|
| `star_component_selector/star_selector/` | il pacchetto: API, regole di missione, selettore, pila e ingombro, CLI, server dell'interfaccia |
| `star_component_selector/data/` | catalogo dei componenti |
| `star_component_selector/images/` | immagini dei componenti |
| `star_component_selector/schema/` | schema JSON del catalogo |
| `star_component_selector/tools/` | script che hanno aggiunto o corretto i dati del catalogo |
| `star_component_selector/tests/` | test del modulo |
| `star_component_selector/audit/` | verifica del catalogo |
