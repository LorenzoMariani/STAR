|![](Aspose.Words.2132cd9c-5305-4f61-98aa-e07ae76327a7.001.png)|<p>PROGETTO: “SPACE IT UP !”</p><p>Contratto n. 2024-5-E.0. – CUP: I53D24000060005</p><p>Interface Definition Document (IDD)</p><p>END-001: CONSTELLATION OPTIMIZER</p>|<p>DOCUMENT ID:</p><p>DX.X.X\_Spoke2\_XXX\_2026</p><p></p><p>DATE OF DELIVERY: XX/XX/2026</p><p></p><p>REV.: V0.1</p><p></p><p>Pag: 9 di 34</p>|
| :-: | :-: | :- |

**Interface Definition Document (IDD)**

**END-001: CONSTELLATION OPTIMIZER**

# **List of Contents**

[**1.**	**Introduction**	2](#_toc230170069)

[**1.1.**	**Functionalities description**	2](#_toc230170070)

[**1.2.**	**Use case scenarios**	2](#_toc230170071)

[**2.**	**Responsibility**	2](#_toc230170072)

[**3.**	**Applicable and reference documents**	2](#_toc230170073)

[**4.**	**Definition of terms and abbreviated terms**	3](#_toc230170074)

[**5.**	**Interface end definition**	3](#_toc230170075)

[**5.1.**	**Interface end description and data definition**	3](#_toc230170076)

[**5.2.**	**Units of measure including scale of measure**	3](#_toc230170077)

[**5.3.**	**Tolerances or required accuracies**	3](#_toc230170078)

[**5.4.**	**In case of using non-SI quantities or units, conversions and conventions**	3](#_toc230170079)

[**5.5.**	**Interface plane implementation**	3](#_toc230170080)

[**5.6.**	**Interface end behaviour**	4](#_toc230170081)

[**5.7.**	**Interface end data**	4](#_toc230170082)

[**6.**	**Special Remarks**	4](#_toc230170083)

[**7.**	**Software**	4](#_toc230170084)

[**7.1.**	**Operating system**	4](#_toc230170085)

[**7.2.**	**Operating hardware**	4](#_toc230170086)

[**7.3.**	**Required software libraries**	4](#_toc230170087)

[**7.4.**	**Required compiler, build environment**	5](#_toc230170088)

[**7.5.**	**API definition**	5](#_toc230170089)

[**7.6.**	**Errors and warnings returned**	5](#_toc230170090)

[**7.7.**	**Map of inputs/outputs**	5](#_toc230170091)


1. ## <a name="_toc230170069"></a>**Introduction**

The IDD shall contain a description of the purpose, objective, content and the reason prompting its preparation.

1. ### <a name="_toc230164775"></a><a name="_toc230165050"></a><a name="_toc230166006"></a><a name="_toc230166124"></a><a name="_toc230166211"></a><a name="_toc230166292"></a><a name="_toc230166362"></a><a name="_toc230166444"></a><a name="_toc230166529"></a><a name="_toc230166588"></a><a name="_toc230166646"></a><a name="_toc230166695"></a><a name="_toc230166756"></a><a name="_toc230166819"></a><a name="_toc230170070"></a>**Functionalities description**

The core functionality of this module lies in its ability to solve highly non-linear, multi-objective orbital mechanics problems by balancing user-defined operational constraints against global constellation performance metrics. The functional architecture can be divided into four main processing phases:

- **Space-Environment and Constraints Parsing:** The module ingests raw physical and geodetic constraints, processing the Region of Interest (ROI) and translating Ground Station coordinates into a multi-dimensional topological matrix. It evaluates payload sensor constraints (SAR, PBS, or CON) and maps specific look-angle configurations (e.g., minimum and maximum elevation thresholds), which directly shape the mathematical boundaries of the search space.
- **Multi-Objective Optimization Search:** Depending on the input profile, the system dynamically scales the optimization parameter space vector. It leverages evolutionary heuristic frameworks, such as the Non-dominated Sorting Genetic Algorithm II (MOGA NSGA-II) or the PlatEMO multi-objective platform, to concurrently minimize variables like maximum revisit time, launch cost, or collision risks, while maximizing average Ground Station access windows and overall constellation robustness.
- **Analytical SSO/RGT Astrodynamics Decoding:** Once the optimizer converges on the absolute Pareto-optimal front, the module extracts the primary solution vector. It runs analytical orbital perturbation equations to calculate the inclination required to maintain Sun-Synchronous or Repeat Ground Track characteristics based on the optimized target altitude.
- **Walker Delta Constellation:** The module automatically applies the Walker Delta constellation distribution laws (T/P/F). It structurally computes the Right Ascension of the Ascending Node (RAAN) across the derived orbital planes and distributes individual spacecraft true anomalies to maximize coverage uniformity. Finally, it formats, prints, and writes these states into JSON structures.


1. ### <a name="_toc230164776"></a><a name="_toc230165051"></a><a name="_toc230166007"></a><a name="_toc230166125"></a><a name="_toc230166212"></a><a name="_toc230166293"></a><a name="_toc230166363"></a><a name="_toc230166445"></a><a name="_toc230166530"></a><a name="_toc230166589"></a><a name="_toc230166647"></a><a name="_toc230166696"></a><a name="_toc230166757"></a><a name="_toc230166820"></a><a name="_toc230170071"></a>**Use case scenarios**

The software makes it suitable for a variety of operational and research scenarios within the space mission architecture design:

- **Initial Constellation Sizing for Earth Observation Missions:** For newly proposed remote sensing or communication missions where the optimal orbital configuration is unknown, the software, by ingesting regional coordinates, ground station locations, and payload requirements, provides an estimation of coverage performance and satellite count to identify the most cost-effective deployment topologies.
- **Trade-Off Analysis: C**ompare and evaluate different constellation design against the same mission goals. By systematically varying configuration inputs, such as switching between Sun-Synchronous (SSO) and Repeat Ground Track (RGT) geometries, or testing hybrid orbital types, the tool serves to trade off coverage uniformity, robustness, and ground segment access times across different candidates.

1. ## <a name="_toc230170072"></a>**Responsibility**

Responsible for END-001:

- Lorenzo Mariani (UNIRM1) Leader
- Fabrizio Piergentili (UNIRM1) Co-Leader

1. ## <a name="_toc230170073"></a>**Applicable and reference documents**

- STAR\_ProductTree

1. ## <a name="_toc230170074"></a>**Definition of terms and abbreviated terms**

|***Term / Abbreviation***|***Definition***|
| :- | :- |
|***API***|Application Programming Interface|
|***CON***|Conventional (Optical/Passive) Sensor operative mode |
|***FOV***|Field of View of a spacecraft sensor payload |
|***GS***|Ground Station |
|***JSON***|JavaScript Object Notation (lightweight data-interchange format) |
|***MOGA***|Multi-Objective Genetic Algorithm |
|***MS***|Multi-Sensor operative mode |
|***NSGA-II***|Non-dominated Sorting Genetic Algorithm II |
|***OPMOD***|Operative Mode |
|***PBS***|Push-Broom Sensor operative mode |
|***RAAN***|Right Ascension of the Ascending Node ($\Omega$) |
|***RGT***|Repeat Ground Track orbit |
|***ROI***|Region of Interest |
|***SAR***|Synthetic Aperture Radar operative mode |
|***SS***|Single Sensor operative mode |
|***SSORGT***|Sun-Synchronous Orbit Repeat Ground Track |
|***WGS-84***|World Geodetic System 1984 (Ellipsoid constants used: Re, mu, J2) |
**\



1. ## <a name="_toc230170075"></a>**Interface end definition**

1. ### <a name="_toc230170076"></a>**Interface end description and data definition** 

The **STAR END-001 Constellation Optimizer** software node acts as an autonomous computational engine designed to optimize satellite constellation topologies. The data interface structure relies on a decoupled, file-based input/output subsystem: 

- **Ingress Interface:** A single, structured configuration file in JSON format (input\_constellation\_optimizer.json) containing system-level user constraints, time variables, orbital boundaries, and optimizer configuration profiles. 

**Egress Interface:** A designated directory populated with discrete, parsed JSON files named sequentially (satellite\_01.json, satellite\_02.json, etc.), where each file encapsulates the definitive Keplerian orbital state vectors and metadata for an individual satellite within the optimized constellation.

1. ### <a name="_toc230170077"></a>**Units of measure including scale of measure**

The software utilizes standard SI units for physical and mathematical processing, with specific spatial and orbital engineering conventions: 

- **Time:** Calendar dates are expressed via the Gregorian calendar format (YYYY-MM-DD hh:mm:ss) and internally processed using continuous Julian Dates (JD) or decimal days. Simulation duration is scaled in hours. 
- **Distance / Altitude:** Scaled from kilometers (km) within the optimizer optimization search space bounds to absolute meters (m) for geodetic, astrodynamic, and output structural models. 
- **Angles:** Angular geodetic positions (Latitude, Longitude), Sensor Field of Views (FOV), and Ground Station elevation masks are scaled in degrees (deg). Astrodynamic Keplerian elements (RAAN, True Anomaly - nu) are handled in radians (rad) during internal mathematical loops and converted to degrees ranging from 0 deg to 360 deg (or clipped from -180 deg to +180 deg) for external interface synchronization. 

1. ### <a name="_toc230170078"></a>**Tolerances or required accuracies**



1. ### <a name="_toc230170079"></a>**In case of using non-SI quantities or units, conversions and conventions**

- **Chronological Scale Transformation:** Calendar date inputs are converted into an absolute Julian Date framework.
- **Optimization Weight Normalization:** User-defined optimization weights (W) are dynamically treated as relative non-dimensional values and scaled into a unified normalized system via a sum-of-elements scaling function: 

W\_i = W\_i \ (sum\_{j=1-10} W\_j)

This guarantees that sum(W\_i) = 1.0 regardless of the initial input scale. 

1. ### <a name="_toc230170080"></a>**Interface plane implementation**



1. ### <a name="_toc230170081"></a>**Interface end behaviour**

Upon execution, the software responds according to the following execution pipeline: 

1. **Initialization:** Appends internal library folders, algorithm repositories (PlatEMO), and mathematical toolboxes to the executable workspace path. 
1. **Configuration Loading:** Ingests the specified input JSON configuration structure. 
1. **Temporal & Spatial Parsing:** Reconstructs the reference starting epoch and instantiates geodetic region constraints (ROI) alongside ground station (GS) matrix allocations. 
1. **Constraint Setup:** Sets up sensor configuration flags (SAR, PBS, CON) and normalizes optimization performance weights. 
1. **Bound Enforcement:** Establishes low-bound (lb) and up-bound (ub) vectors based on the selected operational mode (Multi-Sensor vs. Single Sensor). 
1. **Optimization Engine Routine:** Directs execution flow to the core optimization blocks (MOGA or PLATEMO) according to the designated algorithm type (e.g., MOGA NSGA-II, PSO-based, PlatEMO) and orbital class (SSORGT, RGT, Hybrid). 
1. **Pareto Front Selection:** Extracts the absolute primary optimized solution vector (x\_best) from the generated Pareto optimal front. 
1. **Walker Delta Decoding:** Analytically computes the distinct Keplerian parameters for each satellite, enforcing uniform RAAN separation across calculated orbital planes and applying Walker phasing steps for the true anomaly (nu) of each asset. 
1. **Serialization:** Commits individual satellite structural objects to disk in standardized JSON syntax with 'PrettyPrint' legibility formatting. 

1. ### <a name="_toc230170082"></a>**Interface end data**

Each generated satellite output JSON structure conforms to the following schema definition: 

{

`  `"sim\_start\_date": "YYYY-MM-DD hh:mm:ss",

`  `"sim\_hours": 48,

`  `"orbit": {

`    `"alt\_perigee\_m": double,

`    `"alt\_apogee\_m": double,

`    `"inclination\_deg": double,

`    `"raan\_deg": double,

`    `"omega\_deg": 0,

`    `"nu\_deg": double

`  `}

}

sim\_start\_date: String representing the absolute initial simulation epoch. 

sim\_hours: Constant numerical double defining simulation duration window (hardcoded to 48 hours). 

orbit: Sub-structure grouping the physical Keplerian parameters: 

- alt\_perigee\_m / alt\_apogee\_m: Orbit altitudes in meters, assuming circular configurations derived from the optimized kilometer parameter. 
- inclination\_deg: Orbital inclination expressed in degrees, calculated via analytical perturbation models for SSO or set to a fallback standard value (98 deg). 
- raan\_deg: Right Ascension of the Ascending Node for the specific orbital plane, ranging within [-180 deg, 180 deg]. 
- omega\_deg: Argument of perigee in degrees (fixed to 0 for circular assumptions). 
- nu\_deg: True anomaly of the spacecraft at the starting epoch, derived via Walker Delta positioning laws.

1. ## <a name="_toc230170083"></a>**Special Remarks**

Interfaces in STAR:

- **IF-001: CONSTELLATION OPTIMIZER (END-001) – SYNTHETIC DATA GENERATION (END-007)** The output data produced by END-001 serves as the primary initialization for the Synthetic Data Generation node (END-007). By establishing standardized Keplerian parameters, and time-tagged positions strings, IF-001 ensures synchronization between the orbital configuration found by the optimizer and the subsequent payload data simulation routines within the STAR framework. 

1. ## <a name="_toc230164789"></a><a name="_toc230165064"></a><a name="_toc230170084"></a>**Software**

1. ### <a name="ecss_e_st_10_24_1290199"></a><a name="ecss_e_st_10_24_1290200"></a><a name="_toc230164790"></a><a name="_toc230165065"></a><a name="_toc230170085"></a>**Operating system**

The script is designed for compatibility with cross-platform operating systems (Microsoft Windows, Linux, or macOS) capable of hosting the target MATLAB environment. Absolute file paths specified in the execution driver script utilize standard Windows-style syntax conventions (C:\Users\...). 

1. ### <a name="_toc230164791"></a><a name="_toc230165066"></a><a name="_toc230170086"></a>**Operating hardware**

Standard computational engineering workstation configuration. The software handles multi-variable multi-objective evolutionary algorithms, which require adequate RAM allocation and CPU capabilities proportional to the population sizes (N\_pop) and iteration loops (N\_gen) defined inside the input configuration file. 

1. ### <a name="_toc230164792"></a><a name="_toc230165067"></a><a name="_toc230170087"></a>**Required software libraries**

The runtime path environment requires the mandatory inclusion of the following software packages and analytical suites: 

- **MATLAB Core Environment** (including JSON handling features). 
- **PlatEMO Library Subsystem:** Specifically requires access to the path hierarchy located at \lib\FUNCTIONS\PlatEMO, including user-defined evolutionary problem spaces (\Problems\My Problems\). 
- **MOGA NSGA-II Toolbox:** Located at \lib\FUNCTIONS\MOGA NSGA-II. 

**Geodetic and Orbital Functions:** Internal custom helper functions located in the \lib\FUNCTIONS\ root subdirectory.

1. ### <a name="_toc230164793"></a><a name="_toc230165068"></a><a name="_toc230170088"></a>**Required compiler, build environment**



1. ### <a name="_toc230164794"></a><a name="_toc230165069"></a><a name="_toc230170089"></a>**API definition** 

The system exposes its primary programmatic access via a single main entry-point function: 

**Function Prototype / Signature**

STAR\_END001\_CONSTELLATION\_OPTIMIZER(configFile, output\_folder)

**Input Parameters**

1. configFile
   1. *Type:* string or char array. 
   1. *Format:* Absolute or relative system file path referencing a valid, unencrypted .json configuration file. 
1. output\_folder
   1. *Type:* string or char array. 
   1. *Format:* Absolute or relative system path pointing to the destination directory where individual output files will be written. 

**Output Parameters**

- *Direct Return Values:* None (Function communicates results entirely via file-system data serialization). 

**Internal Constraints & Exceptions**

- **Array Pre-allocation:** Ground Station parameters are parsed into a pre-allocated matrix of dimensions num\_gs x 4. If an optional elevation mask field (mask) is omitted from the input JSON configuration block, the API forces an automatic fallback default value of 5 deg.
- **Optimization Dimension Bounds:** Optimization bounding vectors (lb, ub) scale dynamically based on sensor settings. In Multi-Sensor (MS) configurations, the search space expands to include an upper bound vector length sizing up to a maximum parameter capacity array dimension (nMax = 40). 

1. ### <a name="_toc230164795"></a><a name="_toc230165070"></a><a name="_toc230170090"></a>**Errors and warnings returned**

The routine incorporates deterministic runtime validations that trigger standard MATLAB execution interrupts or terminal notifications: 

- error('Configuration file %s not found.', configFile); Triggered when the system file validator returns a negative value for the provided configFile path string. Stops execution immediately. 
- error('Invalid Optimizer\_Type configuration.'); Triggered if the parameter Opt.Optimizer\_Type contains a token that is not equal to 'MOGA NSGA-II', 'PSO-based', or 'PlatEMO'. 
- error('Invalid Orbit\_Type specified in input configuration.'); Triggered if Opt.Orbit\_Type fails to match the valid system tokens: 'SSORGT', 'RGT (generally inclined)', or 'Hybrid (SSORGT and RGT)'. 
- error('Impossible to write output files: %s', filename); Triggered if the operating system file system rejects write access permissions during an execution of fopen(filename, 'w'). 
- warning(No valid solution found.'); Low-severity execution warning displayed in the Command Window if the core optimization matrices return empty arrays (isempty(x\_opt)), forcing an elegant early exit from the function without crashing the program pipeline. 

1. ### <a name="_toc230164796"></a><a name="_toc230165071"></a><a name="_toc230170091"></a>**Map of inputs/outputs**

The following matrix describes the file access maps, including specific read/write access permissions: 

|***Target File Entity***|***I/O Category***|***File Data Format***|***Description / Content Scope***|***Access Permission***|
| - | - | - | - | - |
|***configFile***|Input|Structured JSON|Comprehensive configuration parameters (Time, ROI, Ground Stations, Sensor Settings, Algorithm Iterations, Optimization Weights). |**Read-Only (**r**)**|
|***satellite\_XX.json***|Output|Standardized JSON|Individual orbital configurations, true anomaly profiles, inclination calculations, and Keplerian matrices for satellite ID XX. |**Write-Only (**w**)**|

