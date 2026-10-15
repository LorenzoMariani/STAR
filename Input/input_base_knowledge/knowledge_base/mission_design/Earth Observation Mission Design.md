# Earth Observation Mission Design

## Purpose

Earth Observation missions aim to acquire measurements or images of the Earth surface, atmosphere, oceans, or human-made infrastructure in order to produce information products for monitoring, detection, mapping, forecasting, or decision support.

## Key design questions

A preliminary EO mission analysis should clarify:
- what physical phenomenon or target must be observed;
- where the observation must be performed;
- how often the target must be observed;
- which spatial, spectral, temporal or radiometric information is required;
- whether the final product is an image, a map, a time series, an alert, a dataset, or a performance indicator;
- whether the mission requires real acquisition planning, simulated observations, or both.

## Typical mission-level quantities

Relevant quantities may include:
- area of interest;
- target coordinates or target region;
- spatial resolution;
- revisit time;
- coverage;
- acquisition frequency;
- observation geometry;
- payload type;
- illumination constraints;
- environmental constraints;
- data product type.

## Reasoning guidance

A requirement asking for monitoring usually implies repeated observations over time.

A requirement asking for frequent revisit usually implies analysis of access opportunities, orbit geometry, sensor field of regard and target latitude.

A requirement asking for images usually implies payload and acquisition geometry assumptions.

A requirement asking for synthetic images implies both a representation of the observed scene and a model of the observation process.

## Preliminary assumptions

At early design stage, assumptions may be introduced for missing quantities, but they should be explicitly marked as first guesses and reviewed by the user.