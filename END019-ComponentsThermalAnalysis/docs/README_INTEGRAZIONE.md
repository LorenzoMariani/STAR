# Modulo Termico STAR — Guida all'integrazione

Modulo di **analisi termica** per CubeSat, da inserire nella pipeline STAR come
un blocco a sé. Si comporta da **black box**: riceve dei file di input, esegue
l'analisi e produce dei file di output. Non è necessario conoscerne il contenuto
interno (modello, calibrazione, parametri fisici): serve solo rispettare il
**contratto di input/output** descritto qui.

---

## 1. Cosa fa (in breve)

Dati l'**orbita** e i **pass** di un satellite (prodotti dai moduli STAR a monte),
il modulo calcola l'evoluzione nel tempo delle **temperature** delle facce/pannelli
solari e dei nodi interni (parte centrale, batteria, payload SAR), e segnala gli
eventuali **superamenti dei limiti** operativi. Il tempo di analisi coincide con la
durata della propagazione fornita in input.

## 2. Come si richiama

### Modalità consigliata: eseguibile (nessuna licenza MATLAB)

Il modulo viene consegnato come **eseguibile** `star_thermal` (cartella
`blackbox_build/`). Gira con il **MATLAB Runtime** (gratuito, da installare una
volta sulla macchina — vedi `readme.txt` nella stessa cartella).

Il software esterno lo lancia come **processo**, passando il file di config:

```bash
star_thermal  input_termico.json
```

Esempi di invocazione da altri linguaggi:

```python
# Python
import subprocess
subprocess.run(["star_thermal", "input_termico.json"], check=True)
```
```bash
# shell / batch
star_thermal input_termico.json
```

Codici di uscita: **0** = ok, **≠0** = errore (messaggio su stderr).

### Modalità alternativa: dentro MATLAB

Se l'ambiente ha MATLAB, si può chiamare direttamente la funzione unica:

```matlab
star_thermal_main('input_termico.json')
% oppure con argomenti:
star_thermal_main('form_factor','6U','n_internal_nodes',3,'sar_power_W',200, ...
                  'star_input_dir','.../esempi_io_star','output_dir','.../out')
```

## 3. Input

### 3a. File di configurazione (`input_termico.json`)

Un unico file JSON con le scelte di missione/satellite:

```json
{
  "star_input_dir": "./esempi_io_star",   // cartella con gli output STAR (vedi 3b)
  "output_dir":     "./output_thermal",   // dove scrivere i risultati
  "form_factor":    "3U",                 // "1U" | "3U" | "6U" | "12U"
  "panels":         "both",               // "body" | "deployable" | "both"
  "n_internal_nodes": 3,                  // 1 | 2 | 3
  "sar_power_W":     200,                  // potenza del payload SAR [W] (se nodi=3)
  "sar_source":     "passes",             // "passes" | "duty"
  "sar_duty":       0.10                   // frazione di orbita ON (se source="duty")
}
```

| Campo | Valori | Significato |
|-------|--------|-------------|
| `form_factor` | 1U/3U/6U/12U | dimensione del satellite |
| `panels` | body/deployable/both | pannelli solari a corpo, dispiegabili, o entrambi |
| `n_internal_nodes` | 1/2/3 | 1=solo parte interna · 2=+batteria · 3=+payload SAR |
| `sar_power_W` | numero | potenza del SAR (usato solo con 3 nodi) |
| `sar_source` | passes/duty | SAR acceso nei pass di imaging **oppure** a ciclo fisso |
| `sar_duty` | 0–1 | quota di orbita con SAR acceso (solo se `duty`) |

Tutti i campi sono opzionali: quelli omessi usano un default sensato.

### 3b. File STAR richiesti (già prodotti dai moduli a monte)

Nella cartella indicata da `star_input_dir` il modulo si aspetta:

```
star_input_dir/
├─ output_constellation_optimizer/
│   └─ satellite_XX.json          (orbita: quota, inclinazione, RAAN, data, durata)
└─ output_attitude_propagation/
    ├─ selected_pass_summary.csv  (finestre dei pass di imaging = quando accendere il SAR)
    └─ output_attitude_propagation.csv  (posizione ECI + assetto, per la rifinitura del pass)
```

Il modulo elabora **tutti** i `satellite_XX.json` presenti.

## 4. Output (contratto)

Nella cartella `output_dir` vengono scritti:

```
output_dir/
├─ output_thermal_SAT-XX.csv        (serie temporale per satellite)
├─ thermal_summary_SAT-XX.json      (riassunto per satellite)
└─ thermal_constellation_output.csv (una riga per satellite — per il livello costellazione)
```

- **`output_thermal_SAT-XX.csv`**: colonne `timestamp_utc`, una colonna `T_<nodo>`
  per ogni faccia/pannello/nodo (in °C), `sar_on` (0/1), `eclipse` (0/1).
- **`thermal_summary_SAT-XX.json`**: configurazione usata, orbita, min/max/media di
  ogni nodo, blocco `solar_panels`, picchi (SAR/batteria/centrale) e `violations`
  (flag di superamento dei limiti).
- **`thermal_constellation_output.csv`**: sintesi per satellite (form factor, beta,
  n. pass, Tmax SAR/BAT/CTR, Tmax pannelli, flag limite batteria).

Il software a valle legge questi file esattamente come legge gli output degli
altri moduli STAR.

## 5. Come si genera l'eseguibile (una volta)

A carico di chi impacchetta il modulo (serve MATLAB + MATLAB Compiler):

```matlab
build_blackbox        % crea blackbox_build/star_thermal(.exe)
```

Poi si consegnano all'integratore **solo**: la cartella `blackbox_build/`, il file
`input_termico.json` di esempio e questo README. Il codice sorgente non è incluso.

## 6. Riepilogo del flusso

```
[moduli STAR a monte] → satellite_XX.json + pass + attitude
                                   │
                                   ▼
                 star_thermal  input_termico.json     (eseguibile)
                                   │
                                   ▼
        output_thermal/  →  CSV temperature + JSON riassunto  →  [software STAR a valle]
```
