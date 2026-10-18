# Modelli 3D di CubeSat per il modulo Reflectance Determination (END-010)

**In uso (2026-10-16)**: solo i modelli della sezione 4, `cds_nasa_style_1U_2U_3U_6U_12U/` (scelta dell'utente). Sono gli unici nel repository STAR; END-010 li usa nella build Unity `lib/BuildCubeSat` (vedi `END010-ReflectanceDetermination/unity_project/README_STAR.md`) con la classe scelta da END-006. Le sezioni 1-3 restano solo su questa macchina (`.gitignore`).

Cartella raccolta il 2026-10-16. Quattro gruppi di modelli: due scaricati da fonti pubbliche (NASA, Pumpkin) e due generati da me dalle quote della CubeSat Design Specification Rev. 14.1 (scatole semplici e modelli dettagliati in stile NASA). **Non esiste (o non ho trovato) un modello 3D gratuito e scaricabile di un 6U e di un 12U da un fornitore o da un'agenzia**: per queste due classi ci sono la scatola CDS generata (sezione 1) e i modelli dettagliati in stile NASA generati per 1U, 2U, 3U, 6U e 12U (sezione 4, i piu' completi).

Formati: OBJ (+ MTL) si importa direttamente in Unity; GLB richiede un pacchetto (per esempio glTFast); STEP serve per CAD. Verificare in Unity l'orientamento degli assi: OBJ e glTF sono destrorsi, Unity e' sinistrorso e l'importatore puo' specchiare l'asse X.

**I modelli non contengono proprieta' ottiche** (albedo, BRDF): solo colori di materiale (NASA) o nessun colore (Pumpkin, scatole CDS). Le proprieta' vanno assegnate nel modulo (per esempio `sat.albedo` in `input_reflectance_determination.json`).

## 1. `cds_envelope_boxes/` (generati, esatti rispetto alla CDS)

Scatola piena con l'inviluppo CDS Rev. 14.1, **una faccia = un gruppo e un materiale** (`face_pX`, `face_mX`, `face_pY`, `face_mY`, `face_pZ`, `face_mZ`: p = +, m = -) per assegnare materiali diversi (celle solari, struttura, ...) faccia per faccia. Unita' **metri**, origine al **centro** dell'inviluppo, asse **Z lungo l'asse lungo**.

| Modello | Inviluppo (X x Y x Z, mm) |
|---|---|
| `CDS_1U_envelope` | 100 x 100 x 113.5 |
| `CDS_3U_envelope` | 100 x 100 x 340.5 |
| `CDS_6U_envelope` | 100 x 226.3 x 366.0 |
| `CDS_12U_envelope` | 226.3 x 226.3 x 366.0 |

Sono volutamente senza guide, pannelli incassati, antenne o pannelli dispiegati: nessun dettaglio non pubblicato e' stato inventato. Sono le stesse quote usate dal selettore END-006.

## 2. `nasa/` (scaricati da NASA 3D Resources, GitHub `nasa/NASA-3D-Resources`)

Per ogni modello: `.glb` originale, `.obj` + `material.mtl` convertiti, `_preview.png`. Fonte: https://github.com/nasa/NASA-3D-Resources (cartella `3D Models/`). Il sito dichiara le risorse gratuite per il download e l'uso; il repository non riporta un file di licenza: per pubblicazioni citare NASA come fonte e non suggerire un patrocinio.

| Modello | Contenuto | Estensione complessiva nelle unita' del modello (X x Y x Z) | Asse lungo |
|---|---|---|---|
| `NASA_1U_generic` | 1U generico con celle solari su 4 facce e due fili d'antenna | 5.19 x 2.60 x 2.20 (corpo circa 2.08 x 2.58 x 2.05) | Y |
| `NASA_2U_generic` | **2U generico NASA**, stesso stile del 1U, con due moduli di pannelli per faccia e due fili d'antenna | 5.39 x 5.00 x 2.21 | Y |
| `NASA_ICECube_3U` | CubeSat ICECube (3U) con pannelli solari dispiegati e strumento | 2.34 x 8.29 x 2.12 | Y |
| `NASA_MiRaTa_3U` | CubeSat MiRaTA (3U) con pannelli solari dispiegati | 2.46 x 8.40 x 2.09 | Y |

**Attenzione alla scala**: i file dichiarano le unita' "metri" ma il corpo di un 1U misura circa 2 unita': la scala va corretta nell'importazione (per un 1U con lato di 100 mm il fattore e' circa 0.048). Le proporzioni del "1U generico" (altezza circa 1.25 volte la larghezza) non coincidono con la CDS (1.135): e' un modello illustrativo, non dimensionalmente esatto. Sono modelli a bassa risoluzione con materiali di colore (celle blu, struttura grigia, lamina d'argento, ...): utili per la forma e per assegnare materiali per parte, non come riferimento dimensionale.

## 3. `pumpkin_cubesat_kit/` (scaricati da cubesatkit.com)

Telai "chassis solid" del CubeSat Kit di Pumpkin (solo struttura, senza pannelli, schede o antenne). Per ogni modello: `.STEP` originale (AP214, mm), `.glb` e `.obj` ottenuti da me dal STEP (metri, tassellazione 0.3 mm, un'unica mesh senza colori), foto del fornitore. Fonte: https://www.cubesatkit.com/content/design.html (file `csk_*_chassis_solid_revd.zip`).

| Modello | Estensione del modello (mm) | Asse lungo |
|---|---|---|
| `CSK_1U_Chassis_Solid_RevD` | 100 x 100 x 116 | Z |
| `CSK_1.5U_Chassis_Solid_RevD` | 100 x 100 x 172.8 | Z |
| `CSK_2U_Chassis_Solid_RevD` | 100 x 229.6 x 100 | Y |
| `CSK_3U_Chassis_Solid_RevD` | 100 x 100 x 343 | Z |

**Termini d'uso Pumpkin** (riassunto della pagina del fornitore, da rileggere prima di ogni uso): i modelli sono © Pumpkin, Inc.; possono essere usati liberamente in qualunque CAD e per creare illustrazioni 2D e 3D, che **devono citare Pumpkin, Inc. e/o www.cubesatkit.com**; non possono essere esportati per prototipare, produrre o chiedere preventivi per gli oggetti reali (eccezione: modelli di prototipazione rapida per progetti o finanziamenti); non vanno rimossi i marchi presenti nei modelli; chi li esporta deve dichiarare la fonte e includere il copyright e i termini. Le immagini renderizzate per il modulo END-010 sono illustrazioni 3D: citare Pumpkin.

Le quote di questi telai superano di qualche millimetro l'inviluppo CDS nominale (per esempio 116 mm contro 113.5 mm per un 1U): sono l'estensione totale del modello CAD, con le parti sporgenti.

## 4. `cds_nasa_style_1U_2U_3U_6U_12U/` (generati: modelli dettagliati in stile NASA)

Modelli costruiti sullo stesso stile dei modelli NASA 1U/2U (guide chiare, pannelli solari modulari con celle e bordi di cella arancioni, fasce grigie di separazione), con le quote CDS esatte. Per ciascuno: `.obj` + `.mtl` (normali per vertice, spigoli netti e guide arrotondate), `.glb` e `_preview.png`. Il programma `generate_cds_models.py` (solo `numpy`; `trimesh` per il GLB) li rigenera; le quote e le convenzioni sono in cima al file. Unita' **metri**, origine al **centro**, asse **Z lungo l'asse lungo**. Sostituisce la versione precedente con guide e pannelli semplici.

| Modello | Inviluppo (X x Y x Z, mm) | Moduli lungo Z | Oggetti | Triangoli | Celle |
|---|---|---|---|---|---|
| `CDS_1U_nasa_style` | 100.0 x 100.0 x 113.5 | 1 | 25 | 1200 | 10 |
| `CDS_2U_nasa_style` | 100.0 x 100.0 x 227.0 | 2 | 37 | 1840 | 18 |
| `CDS_3U_nasa_style` | 100.0 x 100.0 x 340.5 | 3 | 49 | 2480 | 26 |
| `CDS_6U_nasa_style` | 226.3 x 100.0 x 366.0 | 3 | 67 | 3632 | 41 |
| `CDS_12U_nasa_style` | 226.3 x 226.3 x 366.0 | 3 | 85 | 4912 | 58 |

**Materiali** (`usemtl`): `rail`, `structure` (corpo, fasce, piastra del tappo -Z), `panel_substrate`, `solar_cell`, `cell_border`. **Oggetti** (`o`): `rail_pX_pY`, `rail_pX_mY`, `rail_mX_pY`, `rail_mX_mY`; `structure_body`; `structure_band_<faccia>`; `structure_endplate_mZ`; per ogni modulo di pannello `solar_panel_<faccia>_z<n>[_x<n>]_substrate`, `..._cell_borders`, `..._cells`; `solar_panel_pZ_*` sul tappo +Z. Facce: `pX`, `mX`, `pY`, `mY` (lunghe), `pZ`/`mZ` (tappi). Cosi' e' facile assegnare una proprieta' ottica diversa a celle, bordi, substrato, struttura e guide.

**Dalla CDS Rev. 14.1** (disegni dell'Appendice B per 1U, 2U, 3U, 6U e 12U e sezione 2.2): inviluppo; 4 guide sugli spigoli per tutta la lunghezza, sezione 8.5 x 8.5 mm (larghezza minima 2.2.5) con spigoli di raggio 1 mm (2.2.7); le facce con protrusioni ammesse finiscono a 0.5 mm dalle facce +/-Z (il minimo dell'intervallo 0.5-7.0 mm del disegno); nessuna protrusione oltre il piano delle guide (il limite e' 6.5 mm, 2.2.3).

**Convenzioni mie, non date dalla CDS** (modificabili in cima al generatore):
- pannelli su 5 facce (4 lunghe e tappo +Z); il tappo -Z, la faccia inserita per prima nel dispenser, e' una piastra di struttura;
- pannelli modulari: 1, 2, 3, 3, 3 moduli lungo Z per 1U, 2U, 3U, 6U, 12U; 2 moduli affiancati sulle facce larghe 226.3 mm; fasce di struttura di 6 mm tra i moduli lungo Z, 3 mm in larghezza, 4 mm alle estremita';
- spessore del pannello 2.5 mm (dichiarato per il pannello ISIS 1U/3U del catalogo): substrato 2.2 mm, bordo di cella 0.1 mm, cella 0.2 mm; la superficie delle celle e' a filo del piano delle guide;
- celle 40 x 80 mm con angoli smussati di 3 mm, lato lungo lungo Z, spazio di 1 mm, margine di 1 mm, griglia centrata, bordo che sporge 0.4 mm: **la dimensione della cella e' quella tipica di una cella a tripla giunzione da circa 30 cm2, ma non e' scritta nei datasheet del catalogo** (che dicono solo "30 cm2 di area efficace" e "AzurSpace 3G30A"); il numero di celle e' quello che entra nel pannello e non coincide con i fornitori (2 per un pannello 1U come EnduroSat; per il 3U 6 per faccia contro 7);
- corpo pieno dietro i pannelli; nessuna antenna (nemmeno stivata), sensore, connettore, vite, RBF, linguetta o elettronica: i modelli NASA le mostrano, questi no.

**Orientamento in END-010 (2026-10-18).** Gli assi di questi modelli non sono gli assi corpo di STAR (END-006 / END-003: +Z = asse del payload, al nadir; pannelli su +-X e +-Y; il 6U di END-006 e' 100 x 226.3 mm, questo 226.3 x 100 mm). Il player Unity li disegna senza rotazione, e finora l'asse lungo finiva lungo l'asse corpo Y con una faccia lunga con celle al nadir. La correzione e' sull'input di Unity, non nel player: END-010 invia il quaternione d'assetto composto con una rotazione fissa per classe (`sat.unityModelToBody_q`, `END010_MODEL_TO_BODY_Q` in `BackEnd/runners/star_runner_io.py`) che porta l'asse lungo sull'asse corpo Z e il tappo -Z di struttura sulla faccia del payload (+Z, nadir); per il 6U anche X modello (226.3 mm) su Y corpo.

Controlli eseguiti (nel generatore, a ogni esecuzione): inviluppo esatto e centrato sull'origine; ogni oggetto e' una superficie chiusa con volume positivo; le normali dichiarate sono coerenti con l'avvolgimento dei triangoli. Le anteprime sono renderizzate da me con un semplice z-buffer: non sono un riferimento di aspetto.

## Non scaricato

- STEP di ISISpace, EnduroSat, GomSpace: non ho trovato un link di download pubblico e diretto (i datasheet ISIS dicono che i file STEP sono sul sito del fornitore; vanno cercati o chiesti li'). Un sito terzo elenca file STEP ISIS: non l'ho usato perche' non verificabile come fonte.
- 6U e 12U reali: nessuna fonte gratuita trovata (vedi scatole CDS).
- Modelli commerciali a pagamento (RenderHub e simili): esclusi.
