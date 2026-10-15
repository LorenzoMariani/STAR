| | <p>PROGETTO: “SPACE IT UP !”</p><p>Contratto n. 2024-5-E.0. – CUP: I53D24000060005</p><p>Interface Definition Document (IDD)</p><p>END-010: REFLECTANCE MODULE</p> | <p>DOCUMENT ID:</p><p>DX.X.X\_Spoke2\_XXX\_2026</p><p></p><p>DATE OF DELIVERY: XX/XX/2026</p><p></p><p>REV.: V0.1</p><p></p><p>Pag: 9 di 34</p> |
| :-: | :-: | :- |

**Interface Definition Document (IDD)**

**END-010: REFLECTANCE MODULE**

# **List of Contents**

[**1.** **Introduction** 2](#_toc230170069)

[**1.1.** **Functionalities description** 2](#_toc230170070)

[**1.2.** **Use case scenarios** 2](#_toc230170071)

[**2.** **Responsibility** 2](#_toc230170072)

[**3.** **Applicable and reference documents** 2](#_toc230170073)

[**4.** **Definition of terms and abbreviated terms** 3](#_toc230170074)

[**5.** **Interface end definition** 3](#_toc230170075)

[**5.1.** **Interface end description and data definition** 3](#_toc230170076)

[**5.2.** **Units of measure including scale of measure** 3](#_toc230170077)

[**5.3.** **Tolerances or required accuracies** 3](#_toc230170078)

[**5.4.** **In case of using non-SI quantities or units, conversions and conventions** 3](#_toc230170079)

[**5.5.** **Interface plane implementation** 3](#_toc230170080)

[**5.6.** **Interface end behaviour** 4](#_toc230170081)

[**5.7.** **Interface end data** 4](#_toc230170082)

[**6.** **Special Remarks** 4](#_toc230170083)

[**7.** **Software** 4](#_toc230170084)

[**7.1.** **Operating system** 4](#_toc230170085)

[**7.2.** **Operating hardware** 4](#_toc230170086)

[**7.3.** **Required software libraries** 4](#_toc230170087)

[**7.4.** **Required compiler, build environment** 5](#_toc230170088)

[**7.5.** **API definition** 5](#_toc230170089)

[**7.6.** **Errors and warnings returned** 5](#_toc230170090)

[**7.7.** **Map of inputs/outputs** 5](#_toc230170091)


1. ## <a name="_toc230170069"></a>**Introduction**

The present Interface Definition Document (IDD) describes the software interface associated with **END-010: Reflectance Module** within the STAR framework. The document defines the purpose, execution logic, input/output data structures, operating assumptions, software dependencies and expected behaviour of the module, so that the component can be integrated consistently within the STAR orchestration workflow.

The END-010 module is intended to support reflectance and light-curve analysis for space objects or mission-relevant observation scenarios. It combines orbital, solar, observatory and attitude information with a Unity-based rendering/simulation environment in order to generate time-tagged reflectance products, simulation frames, light-curve outputs and optional diagnostic plots.

1. ### <a name="_toc230170070"></a>**Functionalities description**

The core functionality of this module lies in its ability to transform orbital, attitude, illumination and observer-geometry information into reflectance-oriented simulation products. The functional architecture can be divided into five main processing phases:

- **Configuration and Environment Parsing:** The module ingests a structured JSON configuration file (`input_reflectance_determination.json`) that defines data paths, simulation settings, ephemeris flags, observatory information and Unity execution options. It initializes the MATLAB workspace, appends the required internal libraries, and prepares the runtime output directories.
- **Ephemeris and Reference Data Loading:** The module loads external data required for the propagation and geometry reconstruction, including SGP4-related nutation data, DE440 ephemeris coefficients, station definitions, TLE/EOP files and optional externally supplied ephemerides.
- **Orbit, Sun, Observatory and Attitude Reconstruction:** Depending on the configuration flags, the module either reads a timestamped CSV containing ECI orbit and attitude data or internally propagates the orbital state, Sun vector, observatory geometry and attitude profile. Quaternion-based attitude data and auxiliary line-of-sight quantities are synchronized over the simulation timeline.
- **Unity Input Generation and Simulation Execution:** The module writes a `csvUnity.csv` file containing timestamped orbit, Sun, observatory, elevation, range and attitude information. This file is passed to a Unity executable through the configured `unityOpts` structure. The Unity simulation generates render frames, a reflectance or flux time series and execution logs.
- **Diagnostic Plot Generation:** When debug mode is enabled, the module computes and exports diagnostic plots such as phase-angle curves, camera-angle curves and ground-track visualization products. These plots are used to inspect consistency between the MATLAB-side geometry and the Unity-side simulation convention.

1. ### <a name="_toc230170071"></a>**Use case scenarios**

The software is suitable for operational and research scenarios in which reflectance, illumination geometry and observation conditions are relevant to mission analysis:

- **Reflectance and Light-Curve Simulation:** For a defined target object, observatory and illumination geometry, the module can generate a time-tagged reflected-light or flux output suitable for preliminary visibility, detectability or photometric analysis.
- **Geometry-to-Rendering Verification:** The module supports verification of the consistency between orbital/attitude states and Unity rendering inputs by generating `csvUnity.csv` and optional diagnostic plots comparing phase-angle, camera-angle and ground-track behaviour.
- **Use of External Orbit and Attitude Products:** When an upstream module provides timestamped ECI position and quaternion attitude data, the module can ingest those data directly through the configured input CSV instead of recomputing the full propagation internally.
- **Mission-Level Observation Analysis:** The module can support preliminary mission studies where attitude visualization, optical detectability, illumination conditions or observation geometry must be connected to rendered frames and reflectance time series.

1. ## <a name="_toc230170072"></a>**Responsibility**

Responsible for END-010:

- Lorenzo Mariani (UNIRM1) Leader
- Fabrizio Piergentili (UNIRM1) Co-Leader

1. ## <a name="_toc230170073"></a>**Applicable and reference documents**

- STAR\_ProductTree

1. ## <a name="_toc230170074"></a>**Definition of terms and abbreviated terms**

|***Term / Abbreviation***|***Definition***|
| :- | :- |
|***API***|Application Programming Interface|
|***CSV***|Comma-Separated Values file format used for tabular data exchange|
|***DE440***|JPL planetary and lunar ephemeris model used for high-precision celestial reference data|
|***ECI***|Earth-Centered Inertial reference frame|
|***ECEF***|Earth-Centered Earth-Fixed reference frame|
|***EOP***|Earth Orientation Parameters|
|***JSON***|JavaScript Object Notation, lightweight structured data-interchange format|
|***LLA***|Latitude, Longitude, Altitude geodetic coordinate representation|
|***MATLAB***|Numerical computing environment used to execute the END-010 processing chain|
|***OEM***|Orbit Ephemeris Message|
|***Quaternion***|Four-component attitude representation used to describe spacecraft orientation|
|***SGP4***|Simplified General Perturbations 4 orbit propagation model|
|***TLE***|Two-Line Element orbital data format|
|***Unity***|Real-time rendering/simulation engine used for reflectance and frame generation|
|***UTC***|Coordinated Universal Time|


1. ## <a name="_toc230170075"></a>**Interface end definition**

1. ### <a name="_toc230170076"></a>**Interface end description and data definition**

The **STAR END-010 Reflectance Module** software node acts as a file-based computational engine that couples MATLAB-side orbital/attitude/illumination processing with Unity-side visual or photometric simulation. The data interface structure relies on a decoupled input/output subsystem:

- **Ingress Interface:** A structured JSON configuration file, conventionally named `input_reflectance_determination.json`, containing paths to auxiliary data, simulation flags, observatory settings, Unity execution options and optional input CSV references.
- **Optional Ingress Interface:** A timestamped input CSV file containing ECI position and quaternion attitude data. When `cfg.flags.useInputCsv` is enabled, this CSV is read directly and used to synchronize orbit, attitude, Sun and observatory quantities.
- **Egress Interface:** A designated output directory populated with reflectance-determination products, including the Unity input CSV (`csvUnity.csv`), simulation frames, light-curve/flux output, Unity log files and optional diagnostic plots.

The module uses the JSON configuration to construct internal MATLAB structures, read external reference files, prepare Unity input data and launch the configured Unity executable through `runUnity`.

1. ### <a name="_toc230170077"></a>**Units of measure including scale of measure**

The software uses standard scientific and astrodynamic conventions, with the following main units and scales:

- **Time:** Simulation epochs are handled as MATLAB `datetime` values. Timestamped CSV inputs use UTC-like strings, for example `yyyy-MM-ddTHH:mm:ss`. Simulation grids are generated using a start epoch, duration and time step expressed in seconds.
- **Position vectors:** ECI vectors (`reci`, `rseci`, `rsun`) are handled as numerical arrays. In the input CSV workflow, ECI coordinates are expected in kilometres (`eci_x_km`, `eci_y_km`, `eci_z_km`).
- **Angles:** Geodetic latitude and longitude may be read in degrees and internally converted to radians for propagation functions. Phase angle, camera angle and related diagnostic quantities are computed and plotted in degrees.
- **Altitude:** Observatory altitude is converted from metres to kilometres where required by the internal LLA representation.
- **Attitude:** Spacecraft attitude is represented by unit quaternions (`q_w`, `q_x`, `q_y`, `q_z`) or by internally propagated attitude states.
- **Reflectance / Flux:** The Unity-generated light-curve output is written as a CSV product. Its physical unit is governed by the Unity rendering model and the configured reflectance/illumination assumptions.

1. ### <a name="_toc230170078"></a>**Tolerances or required accuracies**

The module does not define hard-coded numerical tolerances inside the interface layer. The effective accuracy of the output products depends on:

- the temporal resolution defined by `cfg.simulation.delta`;
- the accuracy and consistency of TLE, EOP, SGP4 and DE440 input data;
- the quality and timestamp consistency of any externally supplied orbit or attitude CSV;
- the Unity rendering configuration, camera setup, reflectance model and frame-generation settings;
- the precision of the MATLAB propagation and attitude routines available in the internal `lib` folders.

For interface-level consistency, all input files shall be time-synchronized over the same simulation interval and shall use the coordinate and attitude conventions expected by the module.

1. ### <a name="_toc230170079"></a>**In case of using non-SI quantities or units, conversions and conventions**

The following non-SI or mixed engineering quantities are used by the module:

- **Angular quantities:** Latitude, longitude, phase angle, elevation, camera angle and diagnostic angular products may be represented in degrees for input/output readability and converted to radians for internal propagation operations.
- **Orbital coordinates:** ECI and related vectors may be represented in kilometres in the CSV interface, following the naming convention `eci_x_km`, `eci_y_km`, `eci_z_km`.
- **Quaternion attitude:** Attitude quaternions are non-dimensional and are expected to follow the ordering used by the input CSV and internal propagation functions.
- **Unity coordinate convention:** Before Unity execution, the module transforms selected vectors into the coordinate convention required by the Unity simulation pipeline.

1. ### <a name="_toc230170080"></a>**Interface plane implementation**

The interface plane is implemented through file-system and process-level interfaces:

- MATLAB reads the main JSON configuration file from disk.
- MATLAB reads auxiliary ephemeris, station, TLE, EOP and optional CSV files through paths specified in the configuration.
- MATLAB writes `csvUnity.csv` and output folders under the selected output directory.
- MATLAB launches Unity using the configured Unity executable path and `unityOpts` structure.
- Unity writes frames, flux/light-curve outputs and log files in the output folders assigned by MATLAB.

Within STAR, the module is expected to be invoked through a Python runner that calls MATLAB in batch mode and passes the input/output path information to the script.

1. ### <a name="_toc230170081"></a>**Interface end behaviour**

Upon execution, the software responds according to the following execution pipeline:

1. **Initialization:** Clears the MATLAB workspace and appends the required internal library folders (`lib`, `lib/data`, `lib/sgp4`, `lib/BuildAqua`) to the MATLAB path.
1. **Configuration Loading:** Reads and decodes the selected JSON configuration file.
1. **Output Folder Setup:** Creates the output folder hierarchy, including `results_reflectance_determination`, `Plots`, `Frames` and `output_reflectance_determination`.
1. **Reference Data Loading:** Loads SGP4/nutation data and DE440 coefficients from the paths specified in the configuration file.
1. **Observatory Setup:** Reads station data and reconstructs the observer geodetic state.
1. **Ephemeris Branching:** If `useInputCsv` is enabled, reads timestamped ECI position and quaternion attitude from CSV. Otherwise, internally propagates orbit, Sun, observer and attitude data using the configured flags and auxiliary files.
1. **Unity CSV Generation:** Writes `csvUnity.csv`, containing the time series required by the Unity simulation.
1. **Unity Execution:** Configures Unity options, assigns CSV, frame output, light-curve output and log-file paths, then launches Unity through `runUnity`.
1. **Debug Plot Generation:** When debug mode is enabled, exports phase-angle, camera-angle and ground-track plots under the `Plots` directory.
1. **Status Return:** Returns the Unity execution status as the direct output of the main MATLAB function.

1. ### <a name="_toc230170082"></a>**Interface end data**

The primary input configuration is a JSON file with the following logical structure. The exact field population depends on the selected propagation mode and Unity configuration.

```json
{
  "paths": {
    "nutData": "path/to/nut80.mat",
    "deData": "path/to/DE440Coeff.mat",
    "stationsJson": "path/to/stations.json",
    "tleFile": "path/to/object.tle",
    "eopFile": "path/to/eop.txt",
    "inputCsv": "path/to/input_orbit_attitude.csv",
    "unityExe": "path/to/UnityExecutable"
  },
  "simulation": {
    "debug": true,
    "observatory": "station_name",
    "mask": 5,
    "start": "YYYY-MM-DDTHH:mm:ss",
    "duration": 3600,
    "delta": 1
  },
  "flags": {
    "useInputCsv": true,
    "orbitEphemeris": false,
    "sunEphemeris": false,
    "obsEphemeris": false,
    "attEphemeris": false
  },
  "unityOpts": {
    "logFile": "unity_log.txt"
  }
}
```

When `useInputCsv` is enabled, the input CSV shall include at least the following logical fields:

|***Field***|***Description***|
| :- | :- |
|`timestamp_utc`|UTC timestamp associated with the orbit and attitude sample|
|`eci_x_km`, `eci_y_km`, `eci_z_km`|Target/object ECI position components in kilometres|
|`q_w`, `q_x`, `q_y`, `q_z`|Quaternion attitude components|

The principal output data products are:

|***Output entity***|***Description***|
| :- | :- |
|`results_reflectance_determination/csvUnity.csv`|CSV time series generated by MATLAB and passed to Unity|
|`results_reflectance_determination/Frames/`|Unity-generated frames|
|`results_reflectance_determination/Plots/`|Diagnostic plots generated when debug mode is enabled|
|`output_reflectance_determination/flux.csv`|Unity-generated reflectance/light-curve output|
|`output_reflectance_determination/<logFile>`|Unity execution log file|

1. ## <a name="_toc230170083"></a>**Special Remarks**

Interfaces in STAR:

- **IF-004: REFLECTANCE MODULE (END-010) – ATTITUDE VISUALIZATION (END-004)** The END-010 module consumes attitude and observation-geometry-related information that may be generated or visualized by END-004. The reflectance module transforms this geometry into simulation-ready Unity inputs and reflectance/light-curve products.
- **Potential interface with upstream orbit/attitude modules:** END-010 may consume orbit and attitude products produced by upstream STAR modules, provided they are exported using the timestamped CSV convention expected by the module.
- **Nomenclature note:** The uploaded MATLAB source header currently contains the label `END-016`, while the function name and STAR canonical module catalogue identify the implemented module as END-010 Reflectance Determination. This IDD adopts the END-010 nomenclature.

1. ## <a name="_toc230170084"></a>**Software**

1. ### <a name="_toc230170085"></a>**Operating system**

The script is designed primarily for workstation environments capable of hosting MATLAB and the configured Unity executable. Absolute file paths specified in the current execution driver use Windows-style syntax conventions (`C:\Users\...`). Execution on Linux or macOS would require path adaptation and availability of equivalent MATLAB and Unity runtime environments.

1. ### <a name="_toc230170086"></a>**Operating hardware**

The software requires a computational engineering workstation capable of running MATLAB and Unity. Hardware requirements depend on simulation duration, time-step resolution, frame-generation settings and Unity rendering complexity. GPU resources may be relevant when high-resolution frame rendering or long Unity simulations are executed.

1. ### <a name="_toc230170087"></a>**Required software libraries**

The runtime path environment requires the following software components:

- **MATLAB Core Environment**, including JSON parsing, datetime handling, matrix operations and plotting/export features.
- **Internal STAR END-010 libraries**, located under the module `lib` directory.
- **SGP4 support routines**, located under `lib/sgp4`.
- **Reference data utilities**, located under `lib/data`.
- **Unity execution support**, including the Unity executable referenced by `cfg.paths.unityExe` and the `runUnity` helper routine.
- **Mapping/plotting support**, when debug visualizations are enabled. For example, functions such as `geoshow` require the appropriate MATLAB toolbox availability.

1. ### <a name="_toc230170088"></a>**Required compiler, build environment**

No standalone compilation step is required for the MATLAB interface itself. The operational environment shall include:

- a MATLAB installation capable of executing the module scripts and internal functions;
- access to all module-specific library folders;
- a configured Unity executable compatible with the expected command-line invocation;
- read permissions for configuration, ephemeris and input data files;
- write permissions for the selected output directory.

1. ### <a name="_toc230170089"></a>**API definition**

The system exposes its primary programmatic access through a single main MATLAB entry-point function:

**Function Prototype / Signature**

```matlab
status = STAR_END010_REFLECTANCE_DETERMINATION(configFile, output_folder)
```

**Input Parameters**

1. `configFile`
   1. *Type:* string or char array.
   1. *Format:* Absolute or relative system file path referencing a valid JSON configuration file.
   1. *Content:* Paths, simulation settings, flags, observatory selection and Unity execution options.
1. `output_folder`
   1. *Type:* string or char array.
   1. *Format:* Absolute or relative system path pointing to the destination directory where generated reflectance products, Unity files, plots and logs will be written.

**Output Parameters**

- `status`
  - *Type:* numerical or status value returned by the Unity execution helper.
  - *Meaning:* Indicates the completion state of the Unity simulation as returned by `runUnity`.

**Internal Constraints & Exceptions**

- The JSON configuration must expose the expected `paths`, `simulation`, `flags` and `unityOpts` structures.
- If `cfg.flags.useInputCsv` is enabled, the CSV must include timestamped ECI position and quaternion attitude fields.
- If external ephemeris flags are enabled, the corresponding OEM/DBL/CSV files must be selected or available.
- Unity output generation depends on a valid Unity executable path and compatible `unityOpts` fields.

1. ### <a name="_toc230170090"></a>**Errors and warnings returned**

The routine incorporates deterministic runtime validations and may trigger MATLAB errors or Unity status failures in the following cases:

- `error('STAR_END010_REFLECTANCE_DETERMINATION: File JSON not found: %s', configFile);` triggered when the main JSON configuration file is not available.
- `error('File SGP4 not found: %s', cfg.paths.nutData);` triggered when the required SGP4/nutation data file is missing.
- `error('File DE440 not found: %s', cfg.paths.deData);` triggered when the DE440 coefficient data file is missing.
- `error('STAR_END010_REFLECTANCE_DETERMINATION: Input CSV file not found: %s', cfg.paths.inputCsv);` triggered when `useInputCsv` is enabled but the expected CSV file is not available.
- External file-selection branches may fail or stop execution if required OEM, attitude or ephemeris files are not selected correctly.
- Unity execution may return a non-zero or failure status through `runUnity`, depending on the Unity executable, scene configuration, input CSV validity and output path accessibility.

1. ### <a name="_toc230170091"></a>**Map of inputs/outputs**

The following matrix describes the file access map, including specific read/write access permissions:

|***Target File Entity***|***I/O Category***|***File Data Format***|***Description / Content Scope***|***Access Permission***|
| - | - | - | - | - |
|***configFile***|Input|Structured JSON|Main configuration file containing paths, simulation settings, flags, observatory selection and Unity options.|**Read-Only (r)**|
|***cfg.paths.nutData***|Input|MAT-file|SGP4/nutation support data loaded by MATLAB.|**Read-Only (r)**|
|***cfg.paths.deData***|Input|MAT-file|DE440 coefficient data loaded by MATLAB.|**Read-Only (r)**|
|***cfg.paths.stationsJson***|Input|JSON|Ground station / observatory definition file.|**Read-Only (r)**|
|***cfg.paths.tleFile***|Input|TLE/Text|TLE file used for propagation when required.|**Read-Only (r)**|
|***cfg.paths.eopFile***|Input|Text|Earth Orientation Parameters used by the propagation routines.|**Read-Only (r)**|
|***cfg.paths.inputCsv***|Input|CSV|Optional timestamped ECI orbit and quaternion attitude input file.|**Read-Only (r)**|
|***csvUnity.csv***|Output|CSV|Time series generated by MATLAB for Unity simulation input.|**Write-Only (w)**|
|***results_reflectance_determination/Frames***|Output|Folder / image sequence|Unity-generated rendered frames.|**Write-Only (w)**|
|***output_reflectance_determination/flux.csv***|Output|CSV|Unity-generated reflectance/light-curve output.|**Write-Only (w)**|
|***output_reflectance_determination/log file***|Output|Text log|Unity execution log file named according to `cfg.unityOpts.logFile`.|**Write-Only (w)**|
|***results_reflectance_determination/Plots***|Output|PNG figures|Diagnostic plots generated when debug mode is enabled.|**Write-Only (w)**|
