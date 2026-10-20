# END-016 — Collision Avoidance

END-016 fa le verifiche di sicurezza spaziale della costellazione che END-001 ha progettato. Risponde a due domande:

1. **I satelliti si avvicinano tra loro?**
   - Per ogni coppia, lungo tutta la finestra delle effemeridi di END-001: istante e distanza di massimo avvicinamento, componenti della distanza, velocità relativa.
   - La probabilità di collisione Pc con l'incertezza di posizione dichiarata, e la Pc più alta che una qualunque incertezza potrebbe dare.
2. **Quanto dura l'orbita dopo la missione, e quanto costa smaltire il satellite?**
   - Vita orbitale passiva per resistenza atmosferica, per diversi livelli di attività solare.
   - Rispetto delle regole dei 5 anni (FCC) e dei 25 anni (IADC).
   - Δv della manovra che abbassa il perigeo per rientrare nei limiti.
   - Δv per anno necessario a mantenere la quota.

## In breve

| | |
|---|---|
| Linguaggio | MATLAB (R2024b sul PC di STAR) |
| Toolbox | Aerospace (atmosfera NRLMSISE-00 per la vita orbitale) |
| Punto d'ingresso | `lib/star_collision_main.m` (funzione `star_collision_main(cfg_json)`) |
| In STAR | `BackEnd/runners/end016_runner.py` (`run_end016`) |
| Durata in STAR | circa 20–30 s |

## Cosa fa

- **Avvicinamenti nella costellazione:**
  - minimi della distanza campionata di ogni coppia, raffinati con un'interpolazione cubica di Hermite delle effemeridi (posizioni con le loro derivate esatte), così istante e distanza non dipendono dal passo di 10 s;
  - per ogni evento sotto la distanza di screening: componenti radiale / lungo la traccia / fuori dal piano nella terna del primo satellite, velocità relativa, punto sotto il satellite.
- **Probabilità di collisione** su ogni evento:
  - Pc con il metodo di Chan (`lib/chan_pc.m`, NASA CA Handbook, Appendice N), con incertezze gaussiane indipendenti dei due satelliti, proiettate sul piano d'incontro (`lib/conjunction_plane_2d.m`);
  - il limite superiore del quadrato circoscritto (`lib/pc_upper_bound_square.m`);
  - Pc_max, la Pc più alta su ogni possibile covarianza.
- **Vita orbitale e smaltimento** (`lib/star_orbit_lifetime.m`) per ogni guscio orbitale (quota, inclinazione) e ogni livello di attività solare.
  - **Densità:** NRLMSISE-00 mediata sull'orbita e sull'ora locale.
  - **Decadimento:** equazioni di Gauss per la resistenza tangenziale, mediate sull'anomalia media, integrate in semiasse ed eccentricità fino al perigeo di rientro (120 km).
  - **Smaltimento:** una manovra alla quota operativa che abbassa il perigeo quanto basta a rispettare ogni regola.

## Come funziona

1. **Configurazione.** Legge il JSON di input; i percorsi relativi sono relativi alla cartella del JSON.
2. **Costellazione.** Legge da `star_input_dir` i `satellite_NN.json` e le effemeridi `satellite_NN_ephemeris.csv` di END-001, che devono avere la stessa griglia temporale.
3. **Avvicinamenti, Pc e KPI** per ogni coppia.
4. **Vita orbitale** di ogni guscio, con B = Cd · A / m.
5. **Prodotti:** matrice delle distanze minime, eventi, vita orbitale, riepilogo JSON con KPI, storia della distanza della coppia più vicina e curve di decadimento.

## Input

### Il file di input

| Campo | Contenuto |
|---|---|
| `star_input_dir`, `output_dir` | prodotti di END-001 e cartella dei risultati |
| `spacecraft` | `mass_kg`, `drag_area_m2`, `cd` |
| `hard_body_radius_m` | raggio combinato dei due oggetti |
| `position_sigma_rtn_m` | 1σ radiale, lungo la traccia e fuori dal piano di ogni satellite |
| `screening_km` | distanza sotto cui un avvicinamento è un evento (10) |
| `pc_threshold` | Pc sopra cui un evento è segnalato (1e-4) |
| `mission_lifetime_years` | vita operativa prima dello smaltimento |
| `disposal_rules_years` | regole di smaltimento, ad esempio `[5 25]` |
| `solar_f107` | livelli di attività solare F10.7, ad esempio `[70 140 220]` |
| `reentry_km` | quota di rientro (120) |

### Da dove vengono gli input in STAR

Il runner scrive `input_collision_avoidance.json`; ogni valore registra la sua origine.

- **Satellite** (massa, area, Cd): quelli usati da END-001 nella stessa run (`end001_runtime_input.json`, che a sua volta li prende dal progetto iniziale di END-006); altrimenti dai requisiti; altrimenti 100 kg, 1 m², 2,2.
- **Raggio combinato:** approvato dall'utente, oppure dai requisiti ("hard-body radius of …"). Altrimenti due volte il raggio di un disco con l'area di resistenza.
- **Incertezza di posizione:** approvata dall'utente, oppure l'ipotesi dichiarata [50, 200, 50] m, cioè effemeridi GNSS del proprietario predette circa un giorno avanti.
- **Vita della missione e regole di smaltimento:** dai requisiti ("mission lifetime of N years", "disposed of within N years"), più le regole FCC e IADC sempre presenti.
- **Attività solare secondo la modalità del run:** in test solo l'attività media (140); in full bassa, media e alta (70, 140, 220).
- **Prodotti a monte:** il runner copia in `star_input/` i `satellite_NN.json` e le effemeridi di END-001; senza effemeridi si ferma e dice di rilanciare END-001.

## Collegamenti con gli altri moduli

A monte:

| Da | Cosa |
|---|---|
| END-001 Constellation Optimizer | orbite (`satellite_NN.json`), effemeridi (`satellite_NN_ephemeris.csv`), massa, area e Cd della run (`end001_runtime_input.json`) |
| END-006 Component Selector (progetto iniziale) | massa, area e Cd, attraverso l'input di END-001 |

A valle:

| Modulo | Cosa usa di END-016 |
|---|---|
| END-006 Component Selector (progetto finale) | Δv di smaltimento (`space_safety_summary.json`), per la propulsione |
| STAR (conformità ai requisiti, scheda dei risultati END016) | separazione minima, eventi sotto lo screening, vita orbitale passiva, Δv di smaltimento per la regola dei 5 anni |

## Output

In STAR i file vanno in `Output/RUN_<data>/modules_output/END-016/`:

| File | Contenuto |
|---|---|
| `output_collision_avoidance/intra_pair_min_distance.csv` | matrice delle distanze minime tra le coppie |
| `output_collision_avoidance/intra_close_approaches.csv` | un evento per riga: coppia, TCA, distanza, componenti radiale / lungo la traccia / fuori dal piano, velocità relativa, latitudine, longitudine e quota, Pc, limite superiore, Pc_max |
| `output_collision_avoidance/disposal_lifetime.csv` | per guscio e livello solare: vita passiva, Δv di mantenimento per anno, Δv e perigeo dello smaltimento per ogni regola, rispetto della regola |
| `output_collision_avoidance/space_safety_summary.json` | configurazione, finestra, satelliti, matrice delle coppie, eventi, KPI, storia della distanza della coppia più vicina, curve di decadimento, note |
| `results_collision_avoidance/collision_run_info.json` | configurazione, provenienza dei valori, note, comando, esito |
| `input_collision_avoidance.json`, `end016_process_log.txt`, `end016_process_result.json` | input effettivo, log di MATLAB, esito del run |

**KPI di `space_safety_summary.json`:**
- satelliti e coppie;
- separazione minima, con la coppia e l'istante;
- eventi sotto lo screening e sotto 1 km, eventi al giorno;
- Pc e Pc_max massime, eventi sopra la soglia di Pc;
- vita passiva all'attività media, minima e massima;
- rispetto di ogni regola e Δv di smaltimento;
- Δv di mantenimento per anno;
- se serve mantenere l'orbita.

## Come si lancia

Da MATLAB:

```matlab
cd('END016-CollisionAvoidance');
addpath('lib')
star_collision_main('input_collision_avoidance.json')
```

In STAR il modulo fa parte del workflow, dopo END-001. Test: `python run_all_tests.py END-016`, che lancia `tests/test_end016_collision.m`:
- `chan_pc` su forme chiuse e sulle 53 congiunzioni di test di CARA (colonna Pc2D);
- piano d'incontro;
- costellazione sintetica di orbite circolari esatte (eventi, TCA, distanza, Pc confrontata con PcCircle di CARA);
- vita orbitale;
- input non validi.

## Limiti

- **Oggetti considerati:** solo i satelliti della costellazione (orbite END-001 con J2 secolare); gli altri oggetti spaziali non ci sono.
- **Pc:** usa un'incertezza di posizione dichiarata, non misurata. Pc_max dice quanto potrebbe valere al peggio.
- **Vita orbitale:** attività solare costante per livello, mentre il decadimento reale attraversa i cicli solari (i livelli basso e alto lo racchiudono). Orbita iniziale circolare.
- **Smaltimento:** una sola manovra di abbassamento del perigeo alla quota operativa.

## Struttura della cartella

| Cartella | Contenuto |
|---|---|
| `lib/` | il modulo STAR (`star_collision_main.m`, `star_orbit_lifetime.m`, `chan_pc.m`, `conjunction_plane_2d.m`, `pc_upper_bound_square.m`, `rot_eci2rtc.m`); strumenti di sviluppo per l'analisi di una congiunzione da CDM e TLE (`main.m`, covarianza da differenze di TLE, Monte Carlo, `testChan.m`) e i loro dati di esempio (`lib/data/`); SGP4 di Vallado (`lib/sgp4/`) |
| `CARA_Analysis_Tools/` | strumenti NASA CARA (probabilità di collisione, CDM di test con i valori di riferimento) |
| `tests/` | test del modulo |
