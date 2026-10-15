# Earth Observation Mission Design

## Purpose

Acquisition planning defines when, where and under which geometric conditions a spaceborne sensor can observe a target. Observation geometry describes the relative configuration between spacecraft, sensor, target, Sun and Earth at the time of acquisition.

This knowledge is relevant when a mission request involves monitoring, imaging, repeated observations, target access, acquisition opportunities, observation windows, pointing constraints or sensor viewing conditions.

## Key design questions

A preliminary acquisition planning activity should clarify:

what target or area of interest must be observed;
whether the target is a point, polygon, region or distributed class of targets;
how often observations are required;
whether observations must occur at specific times;
what sensor type is assumed;
what viewing geometry is acceptable;
whether nadir or off-nadir observations are allowed;
whether daylight, illumination, local time or cloud constraints are relevant;
whether the acquisition plan must support downstream simulation, power analysis or data volume estimation.

## Typical mission-level quantities

cquisition planning may produce:

access windows;
acquisition opportunity list;
observation timeline;
viewing geometry metadata;
target visibility intervals;
acquisition constraints;
preliminary tasking plan;
observation cadence estimate;
geometry inputs for image simulation;
operation timeline inputs for feasibility analysis.

## Reasoning guidance

If the requirements mention monitoring frequency, access windows, observation cadence or revisit, acquisition planning is likely needed.

If the requirements mention image generation or simulated observations, acquisition geometry is likely needed.

If the mission request only states a target name, the exact geographic definition should be treated as missing information.

If acquisition planning produces a timeline, that timeline may be useful for downstream analyses such as power, data volume, operations or synthetic data generation.

## Preliminary assumptions

At early design stage, assumptions may be introduced for missing quantities, but they should be explicitly marked as first guesses and reviewed by the user.