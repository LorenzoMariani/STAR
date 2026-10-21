# Modulo termico STAR — 3U con SAR (copia adattata di TAURUS)

Adattamento del tool termico TAURUS (Lumped Capacitance Method **calibrato**) per
funzionare come **modulo della pipeline STAR**: legge gli output degli altri
moduli (orbite + pass + assetto), gira l'analisi termica di un CubeSat **3U** e
scrive i risultati in un formato che il programma a livello di costellazione può
rileggere. **Il codice TAURUS originale non è toccato**: questa è una copia a sé.

## Catena I/O (come si integra)

```
constellation_optimizer  ──>  satellite_XX.json      (orbita, data, durata)
attitude_propagation     ──>  selected_pass_summary  (finestre pass imaging)
                              output_attitude_prop.   (pos ECI + quaternioni)
                                        │
                                        ▼
                          [ QUESTO MODULO: termica ]
                                        │
                                        ▼
              output_thermal/  ──>  CSV temperature + JSON riassunto
                                    thermal_constellation_output.csv
```

## File

| File | Ruolo |
|------|-------|
| `run_star_thermal.m`   | **script maestro**: cicla i satelliti, legge input, gira termica, scrive output, grafico |
| `star_config.m`        | tutti i parametri + percorsi I/O (modifica qui) |
| `star_read_orbit.m`    | legge `satellite_XX.json` → orbita, data, durata |
| `star_read_passes.m`   | legge `selected_pass_summary.csv` → finestre pass imaging (SAR ON) |
| `star_read_attitude.m` | legge `output_attitude_propagation.csv` → pos ECI + quaternioni |
| `star_sun_eci.m`, `star_beta.m` | Sole in ECI e angolo beta da orbita+data |
| `star_build_model.m`   | costruisce i nodi (6 facce + 2 pannelli dispiegabili + CTR/BAT/SAR) e la rete |
| `star_thermal_run.m`   | propagazione 48h, assetto nadir analitico, SAR acceso nei pass |
| `star_pass_detail.m`   | rifinitura del pass con l'**assetto reale** (quaternioni), warm-start |
| `star_write_output.m`  | scrive CSV/JSON per satellite + riga per il CSV di costellazione |
| `esempi_io_star/`      | copia degli input STAR di esempio (gira out-of-the-box) |

## Come si esegue

In MATLAB, dalla cartella `STAR_Thermal`:

```matlab
run_star_thermal
```

Legge i satelliti in `esempi_io_star/output_constellation_optimizer/`, per ognuno
propaga la termica sulle 48h e scrive in `output_thermal/`.

## Scelte di input (tutte in `star_config.m`, in cima)

| Parametro | Valori | Cosa fa |
|---|---|---|
| `cfg.sat.form`      | `'1U' '3U' '6U' '12U'` | form factor → geometria/aree |
| `cfg.panels.mode`   | `'body' 'deployable' 'both'` | pannelli solari body-mounted e/o dispiegabili |
| `cfg.nodes.config`  | `1 2 3` | nodi interni: 1=solo centrale · 2=+batteria · 3=+payload SAR |
| `cfg.sar.Ppeak`     | [W] | potenza SAR (solo se nodi=3) |
| `cfg.sar.source`    | `'passes' 'duty'` | SAR ON nei pass STAR oppure a duty cycle |
| `cfg.sar.duty`      | 0–1 | frazione di orbita ON (se `source='duty'`) |

Il **tempo di analisi si adatta da solo** alla durata `sim_hours` fornita dalla
propagazione orbitale (satellite_XX.json): non è mai fissato a mano.

## Modello

- **6 facce** body-mounted: le 4 laterali sono **pannelli solari** con ottiche
  **dalla calibrazione SIMBA** (α=0.95, ε=0.83); le facce di testa ±Z a parte.
- **Pannelli solari dispiegabili** (0 o 2, sun-tracking, nodi a doppia faccia),
  con fronte alle stesse ottiche calibrate.
- **Nodi interni** scelti da `cfg.nodes.config` (CTR sempre; BAT e SAR opzionali).
- Conduttanze e capacità dalla **calibrazione SIMBA**.

Le **temperature dei pannelli solari** (laterali + dispiegabili) sono nell'output
CSV e nel riassunto JSON (blocco `solar_panels`), e nel grafico (curve grigie).

## Output (formato definito, stile STAR)

In `output_thermal/`:
- `output_thermal_SAT-XX.csv` — timestamp UTC, temperatura di ogni nodo, `sar_on`, `eclipse`.
- `thermal_summary_SAT-XX.json` — orbita, beta, periodo, min/max/media per nodo,
  picchi (SAR orbita e SAR con assetto reale), **flag superamento limiti**
  (batteria/SAR/bus).
- `thermal_constellation_output.csv` — una riga per satellite (stile
  `constellation_optimizer_output.csv`), pronta per il livello di costellazione.

## Risultati sull'esempio (SAT-01, validati)

- Orbita: 1200 km, i=100.4°, β=55.5°, periodo 109 min (26 orbite/48h).
- Pass imaging: ~1.94 h dall'inizio, 12.8 min → **SAR sale a ~108 °C**, poi si
  raffredda; a regime i nodi oscillano ~35–40 °C.
- **Verifica assetto**: picco SAR con nadir analitico (108.2 °C) vs assetto reale
  dai quaternioni (108.7 °C) → coincidono (<1 °C): la propagazione nadir è
  confermata dai dati STAR.

## Note / assunzioni

- Quaternione interpretato come **body→ECI** con ordine `[w x y z]`; se STAR usa
  la convenzione opposta, si inverte in `star_pass_detail.m` (funzione locale
  `quat2rotm_wxyz`).
- Beta calcolato all'inizio missione (deriva trascurabile su 48h).
- Nessuna dipendenza da toolbox (jsondecode/readtable sono base MATLAB).
