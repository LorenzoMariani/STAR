# STAR Interface Definition Notes — END-010 Reflectance Determination

> Updated 2026-10-21. The formal IDD is STAR/IDD/STAR_IDD_END-010.docx; the module README is END010-ReflectanceDetermination/README.md.

## Functional role

END-010 simulates the light curve of the satellite seen from a ground observatory during a night pass: the sunlight it reflects towards the observer while the satellite is sunlit and the observer is in the dark. MATLAB (star_reflectance_determination.m) computes the geometry of every instant (ECI position of the satellite, Sun from the JPL DE440 ephemerides, observatory, elevation, range, phase angle, visibility) and Unity (lib/BuildCubeSat/UnityLightCurveInversion.exe, built from unity_project/) renders the NASA-style 3D model of the CubeSat class, oriented with the attitude of the pass and lit by the Sun, from an orthographic camera at the observer; the integrated flux of every frame is the light curve (flux.csv).

The apparent visual magnitude is estimated with a diffuse-sphere model, m = -26.74 - 2.5 log10(albedo R² Phi(phase) / d²) (R the radius of a disc with the reference area, Phi the Lambert phase function, d the range), and the peak is compared with the limiting magnitude of the site (7). The Unity flux is instrumental and not calibrated.

## When the planner should select this module

Select END-010 when the request mentions the reflectance, brightness, apparent magnitude or light curve of the satellite, its visibility from optical ground observatories or telescopes, light pollution or impact on astronomy, or a night observation from an observatory (Matera by default). END-010 needs END-001 (which chooses the first night pass visible from the observatory with the satellite sunlit) and END-003 (attitude of that pass) earlier in the same workflow; the END-006 initial design gives the CubeSat class of the 3D model.

## Input interface

The runner (BackEnd/runners/end010_runner.py; configuration by build_end010_config and end010_cubesat_options in star_runner_io.py) writes modules_output/END-010/end010_runtime_input.json from Input/input_reflectance_determination.json:

- pass: output_attitude_propagation_lightcurve_ECI.csv of END-003 (timestamp, ECI position, body->ECI quaternion) and the observer of selected_passes.json (name, latitude, longitude, altitude); without a night pass, the END-003 imaging pass in true ECI and its site (never the Unreal file, which uses other axes);
- satellite: CubeSat class of the END-006 initial design (3D model; camera half-height = half the envelope diagonal x 1.1) and its mean projected area as reference area; without END-006 the default class;
- data files: lib/data/EOP.txt, TLE, stations.json, DE440.mat and lib/sgp4/nut80.dat;
- Unity options: frames to render and save, resolution, orthographic projection, linear colour space, radiometric model, scene scale.

## Output interface

- modules_output/END-010/output_reflectance_determination/flux.csv — the light curve (instrumental flux of every instant) and the Unity log;
- modules_output/END-010/results_reflectance_determination/reflectance_summary.json — KPI-01 to KPI-16: Unity simulation completed, flux samples, frames rendered, invalid samples, pass duration, maximum elevation, visible fraction, mean and minimum object-station range, mean phase angle, mean and peak instrumental flux, light-curve amplitude and RMS variability, peak apparent visual magnitude (estimate), site limiting magnitude; observatory;
- reflectance_timeseries.json — geometry and photometry time series for the END010 results tab;
- csvUnity.csv (geometry passed to Unity), Frames/*.png (rendered frames), Plots/*.png (phase angle, ground track, camera angles).

Status: `completed`; `failed` when MATLAB ends with an error, for example when DE440.mat or the Unity build is missing.

## Relationship with other modules

- END-001 chooses the night pass visible from the observatory (pass_selection.json); END-003 computes its attitude and writes its ECI CSV; END-006 gives the CubeSat class and the reference area.
- STAR compliance reads the peak apparent magnitude and the observatory (requirement on the brightness); END010 results tab.

## Known limits

DE440.mat (over 50 MB) and the Unity builds (lib/BuildCubeSat/, lib/BuildAqua/) are not in the repository and are copied by hand on the STAR PC. The magnitude is an analytical estimate (albedo 0.2 by default), the 3D model is the NASA-style model of the class, not the satellite with its components; the site limiting magnitude is fixed at 7. Windows only (Unity player). A run takes about one minute.
