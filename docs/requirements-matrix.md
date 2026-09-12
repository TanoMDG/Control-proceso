# Requirements Matrix

Source: `Especificacion_Tecnica_Consolidada_v1_4_FINAL.docx`, v1.4 FINAL, section 14 (`CP01`-`CP70`), audited against `release/v1.0.0` on 2026-09-12.

## Status Legend

| Status | Meaning |
|---|---|
| `IMPLEMENTED` | The exact acceptance criterion has executable evidence at the applicable layer. Backend evidence is used for server-enforced, calculation, persistence, and nonvisual rules; Docker Playwright evidence is used for the listed browser journeys. |
| `PENDING ACCEPTANCE` | Code may exist, but the exact criterion lacks sufficient focused acceptance evidence. The reason is individual to the CP. |
| `PENDING EXTERNAL` | Requires an authorized external plant/service dependency not available in this release environment. |
| `PENDING F8/F9` | Assigned to an unimplemented F8 or F9 scope. |

No CP01-CP70 item is assigned to F8 or F9 by section 14. F6 commissioning is external to these CPs and remains outside this matrix. CP50 is implemented as a tested negative architectural rule.

## CP01-CP35

| CP | Status | Exact acceptance criterion | Evidence test ID/name or individual pending reason |
|---|---|---|---|
| CP01 | IMPLEMENTED | Verdés humidity 4.1% warns, opens D01, and permits saving/closing. | `tests/test_f1_operations.py::test_m1_limits_deviations_consecutivity_and_lifecycle` |
| CP02 | IMPLEMENTED | Verdés humidity 2.8% saves without warning/event. | `tests/test_f1_operations.py::test_in_range_measurement_resets_consecutive_deviation_sequence` |
| CP03 | PENDING ACCEPTANCE | Box 4 cannot be selected for consumption; only 1, 2, 3, 6. | No focused invalid-box request asserts rejection. |
| CP04 | PENDING ACCEPTANCE | Burner-temperature change requires prior value, new value, and reason. | No focused correction test covers the three required burner fields. |
| CP05 | IMPLEMENTED | Calculate 250 L/t from 30 t/h and 7,500 L/h; reference ~237 only, no automatic event. | `tests/test_f1_operations.py::test_m2_dosage_and_stoppage_rules` |
| CP06 | PENDING ACCEPTANCE | Lecho temperature 330 C saves with warning and D10 if configured; no supervisor override. | The 330 C request is accepted, but no test asserts D10/warning and override behavior. |
| CP07 | PENDING ACCEPTANCE | Silo stock calculated as 18 t warns and opens D16 without blocking. | Tonnes below 20 are calculated, but no test asserts D16/warning creation. |
| CP08 | IMPLEMENTED | Line 6 offers silos 9-16 only. | `tests/test_f1_operations.py::test_m3_lecho_ksider_silos_and_physical_mapping` |
| CP09 | IMPLEMENTED | MUA registration creates `MUA-AAAA-MMDD-NN`, records preparer, and is available for loading. | `tests/test_f4_traceability.py::test_m4_identity_composition_and_m5_existing_mua_only`; `apps/web/e2e/roles.spec.ts::M4, M5, M7, and M17 use persisted test masters` |
| CP10 | IMPLEMENTED | Loading cannot use an MUA that was not created. | `tests/test_f4_traceability.py::test_m4_identity_composition_and_m5_existing_mua_only` |
| CP11 | IMPLEMENTED | Show MUA in each box, since when, and FIFO consumption suggestion. | `tests/test_f4_traceability.py::test_m4_identity_composition_and_m5_existing_mua_only` |
| CP12 | IMPLEMENTED | P12 stoppage requires description; other causes do not. | `tests/test_f1_operations.py::test_m2_dosage_and_stoppage_rules` |
| CP13 | IMPLEMENTED | Four-hour stoppage calculates duration, reduces availability, and appears in Pareto. | `tests/test_f2_analytics.py::test_rebuilds_facts_and_serves_kpi_without_operational_queries` |
| CP14 | PENDING ACCEPTANCE | Hopper emptying prompts ~10-minute discard and associated stoppage. | The reminder is tested, but the associated-stoppage acceptance behavior is not. |
| CP15 | IMPLEMENTED | Pressing pressure 200 kg/cm2 warns and opens D19. | `tests/test_f3_prensas.py::test_m8_m9_validate_press_line_and_pressure_deviation` |
| CP16 | IMPLEMENTED | 64x64 thickness flags only 7.45 mm, computes min/max/range, and 0.25 mm does not open dispersion event. | `tests/test_f3_prensas.py::test_m10_requires_full_grids_uses_format_tolerance_and_does_not_invent_dispersion_event` |
| CP17 | IMPLEMENTED | The same values validate differently for 64x122. | `tests/test_f3_prensas.py::test_m10_requires_full_grids_uses_format_tolerance_and_does_not_invent_dispersion_event` |
| CP18 | IMPLEMENTED | Changing Verdés-humidity limit preserves an old record's original evaluation. | `tests/test_cp_acceptance.py::test_cp45_applied_limit_version_and_historical_kpi_are_preserved` |
| CP19 | IMPLEMENTED | Deviation cannot close without verification; close needs SUPERVISION/ADMIN and comment. | `tests/test_f1_operations.py::test_m1_limits_deviations_consecutivity_and_lifecycle`; `apps/web/e2e/roles.spec.ts::supervision persists deviation lifecycle, correction audit, conflict, and dashboard data` |
| CP20 | IMPLEMENTED | Deferred entry retains paper date/20-4 shift; KPI uses it; log retains typist/time. | `tests/test_ft_paper_transition.py::test_paper_entry_preserves_operational_moment_and_is_idempotent` |
| CP21 | IMPLEMENTED | Press operator cannot access other-sector/global history; own sector/current plus 7 days; only own drafts editable. | `tests/test_cp_acceptance.py::test_cp21_cp44_cp62_backend_scope_and_own_draft_only` |
| CP22 | IMPLEMENTED | Supervisor correction of closed record requires reason and preserves old/new/user/date. | `tests/test_cp_acceptance.py::test_cp22_closed_correction_audit_exposes_old_new_user_and_timestamp`; `apps/web/e2e/roles.spec.ts::supervision persists deviation lifecycle, correction audit, conflict, and dashboard data` |
| CP23 | IMPLEMENTED | Remote-read profile sees dashboard only, no create/edit/validate views. | `tests/test_authorization_regressions.py::test_cp23_remote_is_limited_to_exact_dashboard_endpoint`; `apps/web/e2e/roles.spec.ts::real credentials expose role and remote navigation boundaries` |
| CP24 | PENDING ACCEPTANCE | Deactivated palero is absent from new lists but remains in historical record. | No focused person deactivation/history-retention acceptance test. |
| CP25 | IMPLEMENTED | Offline records sync without duplication via `client_uuid`; time/sector/shift match is warning only. | `apps/web/e2e/roles.spec.ts::offline IndexedDB survives reload, reconnects, and retries idempotently`; `tests/test_ft_paper_transition.py::test_paper_entry_preserves_operational_moment_and_is_idempotent` |
| CP26 | PENDING ACCEPTANCE | Dashboard totals agree with manual calculation. | Rebuild calculation is tested, but there is no independently stated manual-total oracle. |
| CP27 | IMPLEMENTED | Blank forms print A4 landscape with repeated header; thickness form has three press pages. | `tests/test_ft_paper_transition.py::test_printable_forms_have_repeated_header_and_thickness_pages` |
| CP28 | IMPLEMENTED | Records may only be voided with reason; audit log cannot be deleted. | `tests/test_cp_acceptance.py::test_cp28_void_requires_reason_prevents_physical_delete_and_keeps_immutable_audit` |
| CP29 | IMPLEMENTED | Laboratory cannot create MUA; SUPERVISION/ADMIN can. | `tests/test_f4_traceability.py::test_mua_creation_requires_supervision_and_boxes_can_hold_two_muas` |
| CP30 | IMPLEMENTED | Two MUA may coexist in a box without invented tonnage/percentages. | `tests/test_f4_traceability.py::test_mua_creation_requires_supervision_and_boxes_can_hold_two_muas` |
| CP31 | IMPLEMENTED | Activating a second box to Verdés closes the prior active period. | `tests/test_f4_traceability.py::test_temporal_handoffs_mapping_and_certainty_trace` |
| CP32 | IMPLEMENTED | Changing K-Sider receiver closes prior receiver and opens new timestamped/user period. | `tests/test_f4_traceability.py::test_temporal_handoffs_mapping_and_certainty_trace` |
| CP33 | PENDING ACCEPTANCE | Two silos may concurrently feed Line 7. | No focused concurrent-two-silo acceptance test. |
| CP34 | IMPLEMENTED | Silo 1 cannot be associated with Line 6. | `tests/test_f4_traceability.py::test_temporal_handoffs_mapping_and_certainty_trace` |
| CP35 | IMPLEMENTED | PH Siti/Line 7 and PH5000/Line 6 combinations are rejected. | `tests/test_f3_prensas.py::test_m8_m9_validate_press_line_and_pressure_deviation` |

## CP36-CP70

| CP | Status | Exact acceptance criterion | Evidence test ID/name or individual pending reason |
|---|---|---|---|
| CP36 | PENDING ACCEPTANCE | Changing Line 7 product/format closes prior period; both PH5000 presses inherit line state. | Initial line state is tested; replacement closure and both-press inheritance are not. |
| CP37 | PENDING ACCEPTANCE | Shift change does not close open stoppage/continuous states; incoming operator confirms reception. | No focused shift-receipt and state-continuity acceptance test. |
| CP38 | IMPLEMENTED | Second consecutive out-of-range measurement for the same variable/point escalates; in-range resets sequence. | `tests/test_f1_operations.py::test_m1_limits_deviations_consecutivity_and_lifecycle`; `tests/test_f1_operations.py::test_in_range_measurement_resets_consecutive_deviation_sequence` |
| CP39 | IMPLEMENTED | Correcting source to valid changes event to INVALIDADO; event remains excluded from real-deviation KPI. | `tests/test_f1_operations.py::test_invalidated_deviation_is_visible_but_excluded_from_real_kpi` |
| CP40 | PENDING ACCEPTANCE | Overlapping future limit version is rejected; future version can be changed/cancelled with audit. | Overlap rejection is tested; future edit, cancellation, and audit are not covered together. |
| CP41 | IMPLEMENTED | Laboratory granulometry stores one configured-mesh determination; no invented meshes. | `tests/test_f7_laboratory.py::test_f7_configurable_analysis_sieves_limits_agenda_and_compliance`; `tests/test_f7_laboratory.py::test_f7_rejects_unconfigured_sieve_and_non_lab_carga` |
| CP42 | PENDING ACCEPTANCE | Missing expected lab analysis reduces compliance only; no fictitious record/deviation. | Agenda counts expected/performed work, but absence-no-event is not asserted directly. |
| CP43 | IMPLEMENTED | Late sync cannot overwrite CERRADO record; it creates a supervisor conflict retaining both versions. | `tests/test_f1_operations.py::test_closed_record_stale_revision_creates_one_sync_conflict`; `apps/web/e2e/roles.spec.ts::two real sessions create a persisted stale-revision conflict` |
| CP44 | IMPLEMENTED | CARGA API request for 30-day history is limited to current shift plus own-sector last 7 days. | `tests/test_cp_acceptance.py::test_cp21_cp44_cp62_backend_scope_and_own_draft_only` |
| CP45 | IMPLEMENTED | Historical record preserves exact applied limit version after a limit change; KPI is not reclassified. | `tests/test_cp_acceptance.py::test_cp45_applied_limit_version_and_historical_kpi_are_preserved` |
| CP46 | PENDING ACCEPTANCE | Person without system account remains valid historic preparer; only authenticated users perform system actions. | No focused historic-person-without-user acceptance test. |
| CP47 | PENDING ACCEPTANCE | New silo height-to-tonne scale affects new records only; old records retain applied scale. | No two-scale historical-retention acceptance test. |
| CP48 | IMPLEMENTED | Frontend-only role change cannot invoke prohibited endpoint. | `tests/test_authorization_regressions.py::test_cp48_permission_table_blocks_ungranted_protected_operations` |
| CP49 | PENDING ACCEPTANCE | Editing name/legajo of person with user updates through relation; user has no duplicate editable identity source. | No focused person/user source-of-truth acceptance test. |
| CP50 | IMPLEMENTED | `origen_dato=ia` is rejected for `reg_*`; predictions exist only in prediction tables. | `tests/test_cp_acceptance.py::test_cp50_rejects_ia_for_every_registros_path_and_has_no_prediction_surface` |
| CP51 | IMPLEMENTED | CARGA cannot edit CERRADO record even if shift closure is null. | `tests/test_f0_foundations.py::test_record_state_machine_blocks_carga_closed_edits` |
| CP52 | IMPLEMENTED | Versioned `>` operator treats equality with minimum according to configured operator. | `tests/test_f0_foundations.py::test_limit_operator_inclusivity_is_explicit` |
| CP53 | IMPLEMENTED | L42 warning without `id_desvio` warns but does not invent Dxx. | `tests/test_f3_prensas.py::test_m10_requires_full_grids_uses_format_tolerance_and_does_not_invent_dispersion_event` |
| CP54 | PENDING ACCEPTANCE | Deactivated flat catalog value is absent for new entries, retained in history, and audited without fictitious catalog version. | Deactivation/list exclusion is tested; historic retention and audit are not asserted together. |
| CP55 | IMPLEMENTED | Removing a loaded programmed shift does not remove it from compliance/hours denominator. | `tests/test_cp_acceptance.py::test_cp55_voided_operational_record_keeps_calendar_scheduled_denominator` |
| CP56 | PENDING ACCEPTANCE | Three M1 controls plus one production summary count one shift and sum tonnes/hours once. | No focused summary-plus-controls aggregation acceptance test. |
| CP57 | PENDING ACCEPTANCE | Stoppage from 23:30 to 01:15 retains start operational date, duration, and stays open across shift. | Cross-midnight duration is tested; open-across-shift state and operational-date retention are not both asserted. |
| CP58 | PENDING ACCEPTANCE | Overlapping stops use interval union for availability; Pareto retains events per rule. | No focused overlapping-stop union/Pareto acceptance test. |
| CP59 | PENDING ACCEPTANCE | Out-of-range correction remaining out-of-range updates same event/history, no duplicate. | No focused same-event correction acceptance test. |
| CP60 | PENDING ACCEPTANCE | Offline out-of-range retry creates one event through idempotency key. | Offline record retry is covered, but the out-of-range event idempotency assertion is absent. |
| CP61 | IMPLEMENTED | Verdés lab analysis stores configured determinations/meshes and traces applied limit version. | `tests/test_f7_laboratory.py::test_f7_configurable_analysis_sieves_limits_agenda_and_compliance` |
| CP62 | IMPLEMENTED | Direct API request by CARGA for another sector or more than 7-day history is rejected. | `tests/test_cp_acceptance.py::test_cp21_cp44_cp62_backend_scope_and_own_draft_only` |
| CP63 | PENDING ACCEPTANCE | Generic PUT cannot set CERRADO; explicit valid `/cerrar` command is required. | State helper covers transitions, but no API request proves arbitrary PUT cannot set CERRADO. |
| CP64 | IMPLEMENTED | Historical `/limites?fecha=` returns historical version without rewriting records/events. | `tests/test_f0_integration.py::test_limit_versions_do_not_overlap_and_historical_read_is_stable`; `tests/test_cp_acceptance.py::test_cp45_applied_limit_version_and_historical_kpi_are_preserved` |
| CP65 | PENDING ACCEPTANCE | Dashboard shows VENCIDO, ESCALADO, INVALIDADO; invalidated does not count as real deviation. | INVALIDADO/KPI exclusion is covered, but all three stated statuses are not demonstrated. |
| CP66 | PENDING ACCEPTANCE | Two M2 measurements remain separate in temporal fact; turn fact aggregates without loss of grain. | No focused dual-grain acceptance test. |
| CP67 | IMPLEMENTED | Two clients editing same draft with stale revision cause server conflict, not device-time resolution. | `tests/test_f0_foundations.py::test_stale_or_closed_sync_creates_conflict_and_retry_is_idempotent`; `apps/web/e2e/roles.spec.ts::two real sessions create a persisted stale-revision conflict` |
| CP68 | IMPLEMENTED | MUA remnants/mixing trace displays chronological sequence and POTENCIAL/INFERIDA labels, no invented percentages. | `tests/test_f4_traceability.py::test_temporal_handoffs_mapping_and_certainty_trace` |
| CP69 | PENDING ACCEPTANCE | Selecting/saving silo below 20 t gives warning plus D16/action; no V1 technical block. | Below-20 calculation is tested, but warning/D16 and non-blocking acceptance are not asserted. |
| CP70 | PENDING ACCEPTANCE | Second consecutive out-of-range event escalates internally only; in-range resets sequence. | Escalation/reset are covered; absence of external notification is not asserted. |

## Docker Playwright Scope

`apps/web/e2e/roles.spec.ts` runs only through the `e2e` Docker Compose profile with disposable PostgreSQL, migrated API, built web, synthetic users, signed login tokens, and real HTTP requests. It does not intercept, route, fulfill, or mock business API requests. Browser scenarios cover role navigation, persisted operational entries, targeted supervision/admin/remote acceptance paths, offline retries, stale revision conflict, and service-worker recovery. Industrial validations, authorization decisions, calculations, audit immutability, and historical persistence remain backend-test evidence unless a browser journey is explicitly named above.
