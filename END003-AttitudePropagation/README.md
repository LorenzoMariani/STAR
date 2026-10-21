# END-003 — Attitude Propagation

END-003 calcola l'assetto del satellite durante i passaggi che END-001 ha scelto: il passaggio di imaging sull'area di interesse e il passaggio notturno visibile dall'osservatorio.
L'orbita non viene propagata qui: arriva dalle effemeridi di END-001, quindi i satelliti sono esattamente quelli progettati.
L'assetto segue una legge di guida (nadir o puntamento del sito), chiusa da un controllo PD con ruote di reazione e magnetotorquer, oppure evolve libero sotto le coppie di disturbo.
Il modulo esporta l'assetto dei passaggi per END-004, END-007, END-010 ed END-018, insieme ai KPI e ai grafici.

## In breve

| | |
|---|---|
| Linguaggio | MATLAB (R2024b sul PC di STAR) |
| Toolbox | Aerospace, Mapping (dall'analisi delle dipendenze di MATLAB) |
| Punto d'ingresso | `star_attitude_propagation_star.m` (funzione `star_attitude_propagation_star(configFile, outputFolder)`) |
| In STAR | `BackEnd/runners/end003_runner.py` (`run_end003`); il modello dell'input è preparato da `build_end003_config` in `BackEnd/runners/star_runner_io.py` |
| Durata in STAR | circa 1 minuto |

## Cosa fa

- **Assetto su una griglia di 1 s** per il satellite del passaggio di imaging e, se diverso, per quello del passaggio notturno.
- **Tre modalità** (`sat.attitude_mode`):
  - `nadir`: +Z verso il nadir, +X lungo la traccia; la velocità angolare è quella della terna orbitale (moto orbitale più rotazione del piano dell'orbita);
  - `follow_site`: +Z verso il sito finché è sopra la soglia di elevazione, nadir altrimenti, con manovre limitate a `max_slew_rate_deg_s`;
  - `dynamics`: equazioni di Eulero e cinematica del quaternione con le coppie di disturbo, moto libero.
- **Controllo d'assetto** in `nadir` e `follow_site`: l'assetto di guida è il riferimento di un controllo PD con una ruota di reazione per asse. Valgono i limiti di coppia e momento delle ruote, l'errore di conoscenza dell'assetto e lo scarico del momento con i magnetotorquer. L'assetto esportato è quello controllato, con il suo errore di puntamento.
- **Coppie di disturbo:** gradiente di gravità, pressione di radiazione solare (con l'ombra della Terra) e resistenza atmosferica, sul braccio tra centro di pressione e centro di massa.
- **KPI e grafici** sull'intera finestra delle effemeridi.

## Come funziona

1. **Orbita da END-001.** Legge `satellite_NN_ephemeris.csv` (posizione e velocità ECI ogni 10 s). Gli stati tra due righe vengono da un'interpolazione cubica di Hermite con la velocità tabulata, con errore sotto il metro.
2. **Passaggi da END-001.** Legge `pass_selection.json`: il passaggio di imaging di giorno sull'area e il primo passaggio notturno visibile dall'osservatorio.
3. **Assetto.** Calcola l'assetto di guida della modalità scelta.
   - Con il controllo attivo, integra il controllo in anello chiuso a passi di 1 s solo sui passaggi, con un margine di 300 s.
   - Nel resto della finestra segue il momento delle ruote a passi più lunghi.
   - Il dipolo dei magnetotorquer è quello di END-006. Se manca, è dimensionato con la regola di END-006: scaricare una ruota piena in un'orbita.
4. **Prodotti dei passaggi.** Scrive gli assetti dei passaggi a passo fisso (10 s) e un AEM CCSDS (passo 1 s) per ogni passaggio, con le figure che lo descrivono (`end003_aem_figures.m`).
5. **Serie dell'intera finestra.** Ogni 60 s calcola coppie, eclisse, momento angolare e contatti con le stazioni, poi i grafici, i dati della scheda e il catalogo dei KPI.

Convenzioni: quaternioni di Hamilton body→ECI (v_eci = R(q) v_body), salvati con lo scalare in fondo; velocità angolare nella terna body; ECI con il GMST IAU-82, come END-001.

## Input

### Il file di input

Il modulo legge un JSON passato come argomento: in STAR è `modules_output/END-003/end003_runtime_input.json`, preparato dal runner a partire da `Input/input_attitude_propagator.json`.

| Sezione | Contenuto |
|---|---|
| `sim_start_date`, `sim_hours` | inizio e durata (limitata alla finestra delle effemeridi di END-001) |
| `sat` | modalità d'assetto, assetto e velocità iniziali, massa, inerzie, area di riferimento, Cr, Cd, centro di pressione `r_cp`, limite di manovra, `control` (frequenza e smorzamento del PD, limiti delle ruote, errore di conoscenza, dipolo dei magnetotorquer, scarico del momento) |
| `env.flags` | coppie attive: gradiente di gravità, pressione solare, resistenza |
| `target` | soglia di elevazione del sito e vincolo di Sole |
| `pass_selection` | passo dei prodotti e dell'AEM, osservatorio e soglie del passaggio notturno |
| riferimenti a END-001 | effemeridi, `pass_selection.json`, stazioni di terra (aggiunti dal runner) |

### Da dove vengono gli input in STAR

- **Orbite e passaggi:** dalle effemeridi e da `pass_selection.json` di END-001. Senza questi file END-003 non parte e lo dice.
- **Satellite:** massa, inerzie, area media proiettata, Cd e Cr vengono dal progetto iniziale di END-006 (`spacecraft_definition.json`). Il centro di pressione è al 20% di ogni lato dell'involucro, la tolleranza sul baricentro della CubeSat Design Specification. Un input `spacecraft_physical_properties` di STAR ha la precedenza.
- **Controllo d'assetto:** dal progetto di END-006.
  - Ruote di reazione: momento e coppia massima.
  - Star tracker: accuratezza, convertita a 1σ; senza star tracker si usa l'accuratezza di puntamento dell'unità ADCS.
  - Magnetotorquer: dipolo per asse.

  Senza dati restano i valori del modello.
- **Altri input di STAR:** `attitude_mode`, `initial_attitude_state`, `environmental_flags`, `simulation_duration_hours`.
- **Stazioni di terra:** quelle di END-001 (`end001_runtime_input.json`), per i contatti mostrati nella scheda.

Ogni decisione è registrata con la sua origine in `star_runtime.end003_inputs`.

## Collegamenti con gli altri moduli

A monte:

| Da | Cosa |
|---|---|
| END-001 Constellation Optimizer | effemeridi `satellite_NN_ephemeris.csv`, `pass_selection.json`, stazioni di terra |
| END-006 Component Selector (progetto iniziale) | massa, inerzie, aree, Cd, Cr, dimensioni, ruote, star tracker, magnetotorquer |

A valle:

| Modulo | Cosa usa di END-003 |
|---|---|
| END-004 Power Budget | l'orbita del satellite scelto (`selected_passes.json`) e la frazione di eclisse (KPI-14 di `attitude_summary.json`) |
| END-007 Synthetic Data Generation | `output_attitude_propagation.csv` (quaternione ECI→body per Unreal) e `selected_passes.json` |
| END-010 Reflectance Determination | il passaggio notturno (`output_attitude_propagation_lightcurve_ECI.csv`, `selected_passes.json`) |
| END-018 Components Thermal Analysis | `selected_pass_summary.csv` e l'assetto del passaggio (`output_attitude_propagation_ECI.csv`, altrimenti il file per Unreal) |
| STAR (conformità ai requisiti, scheda dei risultati END003) | i KPI di `attitude_summary.json`, i dati di `attitude_propagation_plots_data.js` |

## Output

In STAR i file vanno in `Output/RUN_<data>/modules_output/END-003/`:

| File | Contenuto |
|---|---|
| `output_attitude_propagation/output_attitude_propagation.csv` | passaggio di imaging ogni 10 s: tempo UTC, posizione ECI, quaternione **ECI→body** (il coniugato, per Unreal / END-007), angolo dal nadir |
| `results_attitude_propagator/output_attitude_propagation_ECI.csv` | lo stesso passaggio con il quaternione **body→ECI** |
| `results_attitude_propagator/output_attitude_propagation_Unity.csv` | lo stesso passaggio nella terna di Unity |
| `output_attitude_propagation/output_attitude_propagation_lightcurve_ECI.csv` | il passaggio notturno per la curva di luce (END-010) |
| `output_attitude_propagation/selected_passes.json`, `selected_pass_summary.csv` | i due passaggi: satellite, inizio, fine, picco di elevazione, sito o osservatorio, Sole |
| `output_attitude_propagation/pass_candidates.csv` | tutti i passaggi candidati sull'area, con quello scelto segnato |
| `output_attitude_propagation/AEM_END003_<satellite>_<passaggio>_<data>.xml` | assetto CCSDS AEM di ogni passaggio (quaternione e velocità angolare ogni 1 s, J2000) |
| `results_attitude_propagator/attitude_summary.json` | catalogo dei KPI (vedi sotto) |
| `results_attitude_propagator/*.png` | grafici del modulo e figure degli AEM (vedi sotto) |
| `results_attitude_propagator/attitude_propagation_plots_data.js` / `.json` | dati della scheda interattiva di STAR |

**KPI di `attitude_summary.json`:**
- passaggio trovato e soglie rispettate;
- deriva della norma del quaternione;
- elevazione di picco e durata;
- scarto dal nadir e dal sito;
- coppie medie;
- frazione di eclisse (KPI-14);
- momento angolare;
- satelliti esaminati;
- passaggio notturno trovato;
- velocità angolari;
- errore di puntamento, momento e coppia delle ruote, tempo ai limiti, dipolo dei magnetotorquer.

**Grafici:**
- **Grafici del modulo:** telemetria, puntamento, momento angolare, traccia a terra, orbita 3D, controllo d'assetto.
- **Figure dell'AEM di ogni passaggio:** vista inerziale, vista lungo il momento angolare, momento rispetto all'orbita, quaternione, angoli di Eulero e velocità angolare.

Alcuni grafici esistono solo nella modalità `dynamics`.

## Come si lancia

Da MATLAB, con un file di input che punti alle effemeridi e alla selezione dei passaggi di END-001:

```matlab
cd('END003-AttitudePropagation');
star_attitude_propagation_star('end003_runtime_input.json', 'output_folder');
```

In STAR il modulo fa parte del workflow, dopo END-001. Test: `python run_all_tests.py END-003`, che lancia `tests/test_end003_attitude.m`:
- coppie di disturbo su casi analitici;
- velocità angolare della terna nadir;
- controllo PD entro i limiti delle ruote;
- scarico del momento con i magnetotorquer.

## Limiti

- **Coppie di disturbo:** satellite trattato come scatola uniforme. Le coppie di pressione solare e resistenza usano un braccio di riferimento conservativo, non la geometria reale.
- **Campo magnetico:** dipolo inclinato IGRF-13, solo per lo scarico del momento.
- **Anello chiuso:** a 1 s solo sui passaggi, più 300 s di margine. Fuori dai passaggi si segue solo il momento delle ruote.
- **Modalità `dynamics`:** moto libero, senza controllo.

## Struttura della cartella

| File | Contenuto |
|---|---|
| `star_attitude_propagation_star.m` | il modello (orbita da END-001, assetto, controllo, prodotti, KPI, grafici) |
| `end003_disturbance_torques.m` | coppie di gradiente di gravità, pressione solare e resistenza, e il loro caso peggiore |
| `end003_aem_figures.m` | figure e stato rotazionale da un AEM |
| `tests/` | test del modulo |
