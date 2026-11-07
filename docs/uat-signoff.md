# UAT plan and sign-off

User acceptance testing against the [business requirements](business-requirements.md). Each case is
traced to the requirements it proves and to the automated test that repeats it on every push, so the
client can see that nothing was tested only once. `tests/test_traceability.py` fails if a requirement
has no case, or if a case names a test that does not exist.

**Pass rule:** every must-have (M) requirement has all of its cases passing. Should-have (S) cases
may be accepted with a note.

| Case | Requirements | What the tester does | Expected result | Automated test | Result |
| --- | --- | --- | --- | --- | --- |
| UAT-01 | BR-01 | Run onboarding on the sample export, which has the client's own column names | All 8 columns mapped by name; mapping saved | `test_onboarding.OnboardingSampleTests.test_every_column_is_mapped_by_name` | Pass |
| UAT-02 | BR-01 | Run with headings the tool doesn't know, then with an analyst's mapping | Not ready, naming the unmapped fields; then loads | `test_onboarding.OnboardingRuleTests.test_unknown_headings_are_left_for_the_analyst` | Pass |
| UAT-03 | BR-01 | Rerun next month's file with the saved mapping | Same mapping used without changes | `test_onboarding.OnboardingSampleTests.test_outputs_are_written_and_the_mapping_can_be_reused` | Pass |
| UAT-04 | BR-02 | Check the sample's 17 planted bad rows | All 17 rejected with line and reason; no good row rejected | `test_onboarding.OnboardingSampleTests.test_every_planted_blocking_problem_is_rejected_and_nothing_else` | Pass |
| UAT-05 | BR-02 | Check 4 returns and 3 double-exported lines | Loaded with warnings; returns become cancellation lines | `test_onboarding.OnboardingSampleTests.test_every_planted_warning_is_flagged_and_loaded` | Pass |
| UAT-06 | BR-02, BR-04 | Pass the loaded rows through the platform's cleaning step | Accepted unchanged; the 4 returns are removed as cancellations | `test_onboarding.OnboardingSampleTests.test_clean_rows_pass_the_platforms_own_cleaning_step` | Pass |
| UAT-07 | BR-03 | Decide on the sample (2.8% rejected) | Not ready; ready when the limit is 5% | `test_onboarding.OnboardingSampleTests.test_too_many_rejects_means_not_ready` | Pass |
| UAT-08 | BR-04, BR-05 | Clean a sample with a cancelled order, postage, a zero quantity and a 5,000-unit line | Cancellation and its original removed; others removed; large line flagged as bulk | `test_inventory.CleaningTests.test_removes_cancellations_their_originals_and_non_products_and_flags_bulk` | Pass |
| UAT-09 | BR-06 | Load the committed client settings | Valid; produce exactly the published results | `test_onboarding.SettingsTests.test_the_committed_settings_are_valid_and_match_the_published_defaults` | Pass |
| UAT-10 | BR-06 | Load settings with eight different mistakes | Run refused; all eight listed at once | `test_onboarding.SettingsTests.test_every_problem_is_reported_at_once` | Pass |
| UAT-11 | BR-07 | Set a 40-day lead time for one product | Only that product's reorder point changes | `test_onboarding.SettingsTests.test_a_client_lead_time_changes_that_products_policy_only` | Pass |
| UAT-12 | BR-08 | Change all 2011 demand tenfold, rebuild policies | Policies unchanged (set from 2010 only) | `test_inventory.PolicyTests.test_policy_uses_only_2010_demand` | Pass |
| UAT-13 | BR-08 | Simulate a 6-day case by hand and in code | Same stock, lost sales and order timing | `test_inventory.PolicyTests.test_simulation_serves_from_stock_loses_unmet_demand_and_receives_after_lead_time` | Pass |
| UAT-14 | BR-09 | Compare service levels 80% to 99% | Lost units fall and holding cost rises as the level rises | `test_inventory.PolicyTests.test_higher_service_level_means_more_stock_and_fewer_lost_units` | Pass |
| UAT-15 | BR-10 | Build the finance view | Working capital equals average stock value; no change at the current level | `test_onboarding.FinanceTests.test_working_capital_is_average_stock_value` | Pass |
| UAT-16 | BR-11 | Recommend at hurdles of 10%, 1% and 50% | 98%, 99% and 80% | `test_onboarding.FinanceTests.test_recommendation_respects_finances_hurdle` | Pass |
| UAT-17 | BR-10, BR-11 | Open `docs/finance-summary.md` | Recommends 98%, explains the 99% step, has sign-off lines; matches the latest run | `test_onboarding.FinanceTests.test_committed_summary_is_up_to_date` | Pass |
| UAT-18 | BR-12 | List products at or below reorder point on 9 Dec 2011 at 95% | List with on-hand, on-order and reorder point | `test_inventory.PolicyTests.test_reorder_status_lists_products_at_or_below_their_reorder_point` | Pass |
| UAT-19 | BR-13 | Run DELETE, UPDATE, PRAGMA, ATTACH and two statements | All blocked before running | `test_inventory.SqlSafetyTests.test_only_single_select_statements_pass_the_text_check` | Pass |
| UAT-20 | BR-13 | Inspect what is sent to Gemini | Schema and question only, no data values | `test_inventory.SqlSafetyTests.test_gemini_gets_schema_and_question_only` | Pass |
| UAT-21 | BR-14 | Run the go-live gate on 9 of 10 correct, 2 wrong, and no evaluation | GO; NO-GO; NOT READY | `test_pilot.GoLiveTests.test_nine_of_ten_correct_is_go` | Pass |
| UAT-22 | BR-14 | `python -m evaluation.sql_eval --gemini`, then `python -m evaluation.go_live` (run 7 Nov 2026) | Decision recorded in `evaluation/results/go-live.md` | Manual: needs a Gemini key | Pass: 9 of 10, GO |
| UAT-23 | BR-15 | Ask four pilot questions with different outcomes and ratings | Each logged; approval 75%, accuracy as rated 50% | `test_pilot.AskCommandTests.test_every_path_is_logged_with_its_outcome` | Pass |
| UAT-24 | BR-15 | Mark an answer wrong and export candidates | Draft evaluation question with the user's note | `test_pilot.PilotReportTests.test_wrong_answers_become_draft_evaluation_questions` | Pass |
| UAT-25 | BR-16 | AI summary claims "about 30%" and "roughly 25,000 units" | Rejected | `test_inventory.SummaryTests.test_ai_summary_with_invented_figures_is_rejected` | Pass |
| UAT-26 | BR-17 | Validate the Power BI project files | Every file parses and declares its Microsoft schema | `test_powerbi.PowerBIProjectTests.test_every_json_file_parses_and_declares_a_schema` | Pass |
| UAT-27 | BR-17 | Open `powerbi/RetailInventory.pbip` in Power BI Desktop | Figures match the check table in the dashboard guide | Manual: needs Power BI Desktop | Not yet run |

## Open items

- UAT-27 needs Power BI Desktop on a Windows machine.
- The settings are still modelled assumptions. Once the client confirms real unit costs and lead times,
  rerun `python -m inventory.policy` and `python -m inventory.finance`, then repeat UAT-14 to UAT-18.

## Sign-off

By signing, the client accepts that the must-have requirements are met, with the open items above.

| Role | Name | Signature | Date |
| --- | --- | --- | --- |
| Store manager (sponsor) | | | |
| Finance | | | |
| Implementation consultant | | | |
