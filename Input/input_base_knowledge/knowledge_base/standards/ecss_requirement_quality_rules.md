# ECSS-E-ST-10-06C Requirement Quality Rules for STAR

This file is an operational checklist derived from ECSS-E-ST-10-06C, *Space engineering — Technical requirements specification*, 6 March 2009. It is used by STAR as compact prompt context for requirement extraction.

## Requirement scope

- Extract technical requirements only.
- Do not extract general descriptive background, motivation, justification or explanatory text as a requirement.
- A technical requirement shall express a need, constraint, environmental condition, operational feature, performance feature, interface, configuration, design constraint, physical boundary condition, product assurance need, or verification need.
- Cost, payment methods, procurement quantities, time or place of delivery shall not be treated as ordinary technical requirements. Treat them as programmatic context unless explicitly requested as a technical design constraint.

## Requirement types

Use the following ECSS-compatible categories:

- functional: what the product or system shall perform.
- mission: task, function, constraint or action induced by the mission scenario.
- interface: relationship or interconnection between the product and another item or system.
- environmental: natural or induced environment during the life cycle.
- operational: operability, operational profile, modes, control, autonomy or contingency.
- human factor: adaptation to human capabilities, perception, workload or display.
- physical: physical compatibility, dimensions, mass, aperture, physical boundary conditions.
- product assurance: reliability, availability, maintainability, safety or quality assurance.
- configuration: product composition, architecture or organized elements.
- design: imposed design solution, construction standard, component, material or technology.
- verification: imposed verification method, test, analysis, inspection or demonstration.

## Quality characteristics

Each technical requirement should be:

- separately stated;
- quantifiable when it expresses performance;
- justified;
- configuration-managed;
- backward-traceable and forward-traceable;
- unambiguous;
- unique;
- identifiable by a unique identifier;
- singular, meaning it does not combine two or more requirements;
- self-contained;
- verifiable by known verification means;
- provided with tolerances when a parameter or variable is specified.

## Wording rules

- Use the verbal form "shall" for requirements.
- Use "should" only for recommendations.
- Use "may" only for permissions.
- Use "can" only for possibility or capability.
- State requirements as positive, complete sentences with a verb and a noun.
- State what is necessary, not how to perform a task, unless the exact implementation is essential or explicitly imposed.
- Preserve numerical values and units when explicitly present.
- Do not invent numerical values, units, tolerances or verification methods.

## Terms to avoid in technical requirements

Avoid the following ambiguous or weak terms:

- and/or
- etc.
- goal
- shall be included but not limited to
- relevant
- necessary
- appropriate
- as far as possible
- optimize
- minimize
- maximize
- typical
- rapid
- user-friendly
- easy
- sufficient
- enough
- suitable
- satisfactory
- adequate
- quick
- first rate
- best possible
- great
- small
- large
- state of the art

If the mission request uses these terms and no quantitative acceptance criterion is provided, set status to `under_specified` or `requires_review`.


## STAR extraction refinements - v2

The requirement extractor shall not perform sentence-by-sentence conversion from mission proposal prose to "shall" statements. It shall first identify technical needs, discard pure narrative or programmatic context, and then formulate concise technical requirements.

Additional operational rules:

- Do not copy long mission proposal phrases into requirement text except proper nouns, named configurations, declared interfaces, numerical values and units.
- Do not extract budget allocation, procurement cost, launch service cost, payment information, delivery location, or financial framework as a technical requirement.
- Use a specific subject when available, for example "The IRIS-IT constellation", "The spacecraft", "The optical payload", or "The ground segment".
- Remove weak terms such as high-rate, high-resolution, high-stability, comprehensive, efficient and optimized unless a measurable acceptance criterion is also present.
- Group detailed operational narrative into a smaller number of verifiable operational or interface requirements.
- Group astronomy-impact statements into one environmental requirement unless separate measurable requirements are explicitly imposed.
- Limit extraction to the high-level technical requirements needed for preliminary STAR mission analysis.
