# END-018 — Components Thermal Analysis (CubeSat)

Modello termico a parametri concentrati (Lumped Capacitance Method) di un
CubeSat 1U/3U/6U/12U, **calibrato su temperature in orbita** di un 3U
(WildtrackCube / SIMBA): 6 facce (le 4 laterali pannelli solari), pannelli
dispiegabili opzionali, nodi interni corpo centrale (CTR), batteria (BAT) e
payload SAR. Carichi: Sole diretto, albedo, IR terrestre, eclisse cilindrica;
integrazione Backward-Euler con radiazione linearizzata. Solo MATLAB base.

## Struttura

| Cartella | Contenuto |
|---|---|
| `src/` | sorgenti MATLAB (modalità STAR e analisi diretta) |
| `examples/` | input STAR di esempio (`esempi_io_star/`, prodotti END-001/END-003 di un run del 2026-09-22) e configurazioni (`input_termico.json`, `input_test.json` = caso di test del report); gli output generati (`output_*`) non sono in git |
| `blackbox_build/` | `star_thermal.exe`, la versione consegnata compilata (MATLAB Runtime R2026a); non più usata da STAR |
| `docs/` | README dell'autore (`README_software_termico.md`, `README_STAR.md`), `README_INTEGRAZIONE.md`, `demo_analisi.png`; il report `.docx` resta fuori da git |
| `_old/` | copia della consegna originale (solo locale, fuori da git) |

## Come lo usa STAR

`BackEnd/runners/end018_runner.py` (planner: solo missioni CubeSat con analisi
termica, a valle di END-001 ed END-003):

1. scrive `input_termico.json` dai requisiti (classe, pannelli, SAR e potenza);
2. copia in `star_input/` le orbite di END-001 (`satellite_XX.json`), i pass
   di END-003 (`selected_pass_summary.csv`) e l'assetto del pass
   (`output_attitude_propagation_ECI.csv`, quaternione body→ECI);
3. lancia `matlab -batch "addpath('<src>'); star_thermal_main('<input_termico.json>')"`
   (`MATLAB_EXECUTABLE`, `STAR_END018_MATLAB_SOURCE` per cambiare comando e
   cartella; con `STAR_END018_EXECUTABLE` usa invece la black box);
4. gli output (`output_thermal_SAT-XX.csv`, `thermal_summary_SAT-XX.json`,
   `thermal_constellation_output.csv`) vanno nella scheda END018 del frontend v4.

## Uso diretto in MATLAB

```matlab
addpath('src')
star_thermal_main('examples/input_termico.json')   % come STAR, output in examples/output_thermal
run_star_thermal                                    % idem con i default di star_config + grafici
run_analisi                                         % analisi diretta da config_analisi.m (senza file STAR)
```

## Correzioni del 2026-10-15 (rispetto alla consegna)

Verificate sugli input di esempio (script di verifica nella sessione, numeri
sotto); la black box in `blackbox_build/` riproduce bit per bit la consegna,
non queste correzioni.

1. **Convenzione del quaternione** (`star_read_attitude`, `star_process`,
   `star_config`): il modulo leggeva `output_attitude_propagation.csv`, che
   END-003 scrive per Unreal con il quaternione coniugato (ECI→body), come
   body→ECI: nel pass +Z body era a 58° dal nadir e le facce fino a 46 K
   diverse. Ora legge `output_attitude_propagation_ECI.csv` (body→ECI) o, se
   manca, il file Unreal coniugato: +Z a 0,01° dal nadir.
2. **Fase e periodo dell'orbita** (`star_orbit_phase`, `star_thermal_run`):
   ogni satellite partiva a mezzogiorno orbitale (fase 0) con raggio
   6371 km + quota e moto kepleriano, quindi le eclissi non erano allineate ai
   pass reali (flag di eclisse sbagliato nel 5-59% dei passi). Ora: fase reale
   a t = 0 da RAAN, inclinazione, anomalia e Sole; raggio 6378,137 km + quota e
   termini J2 come END-001; flag di eclisse diverso dall'orbita J2 nello
   0,1-0,5% dei passi (~1,5 passi da 10 s per ingresso/uscita).
3. **Condizione iniziale** (`star_thermal_run`): tutti i nodi partivano da
   0 °C a t = 0, così minimi e primo pass risentivano della partenza a freddo
   (BAT/CTR minimo 0,0 °C, a regime 36,6/27,8 °C). Ora si parte dal regime
   periodico (fino a `cfg.sim.spinup_orbits` = 100 orbite prima di t = 0,
   convergenza 0,01 K; 8-11 orbite sugli esempi); il numero di orbite è in
   `thermal_summary` (`thermal.spinup_orbits`).

Effetto sull'esempio (3U, pannelli dispiegabili, SAR 200 W nei pass, SAT-01
che fa l'immagine): SAR max 110,5 → 122,6 °C, BAT max 47,4 → 54,5 °C, CTR max
75,9 → 85,6 °C. Caso di test del report (`input_test.json`, SAR al 30%):
SAT-01 217,8 / 173,1 / 103,3 / 193,3 °C (SAR / CTR / BAT / pannelli),
entro ±3 °C dai valori del report (217 / 172 / 103 / 192).

## Limiti

Orbita circolare; beta costante nella singola analisi (deriva su 48 h
trascurabile per SSO); eclisse cilindrica; assetto nadir analitico fuori dal
pass, reale (END-003) nel pass. La scala tra form factor è un'euristica e il
nodo SAR usa conduttanze di progetto: strumento per analisi preliminari.
Limiti operativi nel riassunto: BAT 25 °C, CTR 60 °C, SAR 85 °C.
