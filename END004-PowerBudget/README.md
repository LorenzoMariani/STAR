# END-004 — Power Budget

END-004 fa il bilancio energetico del satellite di una missione STAR: quanta energia generano i pannelli in un'orbita, quanta ne consumano i sottosistemi in ogni modo operativo e quanto si scarica la batteria.
Riproduce la logica del foglio Excel di riferimento usato in STAR per il dimensionamento del sottosistema di potenza (EPS).
In STAR i carichi vengono dai componenti scelti da END-006, i cicli di lavoro dalle operazioni calcolate da END-001 e la generazione dall'illuminazione dei pannelli nell'assetto di END-003.

## In breve

| | |
|---|---|
| Linguaggio | MATLAB (R2024b sul PC di STAR), solo MATLAB di base |
| Punto d'ingresso | `star_power_budget.m` (script), che chiama `STAR_END004_POWER_BUDGET(configFile, outputFolder)` |
| In STAR | `BackEnd/runners/end004_runner.py` (`run_end004`) |
| Durata in STAR | circa 30 s |

## Cosa fa

Per ognuno dei quattro modi operativi, cioè `idle`, `tx_uhf` (trasmissione UHF), `tx_sband` (trasmissione in banda S) e `payload`, calcola su un'orbita:

- **consumo al Sole e in eclisse:** per ogni sottosistema, potenza × frazione di tempo acceso al Sole e in eclisse × durata;
- **margine:** il 10% di default, su entrambi;
- **energia generata e risparmiata:** l'energia risparmiata è quella generata meno il consumo con il margine;
- **potenza di picco** del modo;
- **profondità di scarica della batteria (DoD):**
  - se la generazione copre il consumo al Sole, è l'energia dell'eclisse divisa per la capacità;
  - altrimenti è il deficit diviso per la capacità;
- **orbite di riposo** necessarie a ricaricare un deficit.

Sul giorno somma i modi secondo quante orbite ne fa ciascuno, e restituisce il **bilancio giornaliero**.

## Come funziona

1. **Orbita.** Periodo, durata al Sole e in eclisse e orbite al giorno.
   - Vengono dall'input, oppure dal raggio del CSV di assetto di END-003 con T = 2π √(a³/μ).
   - In STAR il periodo viene dall'orbita END-001 del satellite scelto da END-003 e l'eclisse dalla frazione d'ombra calcolata da END-003.
2. **Sottosistemi.** Ogni sottosistema ha una potenza e, per ogni modo, la frazione di tempo acceso al Sole e in eclisse.
3. **Bilancio di ogni modo** e poi del giorno (vedi sopra).
4. **Prodotti.** Tabelle CSV, JSON e XLSX, la tabella per la scheda di STAR e tre grafici.

## Input

### Il file di input

Il modello del file è `END004-PowerBudget/Input/input_power_budget.json`; in STAR il modulo legge `modules_output/END-004/end004_runtime_input.json`, preparato dal runner.

| Sezione | Contenuto |
|---|---|
| `paths` | CSV di assetto di END-003 e suo input (per ricavare il periodo dall'orbita) |
| `orbit` | orbite al giorno, periodo, minuti al Sole e in eclisse |
| `generation` | energia generata per orbita (anche per modo) o potenza dei pannelli al Sole |
| `battery` | capacità in Wh |
| `margin_fraction` | margine sui consumi (0,10) |
| `operations.mode_orbits_per_day` | orbite al giorno di ogni modo (senza indicazioni: 8 orbite di payload, il resto idle) |
| `subsystems` | per ogni sottosistema nome, potenza e frazioni di accensione per modo (al Sole / in eclisse) |

Due variabili d'ambiente sostituiscono i percorsi: `STAR_END004_INPUT_FILE` per l'input e `STAR_END004_OUTPUT_DIR` per l'output.

### Da dove vengono gli input in STAR

Il runner parte dal modello e lo completa con i prodotti della stessa run. Gli input approvati in STAR hanno la precedenza.

- **Orbita:** il periodo dall'orbita END-001 del satellite scelto da END-003 (quota media sopra il raggio equatoriale). L'eclisse è la frazione d'ombra di END-003 (KPI-14).
- **Carichi:** dal progetto iniziale di END-006.
  - Per i sottosistemi che il satellite ha, restano le voci del modello con la potenza dichiarata dal fornitore; i trasmettitori prendono la potenza di picco.
  - Le voci dei sottosistemi che il satellite non ha vengono tolte.
- **Batteria:** la capacità della batteria di END-006, oppure quella integrata nell'EPS.
- **Cicli di lavoro e orbite per modo:** dalle operazioni calcolate da END-001 (`operations_summary.json`).
  - Il payload è acceso quando l'area è nell'impronta.
  - I trasmettitori sono accesi durante i contatti con le stazioni, separando la parte al Sole da quella in eclisse.
  - Ricevitori, computer, ADCS e GNSS sono sempre accesi.
  - Orbite al giorno: quelle con acquisizioni sono di payload, quelle con contatti di trasmissione, le altre idle.
- **Generazione:** potenza di picco per pannello di END-006 × somma dei coseni medi delle facce con pannelli nell'assetto di END-003 × minuti al Sole.
  - Durante i contatti al Sole si usa l'illuminazione con il satellite puntato verso la stazione.
  - È a inizio vita, senza perdite termiche o di cablaggio.
- **Input di STAR:** `battery_capacity_Wh`, `power_generated_per_orbit_Wh`, `daily_mode_allocation`.

Ogni decisione è registrata con la sua origine nel report del runner in `end004_runtime_input.json`.

## Collegamenti con gli altri moduli

A monte:

| Da | Cosa |
|---|---|
| END-001 Constellation Optimizer | `operations_summary.json` (acquisizioni e contatti per orbita) |
| END-003 Attitude Propagation | orbita del satellite scelto (`selected_passes.json`), frazione di eclisse e illuminazione delle facce (`attitude_summary.json`) |
| END-006 Component Selector (progetto iniziale) | sottosistemi e potenze dichiarate, batteria, pannelli solari |

A valle:

| Modulo | Cosa usa di END-004 |
|---|---|
| END-006 Component Selector (progetto finale) | `power_budget_summary.json`: l'energia che la batteria deve dare in un'orbita, per dimensionarla |
| STAR (conformità ai requisiti, schede dei risultati END004) | bilancio giornaliero, profondità di scarica massima, generazione per orbita |

## Output

In STAR i file vanno in `Output/RUN_<data>/modules_output/END-004/`:

| File | Contenuto |
|---|---|
| `output_power_budget/power_budget_summary.json` | orbita, modi (consumi, generazione, energia risparmiata, picco, DoD, orbite di ricarica), analisi giornaliera |
| `output_power_budget/power_budget_summary.csv` | una riga per modo |
| `output_power_budget/power_budget_subsystems.csv` | una riga per modo e sottosistema: potenza, frazioni e minuti di accensione, consumi |
| `output_power_budget/power_budget_tables.xlsx`, `power_budget_sheet1.csv`, `power_budget_foglio1.csv` | le tabelle nel formato del foglio Excel di riferimento |
| `output_power_budget/power_budget_status.json` | esito del run |
| `results_power_budget/power_budget_tables.js` | dati della scheda di STAR |
| `results_power_budget/01_power_balance.png` | energia generata e consumata (con margine) per orbita, per modo |
| `results_power_budget/02_mode_consumption.png` | consumo per orbita di ogni modo, al Sole e in eclisse |
| `results_power_budget/03_orbital_dod.png` | profondità di scarica per orbita, per modo |
| `end004_runtime_input.json`, `matlab_stdout.txt`, `end004_process_result.json` | input effettivo, log di MATLAB, esito del run |

## Come si lancia

Da MATLAB:

```matlab
cd('END004-PowerBudget');
run('star_power_budget.m');
```

In STAR il modulo fa parte del workflow, dopo END-001 ed END-003. Test: `python run_all_tests.py END-004`, che lancia `tests/test_end004_power_budget.m`:
- bilancio di un sottosistema;
- modo in deficit, con DoD e orbite di ricarica;
- generazione dalla potenza dei pannelli;
- periodo dal CSV di END-003;
- ripartizione predefinita del giorno;
- prodotti scritti.

## Limiti

- **Granularità:** bilancio per orbita media di ogni modo, senza simulazione nel tempo dello stato di carica.
- **Generazione:** a inizio vita, senza perdite termiche, di cablaggio o di invecchiamento dei pannelli.
- **Cicli di lavoro da END-001:** sono un limite superiore, perché il payload acquisisce sempre quando può e le radio trasmettono per tutto il contatto.
- **Modi operativi:** fissi a quattro (`idle`, `tx_uhf`, `tx_sband`, `payload`).

## Struttura della cartella

| File | Contenuto |
|---|---|
| `star_power_budget.m` | script di avvio (percorsi da variabili d'ambiente o predefiniti) |
| `STAR_END004_POWER_BUDGET.m` | il calcolo, le tabelle e i grafici |
| `Input/input_power_budget.json` | il modello dell'input |
| `tests/` | test del modulo |
