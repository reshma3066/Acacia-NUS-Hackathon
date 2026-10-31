# v1.1 -> v2.0

Fixed parameters: Yield .20; 300 kt per airport; input capacity only; distance x1.3; one year; CapEx/20; fixed OpEx .05 CapEx; variable OpEx by facility size. Old yield citation and capacity sensitivity removed.

Network & baseline: Candidate MILP is MVP. Eight distinct refinery candidates retained. Baseline becomes 80 small depots + 8 large refineries; optimise its flows only.

Scenarios & evidence: Base 1,200 kt; BPN+20% 1,260 kt; all+15% 1,380 kt infeasible. New computed MILP/baseline evidence, fixtures, map and prototype.

Team & schedule: Owners and boundaries retained. Start 13:20, interface check 13:40, first-valid target 14:20. Sarah integrates from 13:30. Pitch: Shaza, Syakir, Reshma; Sarah drives UI silently.

Contract delta: Scenario: Remove refinery_capacity_basis, depot_opex_usd_per_input_t, refinery_opex_usd_per_input_t, opex_status. schema_version value becomes "2.0"; updated values only in other existing fields.

Contract delta: facilities: Each facility_options/config entry adds fixed_opex_usd_per_year and variable_opex_usd_per_tonne_in. capacity_t_per_year remains named as before; always biomass intake.

Contract delta: Result: flows adds mode="truck"|"barge". costs adds fixed_opex_usd_per_year and variable_opex_usd_per_year; existing opex_usd_per_year is their sum. Optional truck_trips excludes barge edges.

Preserved exactly: All 10 function signatures, Service keys, Validation/Patch structures, existing Result fields, module names and ownership. No renamed fields. No other signature or field changes.