# Shared v2.0 contract

No signature changes. Service response exact keys scenario,result,validation,explanation,clarification. See all complete JSON and CSV examples in mocks/.

Contract delta: Scenario: Remove refinery_capacity_basis, depot_opex_usd_per_input_t, refinery_opex_usd_per_input_t, opex_status. schema_version value becomes "2.0"; updated values only in other existing fields.

Contract delta: facilities: Each facility_options/config entry adds fixed_opex_usd_per_year and variable_opex_usd_per_tonne_in. capacity_t_per_year remains named as before; always biomass intake.

Contract delta: Result: flows adds mode="truck"|"barge". costs adds fixed_opex_usd_per_year and variable_opex_usd_per_year; existing opex_usd_per_year is their sum. Optional truck_trips excludes barge edges.

Preserved exactly: All 10 function signatures, Service keys, Validation/Patch structures, existing Result fields, module names and ownership. No renamed fields. No other signature or field changes.