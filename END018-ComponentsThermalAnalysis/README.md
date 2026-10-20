# END-018 — Components Thermal Analysis

END-018 calcola le temperature di un CubeSat (1U, 3U, 6U, 12U) lungo tutta la missione di ogni satellite della costellazione.
Il modello è a parametri concentrati (Lumped Capacitance Method), calibrato sulle temperature in orbita di un 3U (WildtrackCube / SIMBA).
In STAR dice se batteria, corpo centrale e payload restano nei loro limiti operativi, con le orbite di END-001 e i passaggi e l'assetto di END-003.

## In breve

| | |
|---|---|
| Linguaggio | MATLAB (R2024b sul PC di STAR), solo MATLAB di base |
| Punto d'ingresso | `src/star_thermal_main.m` (funzione `star_thermal_main(cfg_json)`) |
| In STAR | `BackEnd/runners/end018_runner.py` (`run_end018`) |
| Durata in STAR | da pochi secondi a circa 40 s (5–20 satelliti per 48 h) |

## Cosa fa

- **Nodi del modello:**
  - le 6 facce, di cui le 4 laterali sono pannelli solari;
  - i pannelli dispiegabili (opzionali, orientati verso il Sole);
  - i nodi interni: corpo centrale (CTR), batteria (BAT) e, per una missione SAR, il payload SAR.
- **Carichi termici:** Sole diretto, albedo, infrarosso terrestre, eclisse cilindrica, potenze interne costanti e potenza del SAR quando è acceso.
- **Integrazione:** Backward-Euler con radiazione linearizzata, stabile con passi di 10 s.
- **Per ogni satellite:** temperature di tutti i nodi su tutta la finestra, minimi, massimi e medie, temperature dei pannelli solari, picchi, confronto con i limiti operativi (BAT 25 °C, CTR 60 °C, SAR 85 °C).

## Come funziona

1. **Configurazione** (`src/star_config.m`): classe, pannelli, numero di nodi interni, potenza e accensione del SAR.
   - Geometria e masse sono scalate dalla classe.
   - Le ottiche dei pannelli e le conduttanze vengono dalla calibrazione SIMBA.
2. **Modello** (`src/star_build_model.m`): nodi, capacità termiche, ottiche e rete conduttiva tra facce, corpo centrale, batteria, SAR e cerniere dei pannelli.
3. **Orbita** (`src/star_orbit_phase.m`, `src/star_beta.m`): orbita circolare con raggio e moto J2 come END-001, posizione reale rispetto al Sole a t = 0, angolo β dalla data.
4. **Regime periodico** (`src/star_thermal_run.m`): prima di t = 0 si ripete l'orbita finché le temperature non cambiano più di 0,01 K, al massimo per 100 orbite. Poi si integra tutta la finestra con assetto nadir analitico.
5. **SAR acceso:**
   - con `sar_source = passes`, nei passaggi di imaging di END-003 (`src/star_read_passes.m`);
   - con `sar_source = duty`, per una frazione di ogni orbita.
6. **Dettaglio del passaggio** (`src/star_pass_detail.m`): sul passaggio di imaging ripete il calcolo con l'**assetto reale** di END-003, partendo dalle temperature dell'orbita.
7. **Prodotti** (`src/star_write_output.m`): un CSV e un JSON per satellite, più un CSV della costellazione.

## Input

### Il file di input

`star_thermal_main` legge un JSON. I percorsi relativi sono relativi alla cartella del JSON.

| Campo | Contenuto |
|---|---|
| `star_input_dir` | cartella con i prodotti di END-001 e END-003 (`output_constellation_optimizer/satellite_XX.json`, `output_attitude_propagation/selected_pass_summary.csv` e il CSV dell'assetto) |
| `output_dir` | cartella dei risultati |
| `form_factor` | `1U`, `3U`, `6U`, `12U` |
| `panels` | `body`, `deployable` o `both` |
| `n_internal_nodes` | 1 (CTR), 2 (+ BAT), 3 (+ SAR) |
| `sar_power_W`, `sar_source`, `sar_duty` | potenza del SAR, accensione nei passaggi o a ciclo di lavoro, frazione d'orbita |

Esempi in `examples/`: `input_termico.json` (SAR nei passaggi) e `input_test.json` (il caso di test del report: SAR al 30%), con i prodotti END-001 / END-003 di un run del 2026-09-22 in `examples/esempi_io_star/`.

### Da dove vengono gli input in STAR

Il runner scrive `input_termico.json`. Ogni valore registra la sua origine. A parità di parametro vale questa priorità:

1. classe del progetto END-006 o approvata dall'utente;
2. requisiti;
3. valori predefiniti del registro.

- **Dominio:** solo CubeSat da 1U a 12U. Una missione con massa oltre 24 kg, o che non nomina un CubeSat, viene saltata.
- **Classe:** quella del progetto iniziale di END-006 (`spacecraft_definition.json`). Una classe scritta nei requisiti è solo riportata; una classe approvata dall'utente prevale.
- **SAR:** se i requisiti nominano un SAR, ci sono 3 nodi interni e il SAR si accende nei passaggi di END-003; la potenza viene dai requisiti, se c'è. Senza SAR ci sono 2 nodi (corpo centrale e batteria).
- **Pannelli:** "deployable" o "body-mounted" letti nei requisiti; altrimenti il valore predefinito del modello.
- **Prodotti a monte:** il runner copia in `star_input/` le orbite di END-001 e i passaggi e l'assetto di END-003.
  - Come assetto preferisce `output_attitude_propagation_ECI.csv` (body→ECI).
  - Se manca usa il file per Unreal, coniugando il quaternione.
- **Motore:**
  - di default i sorgenti in MATLAB (`matlab -batch`);
  - `MATLAB_EXECUTABLE` e `STAR_END018_MATLAB_SOURCE` cambiano comando e cartella;
  - con `STAR_END018_EXECUTABLE` gira invece la black box compilata.

## Collegamenti con gli altri moduli

A monte:

| Da | Cosa |
|---|---|
| END-001 Constellation Optimizer | orbite (`satellite_XX.json`) |
| END-003 Attitude Propagation | passaggi di imaging (`selected_pass_summary.csv`) e assetto del passaggio (`output_attitude_propagation_ECI.csv`) |
| END-006 Component Selector (progetto iniziale) | classe del CubeSat |

A valle:

| Modulo | Cosa usa di END-018 |
|---|---|
| STAR (conformità ai requisiti, scheda dei risultati END018) | temperature massime e minime di batteria e corpo centrale (`thermal_summary_SAT-XX.json`), serie temporali |

## Output

In STAR i file vanno in `Output/RUN_<data>/modules_output/END-018/`:

| File | Contenuto |
|---|---|
| `output_components_thermal_analysis/output_thermal_SAT-XX.csv` | temperature di tutti i nodi ogni 60 s, SAR acceso, eclisse |
| `output_components_thermal_analysis/thermal_summary_SAT-XX.json` | configurazione, orbita (β, periodo, passaggi, orbite di regime), minimi / massimi / medie di ogni nodo e dei pannelli, picchi (SAR anche nel passaggio con l'assetto reale), limiti e superamenti |
| `output_components_thermal_analysis/thermal_constellation_output.csv` | una riga per satellite: classe, nodi, β, passaggi, massimi di SAR, BAT, CTR e pannelli, batteria oltre il limite |
| `results_components_thermal_analysis/thermal_run_info.json` | configurazione, provenienza dei valori, note, dominio, esito |
| `input_termico.json`, `end018_process_log.txt`, `end018_process_result.json` | input effettivo, log, esito del run |

## Come si lancia

Da MATLAB:

```matlab
cd('END018-ComponentsThermalAnalysis');
addpath('src')
star_thermal_main('examples/input_termico.json')   % come STAR, output in examples/output_thermal
run_star_thermal                                    % idem con i valori di star_config, più i grafici
run_analisi                                         % analisi diretta da config_analisi.m, senza file STAR
```

In STAR il modulo fa parte del workflow, dopo END-001 ed END-003. Test: `python run_all_tests.py END-018`, che lancia `tests/test_end018_thermal.m`:
- regime al buio e al Sole costante (bilancio energetico esatto);
- frazione d'eclisse;
- ciclo di lavoro del SAR;
- rete conduttiva;
- Sole e angolo β;
- orbita;
- convenzione dell'assetto;
- caso di test del report;
- SAR solo nei passaggi;
- opzioni dei nodi;
- input non validi.

## Correzioni del 2026-10-15 (rispetto alla consegna)

La black box in `blackbox_build/` riproduce la consegna, non queste correzioni.

1. **Convenzione del quaternione** (`star_read_attitude`, `star_process`, `star_config`).
   - Il modulo leggeva come body→ECI `output_attitude_propagation.csv`, che END-003 scrive per Unreal con il quaternione coniugato (ECI→body). Nel passaggio +Z body era a 58° dal nadir e le facce differivano fino a 46 K.
   - Ora legge `output_attitude_propagation_ECI.csv` oppure il file per Unreal coniugato: +Z è a 0,01° dal nadir.
2. **Fase e periodo dell'orbita** (`star_orbit_phase`, `star_thermal_run`).
   - Ogni satellite partiva a mezzogiorno orbitale, con raggio 6371 km + quota e moto kepleriano. Le eclissi non erano allineate ai passaggi reali: il flag di eclisse era sbagliato nel 5–59% dei passi.
   - Ora fase reale a t = 0 da RAAN, inclinazione, anomalia e Sole; raggio 6378,137 km + quota e termini J2 come END-001.
3. **Condizione iniziale** (`star_thermal_run`).
   - Tutti i nodi partivano da 0 °C, così minimi e primo passaggio risentivano della partenza a freddo.
   - Ora si parte dal regime periodico: 8–11 orbite sugli esempi, numero registrato in `thermal.spinup_orbits`.

**Effetto sull'esempio** (3U, pannelli dispiegabili, SAR 200 W nei passaggi, SAT-01 che fa l'immagine): SAR massimo da 110,5 a 122,6 °C, BAT da 47,4 a 54,5 °C, CTR da 75,9 a 85,6 °C.

**Caso di test del report:** SAT-01 a 217,8 / 173,1 / 103,3 / 193,3 °C (SAR / CTR / BAT / pannelli), entro ±3 °C dai valori del report (217 / 172 / 103 / 192).

## Limiti

- **Orbita e Sole:** orbita circolare; β costante nella singola analisi (deriva su 48 h trascurabile per le SSO); eclisse cilindrica.
- **Assetto:** nadir analitico fuori dal passaggio, reale (END-003) nel passaggio.
- **Scala e calibrazione:** la scala tra le classi è un'euristica e il nodo SAR usa conduttanze di progetto. È uno strumento per analisi preliminari.
- **Limiti operativi** fissi: BAT 25 °C, CTR 60 °C, SAR 85 °C.

## Struttura della cartella

| Cartella | Contenuto |
|---|---|
| `src/` | sorgenti MATLAB (modalità STAR e analisi diretta) |
| `examples/` | input di esempio e prodotti END-001 / END-003 di un run; gli output generati (`output_*`) non sono in git |
| `tests/` | test del modulo |
| `blackbox_build/` | `star_thermal.exe`, la versione consegnata compilata (MATLAB Runtime R2026a); STAR non la usa più |
| `docs/` | README dell'autore (`README_software_termico.md`, `README_STAR.md`), `README_INTEGRAZIONE.md`, `demo_analisi.png`; il report `.docx` è fuori da git |
| `_old/` | copia della consegna originale (solo locale, fuori da git) |
