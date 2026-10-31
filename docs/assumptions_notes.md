# Organiser parameters and team assumptions

Source: data/raw/challenge3_parameters.xlsx and organiser_updates.pdf p2.

Start time: 13:20 Singapore time on 31 October 2026; first-valid target 14:20.

Candidate sites: 80 depot sites at supplied sources; eight refinery sites, two nearest unselected sources per airport in PNK/PKN/BPN/TRK order. Haversine distance, source_id tie-break. Team assumption: source coordinates are eligible land; verify before deployment.

Facility stacking: At most one size per candidate per type. Depot/refinery co-location permitted. Finite candidate set, not continuous land optimisation.

Barge distance: Apply great-circle x 1.3 to TRK too. Entire refinery-TRK link is modelled as barge; no ports, transfer fees or fixed barge cost.

Flow operations: Annual continuous tonnes, exact demand, unused supply allowed; no inventory, lead times, minimum loads, road capacity or upstream biomass purchase cost.

Submission rules: First valid matters. Target 14:20, retain confirmation. Confirm required submission fields and whether later resubmission is allowed; 16:15 is the hard close.