# Software Termico CubeSat (LCM calibrato) — sorgente aperto

Strumento di **analisi termica** per CubeSat basato su un modello a parametri
concentrati (Lumped Capacitance Method) **calibrato su misure in orbita**
(WildtrackCube / SIMBA). Tutto il codice è in chiaro (nessuna black box).

Si usa in **due modalità**, con lo stesso motore calibrato:

## A) Analisi diretta (senza file STAR)
Imposti satellite e orbita a mano e ottieni temperature + grafici.

1. Apri **`config_analisi.m`** e imposta: taglia (`form`), pannelli (`panels`),
   nodi interni (`nnodes`), potenza/duty del SAR, e l'**orbita** (quota,
   inclinazione, RAAN, data, n. orbite, assetto). Il beta è calcolato da
   orbita+data, oppure lo fissi tu.
2. Lancia:
   ```matlab
   run_analisi
   ```
3. Ottieni: riepilogo a schermo (min/max/media per nodo), due figure
   (tutte le misure; esterne vs interne) e il file **`risultati_analisi.csv`**.

## B) Interfaccia con i moduli STAR
Legge gli output STAR (orbite/pass/assetto) e scrive i risultati nel formato STAR.

```matlab
run_star_thermal
```
Legge `esempi_io_star/` e scrive in `output_thermal/` (CSV + JSON per satellite +
CSV di costellazione). Vedi `README_STAR.md` per i dettagli dell'I/O STAR.

## File

| File | Ruolo |
|------|-------|
| **config_analisi.m** | scelte per l'analisi diretta (satellite + orbita) |
| **run_analisi.m** | script principale analisi diretta (riepilogo + grafici + CSV) |
| **lcm_solve.m** | solutore per l'analisi diretta (orbita da config) |
| run_star_thermal.m | script per la modalità STAR (grafici inclusi) |
| star_process.m | nucleo della modalità STAR (lettura → calcolo → scrittura) |
| star_config.m | parametri e scelte (motore condiviso) |
| star_build_model.m | costruzione nodi, capacità, ottiche, rete conduttiva |
| star_thermal_run.m / star_pass_detail.m | propagazione STAR (nadir + rifinitura pass) |
| star_read_orbit/passes/attitude.m | lettura dei file STAR |
| star_beta.m / star_sun_eci.m | angolo beta e posizione del Sole |
| star_write_output.m | scrittura output STAR |
| esempi_io_star/ | file STAR di esempio |

## Requisiti
Solo **MATLAB base** (nessuna toolbox aggiuntiva).

## Modello (sintesi)
- 6 facce (le 4 laterali sono pannelli solari, ottiche calibrate) + eventuali
  pannelli dispiegabili + nodi interni (centrale, batteria, payload SAR).
- Carichi ambientali: solare diretto, albedo, IR terrestre, eclisse.
- Parametri (conduttanze, capacità, ottiche) dalla calibrazione; masse e scambi
  con le facce scalano con il form factor.
- Integrazione Backward-Euler con radiazione linearizzata (stabile).

## Limiti (da tenere a mente)
- Orbita circolare; beta costante nella singola analisi; eclisse cilindrica.
- Assetto nadir o sun (analisi diretta); per la modalità STAR l'assetto reale
  dei quaternioni è usato solo nella finestra del pass.
- La scala tra form factor è un'euristica; il nodo SAR usa conduttanze di
  progetto (non calibrate su test). Strumento per analisi **preliminari**.
