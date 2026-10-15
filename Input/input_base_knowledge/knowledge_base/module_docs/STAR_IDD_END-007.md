|![](Aspose.Words.daca9b4f-3c28-4d57-a190-9631b18958ec.001.png)|<p>PROGETTO: “SPACE IT UP !”</p><p>Contratto n. 2024-5-E.0. – CUP: I53D24000060005</p><p>Interface Definition Document (IDD)</p><p>END-006: SCENARIO GENERATION</p>|<p>DOCUMENT ID:</p><p>DX.X.X\_Spoke2\_XXX\_2026</p><p></p><p>DATE OF DELIVERY: XX/XX/2026</p><p></p><p>REV.: V0.1</p><p></p><p>Pag: 9 di 34</p>|
| :-: | :-: | :- |

**Interface Definition Document (IDD)**

**END-007: SYNTHETIC DATA GENERATION**

# **List of Contents**

[**1.**	**Introduction**	2](#_toc230170162)

[**1.1.**	**Functionalities description**	2](#_toc230170163)

[**1.2.**	**Use case scenarios**	2](#_toc230170164)

[**2.**	**Responsibility**	2](#_toc230170165)

[**3.**	**Applicable and reference documents**	2](#_toc230170166)

[**4.**	**Definition of terms and abbreviated terms**	3](#_toc230170167)

[**5.**	**Interface end definition**	3](#_toc230170168)

[**5.1.**	**Interface end description and data definition**	3](#_toc230170169)

[**5.2.**	**Units of measure including scale of measure**	3](#_toc230170170)

[**5.3.**	**Tolerances or required accuracies**	3](#_toc230170171)

[**5.4.**	**In case of using non-SI quantities or units, conversions and conventions**	3](#_toc230170172)

[**5.5.**	**Interface plane implementation**	3](#_toc230170173)

[**5.6.**	**Interface end behaviour**	4](#_toc230170174)

[**5.7.**	**Interface end data**	4](#_toc230170175)

[**6.**	**Special Remarks**	4](#_toc230170176)

[**7.**	**Software**	4](#_toc230170177)

[**7.1.**	**Operating system**	4](#_toc230170178)

[**7.2.**	**Operating hardware**	4](#_toc230170179)

[**7.3.**	**Required software libraries**	4](#_toc230170180)

[**7.4.**	**Required compiler, build environment**	5](#_toc230170181)

[**7.5.**	**API definition**	5](#_toc230170182)

[**7.6.**	**Errors and warnings returned**	5](#_toc230170183)

[**7.7.**	**Map of inputs/outputs**	5](#_toc230170184)


1. ## <a name="_toc230170162"></a>**Introduction**

END-007 is responsible for the generation of synthetic optical imagery from digital 3D scenarios, based on Cesium for Unreal, in Unreal version 5.5 environment. 
1. ### <a name="_toc230164775"></a><a name="_toc230165050"></a><a name="_toc230166006"></a><a name="_toc230166124"></a><a name="_toc230166211"></a><a name="_toc230166292"></a><a name="_toc230166362"></a><a name="_toc230166444"></a><a name="_toc230166529"></a><a name="_toc230170163"></a>**Functionalities description**

The module simulates the acquisition process of optical payloads by reproducing the geometry between the sensor and the observed scene according to user-defined orbital and pointing parameters. The image generation process relies on the Unreal Engine Camera Actor and its associated pinhole camera model, enabling the projection of three-dimensional scene elements onto a two-dimensional image plane. 

In addition to photorealistic optical imagery, the module can generate multiple forms of ground-truth information associated with the simulated scene. Available outputs include: 

- Instance segmentation masks;  
- Object detection labels and bounding boxes;  
- Depth maps;  
- Visibility and occlusion information;  

The simultaneous generation of imagery and ground-truth products enables the creation of fully annotated datasets suitable for computer vision, machine learning, and autonomous navigation applications.

1. ### <a name="_toc230164776"></a><a name="_toc230165051"></a><a name="_toc230166007"></a><a name="_toc230166125"></a><a name="_toc230166212"></a><a name="_toc230166293"></a><a name="_toc230166363"></a><a name="_toc230166445"></a><a name="_toc230166530"></a><a name="_toc230170164"></a>**Use case scenarios**

END-007 is intended to support a variety of activities involving the simulation of optical observations and the generation of synthetic datasets. Representative use cases are described below. 



**UC-1: EO Mission Design and Payload Assessment** 

During the design phase of an EO mission, END-007 can be used to evaluate the suitability of a candidate optical payload with respect to mission objectives.  By reproducing realistic observation conditions, including illumination effects, background characteristics, and target visibility, the tool provides additional evidence for payload selection and mission design decisions. 

**UC-2: EO Operations and Acquisition Planning** 

END-007 can support operational activities by simulating future acquisitions under predicted environmental conditions. When coupled with external information sources, such as weather forecasts or cloud coverage predictions, the simulator can estimate the expected quality and usability of planned acquisitions. The generated information can support acquisition planning, resource allocation, and data downlink prioritization activities. 

**UC-3: Synthetic Dataset Generation for Artificial Intelligence** 

END-007 can be used to generate fully annotated datasets for the development, training, and validation of machine learning algorithms. Unlike real-world datasets, which often require costly and time-consuming manual annotation procedures, the simulator automatically produces ground-truth information perfectly aligned with the generated imagery. Typical applications include object detection, semantic segmentation, and instance segmentation.  

**UC-4: IOS and Autonomous Space Operations** 

For IOS, RPO, and SSA applications, END-007 can generate synthetic image sequences representing spacecraft interactions in close proximity. The simulator enables the reproduction of relative spacecraft motion, attitude variations, illumination changes, and observation geometries relevant to vision-based navigation systems. The generated datasets can be used to develop and validate autonomous guidance, navigation, and control algorithms, including close-approach, inspection, docking, pose estimation, and visual navigation functions. The availability of precise ground-truth information allows systematic performance assessment before deployment in operational missions. 

1. ## <a name="_toc230170165"></a>**Responsibility**

Responsible for END-006:

- Alessia De Matteis (TELESPAZIO) Leader
- Mascia Bucciarelli (UNIRM1) Co-Leader

1. ## <a name="_toc230170166"></a>**Applicable and reference documents**

- STAR\_ProductTree
- STAR\_IID

1. ## <a name="_toc230170167"></a>**Definition of terms and abbreviated terms**

EO: Earth Observation 

UC: Use Case 

IOS: In-Orbit Service 

RPO: Rendez-vous and Proximity Operation 

SSA: Space Situational Awareness 

UTC: Coordinated Universal Time 

CSV: Comma Separated Values 

ECI: Earth-Centered Intertial 

1. ## <a name="_toc230170168"></a>**Interface end definition**

1. ### <a name="_toc230170169"></a>**Interface end description and data definition** 
**Customized Scenario**

Default scenario is based on Terrestrial Ellipsoid as ground map, and NASA global maps of color, roughness, clouds and normals as texture. A customised scenario can replace the default scenario through an Unreal .umap file. It can contain customized local maps, 3D targets or customized natural rendered events.

**Trajectory and pointing**

The interface plane is a file-based data exchange. END-007 shall receive a CSV file containing orbital and attitude coordinates at defined times. 

- Medium: shared folder 
- Data format: CSV file. RFC 4180 compatible, UTF-8 encoded text 
- Delimiter: comma 
- Decimal separator: dot 

File structure: 

Row 1. Header with column names: timestamp\_utc, eci\_x\_km, eci\_y\_km, eci\_z\_km, q\_w, q\_x, q\_y, q\_z, nadir\_offset\_deg 

Rows 2…N+1. Records with values separated by commas 

Empty values or NaN values are not allowed. File’s fields are described in the Table below.

![](Aspose.Words.daca9b4f-3c28-4d57-a190-9631b18958ec.002.png)




1. ### <a name="_toc230170170"></a>**Units of measure including scale of measure**

Distances are required to be in km. 

Angles are required to be in degrees

1. ### <a name="_toc230170171"></a>**Tolerances or required accuracies**



1. ### <a name="_toc230170172"></a>**In case of using non-SI quantities or units, conversions and conventions**



1. ### <a name="_toc230170173"></a>**Interface plane implementation**



1. ### <a name="_toc230170174"></a>**Interface end behaviour**



1. ### <a name="_toc230170175"></a>**Interface end data**

1. ## <a name="_toc230170176"></a>**Special Remarks**

Interfaces in STAR: 

- IF-006: SCENARIO GENERATION (END-006) – SYNTETIC DATA GENERATION (END-007) 
- IF-002: ATTITUDE PROPAGATION (END-003) – SYNTHETIC DATA GENERATION (END-007) 
- IF-005: CONSTELLATION OPTIMIZER (END-001) – SYNTHETIC DATA GENERATION (END-007) 

1. ## <a name="_toc230164789"></a><a name="_toc230165064"></a><a name="_toc230170177"></a>**Software**

1. ### <a name="ecss_e_st_10_24_1290199"></a><a name="ecss_e_st_10_24_1290200"></a><a name="_toc230164790"></a><a name="_toc230165065"></a><a name="_toc230170178"></a>**Operating system**

Recommended OS: Microsoft Windows 11 (64-bit)

Linux support may be introduced in future releases but is currently not validated.

1. ### <a name="_toc230164791"></a><a name="_toc230165066"></a><a name="_toc230170179"></a>**Operating hardware**

**General requirements:**

CPU: Multi-core x86-64

RAM: Minimum 16 GB

GPU: DirectX 12 compatible dedicated graphics card

VRAM: Minimum 4 GB

Storage: SSD recommended

Specific hardware requirements depend on scene complexity, terrain size, volumetric effects, and rendering resolution.

**Minimum Validated configuration**

CPU: Intel Core i7-12700H, 14 cores

RAM: 16 GB

GPU: NVIDIA Ge Force RTX 3050 Ti Laptop GPU, DirectX 12

VRAM: 4 GB

1. ### <a name="_toc230164792"></a><a name="_toc230165067"></a><a name="_toc230170180"></a>**Required software libraries**

Unreal Engine version 5.5 (Core simulation and visualization framework 

Cesium for Unreal (Georeferencing, coordinate transformations) 

Custom Depth Pass (Segmented data generation) 

1. ### <a name="_toc230164793"></a><a name="_toc230165068"></a><a name="_toc230170181"></a>**Required compiler, build environment**



1. ### <a name="_toc230164794"></a><a name="_toc230165069"></a><a name="_toc230170182"></a>**API definition** 

END-007 exposes a file-based interface for scenario configuration. 

Input data are provided through structured files containing: 

- Sensor configuration parameters;  
- Spacecraft position and attitude information;   

Output products are generated as image files and associated metadata, including: 

- RGB synthetic imagery;  
- Segmentation masks;  
- Bounding-box annotations;  
- Ground-truth metadata.  

Data exchange is currently performed through JSON, CSV configuration files and standard image formats (PNG, EXR, TIFF). 

No network-based API is currently implemented

1. ### <a name="_toc230164795"></a><a name="_toc230165070"></a><a name="_toc230170183"></a>**Errors and warnings returned**



1. ### <a name="_toc230164796"></a><a name="_toc230165071"></a><a name="_toc230170184"></a>**Map of inputs/outputs**

**Input**

CSV file with trajectory and pointing

Camera FOV

**Output**

Synthetic Images and associated metadata
