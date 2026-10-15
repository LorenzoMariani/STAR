|![](Aspose.Words.a0eaa821-31c4-4a1c-9a1c-d0c641afc9cd.001.png)|<p>PROGETTO: “SPACE IT UP !”</p><p>Contratto n. 2024-5-E.0. – CUP: I53D24000060005</p><p>Interface Definition Document (IDD)</p><p>END-003: ATTITUDE PROPAGATION</p>|<p>DOCUMENT ID:</p><p>DX.X.X\_Spoke2\_XXX\_2026</p><p></p><p>DATE OF DELIVERY: XX/XX/2026</p><p></p><p>REV.: V0.1</p><p></p><p>Pag: 9 di 34</p>|
| :-: | :-: | :- |

**Interface Definition Document (IDD)**

**END-003: ATTITUDE PROPAGATION**

# **List of Contents**

[**1.**	**Introduction**	2](#_toc230170026)

[**1.1.**	**Functionalities description**	2](#_toc230170027)

[**1.2.**	**Use case scenarios**	2](#_toc230170028)

[**2.**	**Responsibility**	2](#_toc230170029)

[**3.**	**Applicable and reference documents**	2](#_toc230170030)

[**4.**	**Definition of terms and abbreviated terms**	3](#_toc230170031)

[**5.**	**Interface end definition**	3](#_toc230170032)

[**5.1.**	**Interface end description and data definition**	3](#_toc230170033)

[**5.2.**	**Units of measure including scale of measure**	3](#_toc230170034)

[**5.3.**	**Tolerances or required accuracies**	3](#_toc230170035)

[**5.4.**	**In case of using non-SI quantities or units, conversions and conventions**	3](#_toc230170036)

[**5.5.**	**Interface plane implementation**	3](#_toc230170037)

[**5.6.**	**Interface end behaviour**	4](#_toc230170038)

[**5.7.**	**Interface end data**	4](#_toc230170039)

[**6.**	**Special Remarks**	4](#_toc230170040)

[**7.**	**Software**	4](#_toc230170041)

[**7.1.**	**Operating system**	4](#_toc230170042)

[**7.2.**	**Operating hardware**	4](#_toc230170043)

[**7.3.**	**Required software libraries**	4](#_toc230170044)

[**7.4.**	**Required compiler, build environment**	5](#_toc230170045)

[**7.5.**	**API definition**	5](#_toc230170046)

[**7.6.**	**Errors and warnings returned**	5](#_toc230170047)

[**7.7.**	**Map of inputs/outputs**	5](#_toc230170048)


1. ## <a name="_toc230170026"></a>**Introduction**

This Interface Design Document (IDD) defines the architectural specifications, data structures, and operational protocols governing the interface IF-001 between the ATTITUDE PROPAGATOR (END-003) module and the SYNTHETIC DATA GENERATION (END-007) module.

The primary objective of this document is to formalize the data exchange mechanisms and underlying physical conventions used to export time-series orbital kinematics and spacecraft attitude state profiles during ground station visibility windows. This data exchange provides the downstream module (END-007) with the geometric and telemetry inputs required to synthesize high-fidelity remote sensing and payload telemetry datasets.

1. ### <a name="_toc230164775"></a><a name="_toc230165050"></a><a name="_toc230166006"></a><a name="_toc230166124"></a><a name="_toc230166211"></a><a name="_toc230166292"></a><a name="_toc230166362"></a><a name="_toc230166444"></a><a name="_toc230166529"></a><a name="_toc230166588"></a><a name="_toc230166646"></a><a name="_toc230166695"></a><a name="_toc230170027"></a>**Functionalities description**

The underlying core software handles the simultaneous numerical propagation of the spacecraft's orbital path and its rotational kinematics. The main technical functionalities comprise:

- **Orbital Propagation:** Numerical integration of the Earth-centered orbital state via a variable-step Adams-Bashforth-Moulton solver (ode113), accounting for non-spherical gravitational perturbations up to the third zonal harmonic (J2 and J3).
- **Attitude Kinematics & Dynamics:** Implementation of a three-tier operational configuration framework:
  - dynamics: Solves Euler's rotational equations of motion coupled with quaternion kinematics. It accounts for environmental disturbance torques including Gravity Gradient (GG), Solar Radiation Pressure (SRP) with cylindrical Earth shadow transitions, and Aerodynamic Drag based on the NRLMSISE-00 atmospheric model.
  - nadir: Enforces a deterministic, ideal geometric alignment where the spacecraft's boresight matches the geocentric nadir vector.
  - follow\_site: Operates in nominal Nadir pointing mode, executing an automated rotational maneuver toward a targeted ground coordinate (Target Tracking) whenever the topocentric elevation angle exceeds a defined threshold.
- **Visibility Filtering:** Evaluates topocentric elevation profiles relative to the Ground Station. The module isolates continuous tracking windows exceeding the elevation threshold and filters the data to export only the pass containing the absolute maximum elevation peak.

1. ### <a name="_toc230164776"></a><a name="_toc230165051"></a><a name="_toc230166007"></a><a name="_toc230166125"></a><a name="_toc230166212"></a><a name="_toc230166293"></a><a name="_toc230166363"></a><a name="_toc230166445"></a><a name="_toc230166530"></a><a name="_toc230166589"></a><a name="_toc230166647"></a><a name="_toc230166696"></a><a name="_toc230170028"></a>**Use case scenarios**

- **Scenario A - Observation Planning:** This software utility can be used to simulate directed spaceborne observation campaigns where high-accuracy relative geometry between a spacecraft and a ground asset is required. By computing the exact inertial trajectory and matching orientation states during periods of optimal topocentric visibility, the interface delivers highly specialized datasets to downstream simulation toolchains. Analysts can utilize these outputs to synthesize high-fidelity payload data, such as optical remote sensing imagery, synthetic aperture radar (SAR) returns, or directional communication links, accounting for the exact time-varying line-of-sight vector. This scenario is critical for evaluating target-revisit capabilities, planning payload duty cycles, and validating data processing algorithms prior to hardware deployment.
- **Scenario B: Impact Assessment of Environmental Perturbations on Mission Products** The core architecture serves as an analytical environment to evaluate how non-spherical gravitational harmonics, atmospheric drag variations, and solar radiation pressure affect platform stability and subsequent payload data quality. By propagating the unmitigated attitude drift of a spacecraft subjected to real-world space environmental torques, the interface records the precise pointing errors and angular deviations from the nominal target alignment. Downstream synthetic data generators can ingest these corrupted attitude states to perform sensitivity analyses, quantifying exactly how environmental disturbances degrade image resolution, cause geometric distortions, or introduce noise into remote sensing datasets. This enables system engineers to define strict pointing-budget requirements for the vehicle's stabilization systems.

1. ## <a name="_toc230170029"></a>**Responsibility**

Responsible for END-003:

- Lorenzo Mariani (UNIRM1) Leader
- Fabrizio Piergentili (UNIRM1) Co-Leader

1. ## <a name="_toc230170030"></a>**Applicable and reference documents**

- STAR\_ProductTree

1. ## <a name="_toc230170031"></a>**Definition of terms and abbreviated terms**

|**Acronym**|**Definition**|
| :- | :- |
|***API***|Application Programming Interface|
|***COE***|Classical Orbital Elements|
|***CSV***|Comma-Separated Values|
|***ECEF***|Earth-Centered, Earth-Fixed Rotational Frame|
|***ECI***|Earth-Centered Inertial Frame|
|***GG***|Gravity Gradient|
|***GMST***|Greenwich Mean Sidereal Time|
|***GS***|Ground Station|
|***HEO***|Highly Elliptical Orbit|
|***IDD***|Interface Design Document|
|***SI***|International System of Units|
|***SRP***|Solar Radiation Pressure|

1. ## <a name="_toc230170032"></a>**Interface end definition**

1. ### <a name="_toc230170033"></a>**Interface end description and data definition** 

The structural implementation of interface IF-001 is a file-based data exchange using a standardized flat text schema (CSV format), designated as gs\_pass.csv. The interface file contains a singular header row defining the structural fields, followed by N chronologically sorted data vectors sampled natively at the integration steps generated during the selected tracking pass.

|**Column Identifier**|**Data Type**|**Physical Description**|
| :- | :- | :- |
|***timestamp\_utc***|String (ISO 8601)|Coordinated Universal Time stamp in YYYY-MM-DDTHH:MM:SSZ format|
|***eci\_x\_km***|Float|X-component of the spacecraft position vector in the ECI frame [km]|
|***eci\_y\_km***|Float|Y-component of the spacecraft position vector in the ECI frame [km]|
|***eci\_z\_km***|Float|Z-component of the spacecraft position vector in the ECI frame [km]|
|***q\_w***|Float|Scalar component (q0) of the ECI-to-Body orientation quaternion|
|***q\_x***|Float|Vector X-component (q1) of the ECI-to-Body orientation quaternion|
|***q\_y***|Float|Vector Y-component (q2) of the ECI-to-Body orientation quaternion|
|***q\_z***|Float|Vector Z-component (q3) of the ECI-to-Body orientation quaternion|
|***nadir\_offset\_deg***|Float|Angular pointing boresight deviation relative to true geocentric nadir [deg]|

1. ### <a name="_toc230170034"></a>**Units of measure including scale of measure**

- **Temporal Domain:** Standard UTC with single-second structural resolution.
- **Spatial Trajectory:** Kilometers [km]. The internal representation in meters is scaled by 10^-3 prior to file-writing operations.
- **Attitude State:** Dimensionless, unitary norm constraint enforced via algebraic normalization (qw2+qx2+qy2+qz2=1).
- **Angular Metrics:** Sexagesimal decimal degrees [deg].

1. ### <a name="_toc230170035"></a>**Tolerances or required accuracies**

**Numerical Integration Precision:** Governed by the ode113 solver properties configured with a relative tolerance RelTol = 1e-12 and absolute tolerance AbsTol = 1e-15.

**Export Quantization Layout:** \* Position coordinates: 3 decimal places (1-meter structural quantization).

- Attitude quaternions: 4 decimal places.
- Pointing offset: 2 decimal places.

1. ### <a name="_toc230170036"></a>**In case of using non-SI quantities or units, conversions and conventions**

- Kinematic Positioning: Conversion from SI meters to kilometers is applied via: rk=rmtr1000
- Rotational Space: Conversion from native algorithmic radians to output degrees is governed by the scaling factor 180/π.
- Quaternion Core Convention: The interface uses the scalar-first convention layout: q=qwqxqyqzT
- This vector represents the passive rotation mapping coordinates from the inertial ECI frame to the rotating spacecraft Body frame.


1. ### <a name="_toc230170037"></a>**Interface plane implementation**

The interface is deployed at the File System Level. The END-001 module handles the generation, formatting, and disk storage of the CSV file. The END-007 module retains read-only privileges, executing consumer parsing algorithms sequentially upon termination of the upstream propagation.

1. ### <a name="_toc230170038"></a>**Interface end behaviour**

- Upon execution, END-001 computes the full trajectory envelope and evaluates topocentric elevation histories against the target ground station.
- An edge-detection algorithm parses continuous visibility segments exceeding the elevation threshold (10 deg). If multiple passes occur over the 48-hour simulation envelope, it isolates the sequence containing the absolute highest elevation apex.
- The module opens a synchronous file descriptor (fopen), locks execution, writes the formatting streams iteratively, and releases the descriptor handle (fclose).

1. ### <a name="_toc230170039"></a>**Interface end data**

Below is a syntax-compliant structural record sample from genova\_pass.csv:

timestamp\_utc,eci\_x\_km,eci\_y\_km,eci\_z\_km,q\_w,q\_x,q\_y,q\_z,nadir\_offset\_deg

2024-06-21T14:23:10Z,12450.321,-32104.556,15420.112,0.7071,0.0000,0.7071,0.0000,0.15

2024-06-21T14:23:15Z,12452.114,-32101.201,15424.394,0.7065,0.0012,0.7075,0.0021,0.18

1. ## <a name="_toc230170040"></a>**Special Remarks**

Interfaces in STAR:

- IF-002: ATTITUDE PROPAGATION (END-003) – SYNTHETIC DATA GENERATION (END-007)
- IF-003: ATTITUDE PROPAGATION (END-003) – ATTITUDE VISUALIZATION (END-004)

1. ## <a name="_toc230164789"></a><a name="_toc230165064"></a><a name="_toc230170041"></a>**Software**

1. ### <a name="ecss_e_st_10_24_1290199"></a><a name="ecss_e_st_10_24_1290200"></a><a name="_toc230164790"></a><a name="_toc230165065"></a><a name="_toc230170042"></a>**Operating system**

The software execution layer is cross-platform and OS-agnostic due to the abstract nature of the underlying MATLAB runtime environment. It is fully supported across Windows 10/11, Linux Ubuntu 20.04 LTS (or higher), and macOS.

1. ### <a name="_toc230164791"></a><a name="_toc230165066"></a><a name="_toc230170043"></a>**Operating hardware**

- **Processor Architecture:** x86-64 or Apple Silicon architecture (Minimum: 4 physical cores).
- **Volatile Memory (RAM):** 8 GB minimum requirement. This memory allocation is required to handle high-dimensional interpolation structures (griddedInterpolant) generated during long-duration runs.
- **Disk Space Allocation:** Minimal footprint required (< 10 MB for local text telemetry logs).

1. ### <a name="_toc230164792"></a><a name="_toc230165067"></a><a name="_toc230170044"></a>**Required software libraries**

- **Execution Core:** MATLAB Environments (Release R2021a or newer).
- **Subsystem Dependencies:** *Aerospace Toolbox* (utilized for internal transformations and empirical database evaluations: ecef2lla, atmosnrlmsise00, igrfmagm). If this toolbox is absent, the architecture switches to analytic fallback algorithms (e.g., standard dipole magnetic assumptions above 600 km).

1. ### <a name="_toc230164793"></a><a name="_toc230165068"></a><a name="_toc230170045"></a>**Required compiler, build environment**

No external C/C++ compilation suites or toolchains are required. The module operates natively as an interpreted execution routine within the MATLAB Command Window environment or via Automated headless runners.

1. ### <a name="_toc230164794"></a><a name="_toc230165069"></a><a name="_toc230170046"></a>**API definition** 

- **Input Parameters:**
  - json\_filepath (String): The absolute or relative system path pointing to the input file (conventionally input\_attitude\_propagator.json). This file contains the serialized orbital elements, satellite mass properties, inertia tensors ($I\_x, I\_y, I\_z$), environmental flags, and ground target coordinates.
  - output\_dir (String, Optional): The designated target folder where verification plots and data logs are saved. If omitted, it defaults to 'simulation\_outputs'.
- **Output Artifacts:**
  - Procedural generation of gs\_pass.csv alongside six validation telemetry figures.
- **Exceptions & Constraints:**
  - If the file path specified in json\_filepath does not exist on the host system, the function terminates execution abruptly and throws a fatal runtime error: File JSON not found: <filepath>.

1. ### <a name="_toc230164795"></a><a name="_toc230165070"></a><a name="_toc230170047"></a>**Errors and warnings returned**

"Warning: No passage found over %d deg threshold. Export entire simulation."

Root Cause: The defined orbital parameters parsed from the JSON configuration do not intersect the topocentric visibility cone of the designated ground station within the simulated timeline window.

Mitigation Strategy: To maintain the integrity of the downstream toolchain and prevent execution halts inside END-007, the error handler catches the null pointer exception, overrides the filtering window, and automatically writes the full orbital trajectory dataset to `gs\_pass.csv` while logging the telemetry warning directly to the standard output console.

1. ### <a name="_toc230164796"></a><a name="_toc230165071"></a><a name="_toc230170048"></a>**Map of inputs/outputs**

Input Data Map (Ingested via JSON Serialization structure `cfg`):

- cfg.sim\_start\_date / cfg.sim\_hours: Temporal baseline
- cfg.sat (attitude\_mode, q0, w0, m, A\_ref, Cr, Cd, r\_cp, Ix, Iy, Iz): Spacecraft physical & initial conditions
- cfg.orbit (alt\_perigee\_m, alt\_apogee\_m, inclination\_deg, raan\_deg, omega\_deg, nu\_deg): Keplerian initial conditions 
- cfg.target (site\_lat\_deg, site\_lon\_deg, elev\_threshold): Topocentric station target coordinates
- cfg.env.flags: Perturbations state array (`gg`, `srp`, `drag`, `pert`, `j2`, `j3`)

Output Data Map (Generated Artifacts):

- gs\_pass.csv: Filtered state telemetry exported to disk 
- 01\_telemetry.png: Core angular kinematics, torques, and altitude histories 
- 02\_tracking.png: Elevation profiles and pointing error matrices 
- 03\_angular\_momentum.png: Spacecraft angular momentum modulus and direction in ECI
- 04\_ground\_track.png: 2D geographic projection mapping complete and active-pass arcs 
- 05\_orbit\_3d\_ecef.png: 3D orbital trajectory representation in the Earth-Centered Earth-Fixed rotating frame 
- 06\_orbit\_3d\_eci.png: 3D orbital trajectory representation in the Earth-Centered Inertial frame 
