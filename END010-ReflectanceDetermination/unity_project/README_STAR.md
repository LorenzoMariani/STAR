# Progetto Unity di END-010 (copia STAR di unityLightCurveInversion)

Copia ridotta del progetto Unity `unityLightCurveInversion` (repository Sapienza-S5Lab, cartella locale `Desktop/git_repository/unityLightCurveInversion`), presa il 2026-10-16 dalla **copia di lavoro**: ultimo commit `a05cab0` del 2026-03-09 ("New shader for normal maps") piu' le modifiche non committate fino al 2026-06-11 (tra cui il fattore di scala della scena 100 -> 10000000). Editor Unity **6000.0.77f1**.

Copiati: `Assets/Scripts`, `Assets/Shaders`, `Assets/Materials`, `Assets/Input`, `Assets/Plugins`, `Assets/Settings` (URP), `Assets/Scenes/baseScene.unity`, `Packages`, `ProjectSettings`. Non copiati: gli altri modelli e scene del progetto originale (Aqua, Sentinel, PROBA, Coral, ... 345 MB) e `Library` (1.9 GB, Unity la rigenera; con `Temp`, `Logs`, `obj`, `UserSettings` e' esclusa da git).

## Il CubeSat della missione

- `Assets/Models/StarCubeSats/`: i cinque modelli CDS "stile NASA" (1U, 2U, 3U, 6U, 12U) di `Input/cubesat_3d_models/cds_nasa_style_1U_2U_3U_6U_12U` (OBJ + MTL, metri, origine al centro, Z lungo l'asse lungo).
- `Assets/Editor/StarCubeSatBuild.cs`: apre `baseScene.unity`, toglie il modello del satellite (il suo asset non e' nella copia), mette sotto `ObjectWrapper` i cinque modelli come `CubeSat_1U` ... `CubeSat_12U`, assegna i materiali del progetto, salva `Assets/Scenes/StarCubeSat.unity` e compila il player Windows in `../lib/BuildCubeSat/`.
- Materiali (convenzione dichiarata, nessun dato ottico pubblicato per queste parti): `rail` e `structure` -> `Aluminium` (con la LUT BRDF dell'alluminio), `solar_cell` -> `SolarArray`, `panel_substrate` e `cell_border` -> `Black`.
- `Assets/Scripts/StarCubeSatSelector.cs`: con `-cubesatClass <1|2|3|6|12>` tiene il modello della classe ed elimina gli altri (i piani di taglio e la somma per faccette leggono anche i figli inattivi); senza l'argomento 6U.

## Modifiche agli script originali (solo in questa copia)

- `-sceneScale <float>`: il fattore che divide le posizioni del csv (`LightCurveGenerator.SceneScale`, predefinito 10000000 come nella copia di lavoro). STAR passa **100** perche' le sue posizioni sono in km: con 10000000 un satellite a 1000 km sarebbe a 0.0001 unita' dalla camera, dentro un CubeSat di 0.3 unita'.
- `-camSize`, `-exposure`, `-focalLength` letti come numeri decimali (prima interi: un `camSize` di 0.27 m diventava 0).
- Nella scena CubeSat `DrawAxis`, `EnableView`, `SaveEXR`, `UseFacetSum`, `UseRadiometricModel` sono spenti: `runUnity.m` passa un flag booleano solo quando e' vero, quindi da STAR si possono solo accendere.

## Ricompilare

```
"C:\Program Files\Unity\Hub\Editor\6000.0.77f1\Editor\Unity.exe" -batchmode -quit -projectPath <questa cartella> -executeMethod StarCubeSatBuild.BuildAll -logFile build.log
```

La prima volta Unity importa il progetto (qualche minuto). Il player (circa 99 MB) va in `END010-ReflectanceDetermination/lib/BuildCubeSat/`, fuori da git come `lib/BuildAqua/`.

## In STAR

Il runner (`BackEnd/runners/star_runner_io.py`, `end010_cubesat_options`) usa `lib/BuildCubeSat` se c'e' (altrimenti la vecchia `lib/BuildAqua`), legge la classe scelta da END-006 nella stessa run (`component_selector_results.json`; senza END-006: 6U) e passa `cubesatClass`, `sceneScale` = 100 e `camSize` = meta' della diagonale dell'ingombro CDS della classe x 1.1. END-006 e' una dipendenza facoltativa di END-010 nel registro: quando ci sono entrambi END-010 gira dopo END-006. La magnitudine stimata (KPI-15, modello a sfera) usa ancora `sat.A_ref` e `sat.albedo` di `input_reflectance_determination.json`.
