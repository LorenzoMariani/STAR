# END-010 — Reflectance Determination

END-010 simula la curva di luce del satellite visto da un osservatorio a terra: quanta luce solare riflette verso l'osservatore durante un passaggio notturno, con il satellite illuminato e l'osservatore al buio.
Calcola la geometria del passaggio (satellite, Sole, osservatore) in MATLAB e fa il rendering del modello 3D del CubeSat in Unity, che restituisce il flusso fotometrico istante per istante.
In STAR stima anche la magnitudine apparente del satellite, cioè quanto sarà visibile dagli osservatori ottici.

## In breve

| | |
|---|---|
| Linguaggio | MATLAB (geometria, KPI, grafici) + Unity (rendering della curva di luce) |
| Punto d'ingresso | `star_reflectance_determination.m` (funzione `STAR_END010_REFLECTANCE_DETERMINATION(file_input, path_output)`) |
| Unity | `lib/BuildCubeSat/UnityLightCurveInversion.exe`, compilato dal progetto `unity_project/` (in alternativa `lib/BuildAqua/`) |
| In STAR | `BackEnd/runners/end010_runner.py` (`run_end010`); l'input è preparato da `build_end010_config` e `end010_cubesat_options` in `BackEnd/runners/star_runner_io.py` |
| Durata in STAR | circa 1 minuto |

## Cosa fa

- **Geometria del passaggio, istante per istante:** posizione ECI del satellite, Sole (effemeridi JPL DE440), osservatorio, elevazione, distanza, angolo di fase e visibilità.
- **Rendering Unity:** il modello 3D del CubeSat della classe scelta, orientato come l'assetto del passaggio e illuminato dal Sole, ripreso da una camera ortografica nella posizione dell'osservatore. Il flusso integrato di ogni immagine forma la curva di luce.
- **Magnitudine apparente:** stimata con il modello di una sfera diffondente, m = −26,74 − 2,5 log₁₀(albedo · R² · Φ(fase) / d²). R è il raggio equivalente dell'area di riferimento, Φ la funzione di fase di Lambert, d la distanza dall'osservatore. Il picco è confrontato con la magnitudine limite del sito.
- **KPI e grafici del passaggio:** durata, elevazione massima, distanza, angolo di fase, flusso medio e di picco, ampiezza e variabilità della curva, magnitudine di picco, magnitudine limite.

## Come funziona

1. **Configurazione.** Legge il JSON di input; carica le costanti di nutazione (`lib/sgp4/nut80.dat`) e le effemeridi planetarie (`lib/data/DE440.mat`).
2. **Osservatorio.** Prende latitudine, longitudine e quota esplicite dalla configurazione; altrimenti cerca il nome in `lib/data/stations.json`.
3. **Orbita e assetto.**
   - Con `flags.useInputCsv` legge posizione ECI e quaternione dal CSV del passaggio (in STAR quello di END-003) e calcola Sole e osservatore sugli stessi istanti (`lib/propagation_from_reci.m`).
   - Altrimenti propaga un TLE con SGP4 (`lib/propagation.m`).
4. **CSV per Unity.** Scrive `csvUnity.csv`: tempi, posizioni di satellite, osservatore e Sole, elevazione, distanze e assetto nella terna di Unity.
5. **Unity** (`lib/runUnity.m`): rendering di ogni istante, salvataggio delle immagini e del flusso in `flux.csv`.
6. **KPI e serie temporali** per la scheda di STAR, **grafici** della geometria.

## Input

### Il file di input

Il modello del file è `Input/input_reflectance_determination.json`; in STAR il modulo legge `modules_output/END-010/end010_runtime_input.json`, preparato dal runner.

| Sezione | Contenuto |
|---|---|
| `paths` | eseguibile Unity, CSV del passaggio, EOP, TLE, stazioni, dati di nutazione, DE440 |
| `simulation` | osservatorio (nome o coordinate esplicite), maschera di elevazione, passo, durata e inizio (se si propaga) |
| `sat` | area di riferimento, albedo, rotazione dal modello Unity alla terna body |
| `flags` | `useInputCsv` (orbita e assetto da CSV) e uso di effemeridi esterne |
| `unityOpts` | immagini da produrre e salvare, risoluzione e dimensione della camera, proiezione ortografica, spazio lineare, modello radiometrico, file della curva di luce e del log, scala della scena, classe del CubeSat |

Variabili d'ambiente: `STAR_END010_INPUT_FILE`, `STAR_END010_OUTPUT_DIR`, `STAR_END010_MAIN_FOLDER`.

### Da dove vengono gli input in STAR

- **Passaggio:** il passaggio notturno che END-001 ha scelto e su cui END-003 ha calcolato l'assetto, cioè `output_attitude_propagation_lightcurve_ECI.csv` e `selected_passes.json`.
  - L'osservatorio è quello usato per scegliere il passaggio (Matera di default).
  - Senza passaggio notturno si usa il passaggio di imaging di END-003 e il suo sito.
  - Il CSV letto è sempre quello in ECI vero: il file per Unreal ha gli assi di un'altra convenzione.
- **Satellite:** dal progetto iniziale di END-006.
  - La classe sceglie il modello 3D NASA-style del CubeSat per Unity.
  - La dimensione della camera è metà della diagonale dell'involucro × 1,1, così il modello resta nell'immagine con qualunque assetto.
  - L'area di riferimento è l'area media proiettata.

  Senza END-006 si usa la classe predefinita.
- **File di dati:** EOP, TLE di riferimento, stazioni, nutazione e DE440 dalla cartella `lib/`.

## Collegamenti con gli altri moduli

A monte:

| Da | Cosa |
|---|---|
| END-001 Constellation Optimizer | la scelta del passaggio notturno visibile dall'osservatorio (`pass_selection.json`), attraverso END-003 |
| END-003 Attitude Propagation | orbita e assetto del passaggio notturno (`output_attitude_propagation_lightcurve_ECI.csv`), osservatorio (`selected_passes.json`) |
| END-006 Component Selector (progetto iniziale) | classe del CubeSat (modello 3D, camera) e area media proiettata |

A valle:

| Modulo | Cosa usa di END-010 |
|---|---|
| STAR (conformità ai requisiti, scheda dei risultati END010) | magnitudine apparente di picco e osservatorio (`reflectance_summary.json`), serie temporali, immagini |

## Output

In STAR i file vanno in `Output/RUN_<data>/modules_output/END-010/`:

| File | Contenuto |
|---|---|
| `output_reflectance_determination/flux.csv` | la curva di luce: flusso strumentale di ogni istante |
| `output_reflectance_determination/unityLog.log` | log di Unity |
| `results_reflectance_determination/csvUnity.csv` | la geometria del passaggio passata a Unity |
| `results_reflectance_determination/reflectance_summary.json` | catalogo dei KPI (KPI-01…16): simulazione completata, campioni e immagini, durata, elevazione massima, frazione visibile, distanza media e minima, angolo di fase medio, flusso medio e di picco, ampiezza e variabilità della curva, magnitudine di picco stimata, magnitudine limite del sito |
| `results_reflectance_determination/reflectance_timeseries.json` | serie temporali di geometria e fotometria per la scheda di STAR |
| `results_reflectance_determination/Frames/*.png` | le immagini del rendering |
| `results_reflectance_determination/Plots/*.png` | angolo di fase (terna Unity ed ECI), traccia a terra, angoli della camera |
| `end010_runtime_input.json`, `star_reflectance_determination_runtime.m`, `matlab_stdout.txt`, `end010_process_result.json` | input effettivo, copia dello script che STAR esegue, log di MATLAB, esito del run |

## Come si lancia

Da MATLAB, con i file di dati e la build di Unity al loro posto:

```matlab
cd('END010-ReflectanceDetermination');
run('star_reflectance_determination.m');
```

In STAR il modulo fa parte del workflow, dopo END-003. Il test della pipeline (`python run_all_tests.py SMOKE`) lo esegue con gli altri moduli.

## Limiti

- **File non nel repository:** `lib/data/DE440.mat` (oltre 50 MB) e le build di Unity (`lib/BuildCubeSat/`, `lib/BuildAqua/`) vanno copiati a mano. Senza, END-010 si ferma e lo dice.
- **Magnitudine:** è una stima analitica (sfera diffondente con albedo 0,2 di default), non viene dal flusso di Unity, che è strumentale e non calibrato. La magnitudine limite del sito è fissa a 7.
- **Modello 3D:** è quello NASA-style della classe, non il satellite con i componenti scelti.
- **Scene Unity:** alcuni percorsi assoluti di un'altra macchina restano nelle scene del progetto (`unity_project/Assets/Scenes/*.unity`); vanno cambiati dall'editor di Unity.
- **Sistema operativo:** l'esecuzione è solo per Windows (eseguibile Unity, percorsi con `\`).

## Struttura della cartella

| Cartella | Contenuto |
|---|---|
| `star_reflectance_determination.m` | il modulo |
| `lib/` | geometria (propagazione, Sole, osservatore), interfaccia con Unity, dati (EOP, TLE, stazioni), SGP4 di Vallado, script di sviluppo |
| `unity_project/` | sorgenti del progetto Unity che fa il rendering |
| `_old/` | versioni precedenti (fuori da git) |
