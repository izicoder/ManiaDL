# Python → C# test porting map

Every test in the Python suite (`tests/test_*.py`, 87 tests) has a C# equivalent in
`tests/ManiaDL.Core.Tests`. The Python suite stays in the repo as the reference until
the maintainer retires it.

Run the C# suite with:

```powershell
dotnet test tests/ManiaDL.Core.Tests/ManiaDL.Core.Tests.csproj
```

## Test infrastructure

| Python (`tests/fakes.py`, fixtures) | C# (`tests/ManiaDL.Core.Tests/Support/`) |
| --- | --- |
| `FakeSession` / `FakeResponse` scripted aiohttp responses | `ScriptedHandler` + `Responses` (status, headers, JSON, raw body, `Content-Range`) |
| `tempfile.TemporaryDirectory()` per test | `TempDir` (unique folder, deleted on `Dispose`) |
| patched `time.monotonic` / `asyncio.sleep` | `ManualTimeProvider` + `TestClock.AdvanceUntilAsync`, `ImmediateTimeProvider` |
| `make_osz()` zip builder | `TestData.MakeOsz` / `WriteOsz` |
| `make_cfg()` / `make_set()` builders | `TestData.Cfg` / `AdvancedCfg` / `Set` |
| `FakeProgress` / `FakeSpinner` | real `TaskBoard`, `Action<string>` sink, `RunLog` |

## `tests/test_util.py` (17) → `UtilTests.cs`

| Python | C# |
| --- | --- |
| `test_blank_means_no_filter` | `RangeParserTests.Blank_means_no_filter` |
| `test_pair_and_operators` | `RangeParserTests.Pair_and_operators` |
| `test_int_cast` | `RangeParserTests.Int_cast` |
| `test_invalid_and_inverted` | `RangeParserTests.Invalid_and_inverted` |
| `test_blank` | `DateRangeParserTests.Blank` |
| `test_ranges_and_normalisation` | `DateRangeParserTests.Ranges_and_normalisation` |
| `test_invalid` | `DateRangeParserTests.Invalid` |
| `test_statuses` | `ParseListsTests.Statuses` |
| `test_keys` | `ParseListsTests.Keys` |
| `test_csv` | `ParseListsTests.Csv` |
| `test_plain_text_is_client_filtered` | `QueryTermTests.Plain_text_is_client_filtered` |
| `test_operator_queries_are_left_to_api` | `QueryTermTests.Operator_queries_are_left_to_api` |
| `test_direct_links_are_unique` | `MiscUtilTests.Direct_links_are_unique` |
| `test_valid_osz` | `MiscUtilTests.Valid_osz` |
| `test_retry_after` | `MiscUtilTests.Retry_after` |
| `test_free_gb_returns_number` | `MiscUtilTests.Free_gb_returns_number` |
| `test_mirror_helpers` | `MiscUtilTests.Mirror_helpers` |

## `tests/test_config.py` (9) → `ConfigTests.cs`

| Python | C# |
| --- | --- |
| `test_old_config_gets_defaults` | `CfgFromRawTests.Old_config_gets_defaults` |
| `test_advanced_config` | `CfgFromRawTests.Advanced_config` |
| `test_validation` | `CfgFromRawTests.Validation` |
| `test_partial_genre_names_resolve` | `CfgFromRawTests.Partial_genre_names_resolve` |
| `test_limits_and_clamps` | `CfgFromRawTests.Limits_and_clamps` |
| `test_migrate_fills_new_keys_only` | `MigrationTests.Migrate_fills_new_keys_only` |
| `test_migrate_is_idempotent` | `MigrationTests.Migrate_is_idempotent` |
| `test_any_allows_everything` | `StatusAllowedTests.Any_allows_everything` |
| `test_ranked_includes_approved` | `StatusAllowedTests.Ranked_includes_approved` |

## `tests/test_state.py` (8) → `StateTests.cs`

| Python | C# |
| --- | --- |
| `test_v1_is_upgraded_on_load` | `StatusMigrationTests.V1_is_upgraded_on_load` |
| `test_legacy_text_files_are_imported` | `StatusMigrationTests.Legacy_text_files_are_imported` |
| `test_stale_legacy_files_are_removed_when_status_exists` | `StatusMigrationTests.Stale_legacy_files_are_removed_when_status_exists` |
| `test_invalid_json_is_rebuilt` | `StatusMigrationTests.Invalid_json_is_rebuilt` |
| `test_success_removes_failure_and_title` | `StatusBehaviourTests.Success_removes_failure_and_title` |
| `test_prune_failed_drops_present_ids` | `StatusBehaviourTests.Prune_failed_drops_present_ids` |
| `test_batched_saves` | `StatusBehaviourTests.Batched_saves` |
| `test_scan_existing` | `StatusBehaviourTests.Scan_existing` |

## `tests/test_progress.py` (4) → `ProgressTests.cs`

| Python | C# |
| --- | --- |
| `test_tracks_tasks` | `TaskBoardTests.Tracks_tasks` |
| `test_unknown_task_is_ignored` | `TaskBoardTests.Unknown_task_is_ignored` |
| `test_reset_clears_everything` | `TaskBoardTests.Reset_clears_everything` |
| `test_status_sink_works_with_plain_fakes` | `TaskBoardTests.Status_sink_receives_search_updates` |

## `tests/test_reports.py` (4) → `ReportTests.cs`

| Python | C# |
| --- | --- |
| `test_entries_are_sorted_and_include_all_links` | `FailedEntriesTests.Entries_are_sorted_and_include_all_links` |
| `test_unknown_title` | `FailedEntriesTests.Unknown_title` |
| `test_links_text_for_clipboard` | `FailedEntriesTests.Links_text_for_clipboard` |
| `test_no_failures` | `FailedEntriesTests.No_failures` |

## `tests/test_ui.py` (6) → `UiLabelTests.cs`

| Python | C# |
| --- | --- |
| `test_range_labels` | `LabelTests.Range_labels` |
| `test_date_labels` | `LabelTests.Date_labels` |
| `test_keys_label` | `LabelTests.Keys_label` |
| `test_basic_rows_only_when_advanced_off` | `SummaryTests.Basic_rows_only_when_advanced_off` |
| `test_advanced_rows` | `SummaryTests.Advanced_rows` |
| `test_search_rows` | `SummaryTests.Search_rows` |

## `tests/test_api.py` (22) → `QueryAndQualifierTests.cs`, `SearchTests.cs`

| Python | C# |
| --- | --- |
| `test_legacy_defaults_do_not_add_filters` | `BuildQueryTests.Legacy_defaults_do_not_add_filters` |
| `test_advanced_query` | `BuildQueryTests.Advanced_query` |
| `test_minimal_query` | `BuildQueryTests.Minimal_query` |
| `test_search_params_narrows_genre_and_language` | `BuildQueryTests.Search_params_narrows_genre_and_language` |
| `test_search_params_keeps_multiple_genres_client_side` | `BuildQueryTests.Search_params_keeps_multiple_genres_client_side` |
| `test_basic_match` | `QualifierTests.Basic_match` |
| `test_status_and_favourites` | `QualifierTests.Status_and_favourites` |
| `test_keys_and_stars` | `QualifierTests.Keys_and_stars` |
| `test_text_filters` | `QualifierTests.Text_filters` |
| `test_free_query_and_exclude` | `QualifierTests.Free_query_and_exclude` |
| `test_genre_language_bpm_length_notes_plays_dates` | `QualifierTests.Genre_language_bpm_length_notes_plays_dates` |
| `test_length_applies_to_matching_diff` | `QualifierTests.Length_applies_to_matching_diff` |
| `test_nsfw_filter` | `QualifierTests.Nsfw_filter` |
| `test_genre_and_language_use_api_ids` | `QualifierTests.Genre_and_language_use_api_ids` |
| `test_unknown_genre_is_rejected_at_parse_time` | `QualifierTests.Unknown_genre_is_rejected_at_parse_time` |
| `test_paginates_and_filters` | `SearchTests.Paginates_and_filters` |
| `test_http_400_raises_search_rejected` | `SearchTests.Http_400_raises_search_rejected` |
| `test_429_waits_and_retries` | `SearchTests.Http_429_waits_and_retries` |
| `test_falls_back_when_advanced_query_is_rejected` | `SearchTests.Http_400_falls_back_to_the_minimal_query` |
| `test_second_request_waits_for_the_interval` | `SearchPacerTests.Second_request_waits_for_the_interval` |
| `test_rate_limit_stretches_then_recovers` | `SearchPacerTests.Rate_limit_stretches_then_recovers` |
| `test_genre_and_language_are_sent_as_api_params` | `SearchTests.Genre_and_language_are_sent_as_api_params` |

## `tests/test_mirrors.py` (13) → `MirrorTests.cs`

| Python | C# |
| --- | --- |
| `test_downloads_to_part_file` | `FetchTests.Downloads_to_part_file` |
| `test_resumes_with_range` | `FetchTests.Resumes_with_range` |
| `test_rate_limit_is_reported` | `FetchTests.Rate_limit_is_reported` |
| `test_mirror_miss` | `FetchTests.Mirror_miss` |
| `test_stop_aborts_transfer` | `FetchTests.Stop_aborts_transfer` |
| `test_bad_content_range_restarts` | `FetchTests.Bad_content_range_restarts` |
| `test_returns_a_ready_mirror` | `ChooseMirrorTests.Returns_a_ready_mirror` |
| `test_all_cooling_returns_wait` | `ChooseMirrorTests.All_cooling_returns_wait` |
| `test_tried_mirrors_are_skipped` | `ChooseMirrorTests.Tried_mirrors_are_skipped` |
| `test_park_host_parks_every_endpoint_on_that_host` | `ChooseMirrorTests.Park_host_parks_every_endpoint_on_that_host` |
| `test_successful_download` | `DownloadSetTests.Successful_download` |
| `test_all_mirrors_missing_marks_failure` | `DownloadSetTests.All_mirrors_missing_marks_failure` |
| `test_invalid_zip_is_rejected` | `DownloadSetTests.Invalid_zip_is_rejected` |

## `tests/test_app.py` (4) → `OrchestratorTests.cs`

| Python | C# |
| --- | --- |
| `test_full_run_downloads_and_records_status` | `OrchestratorTests.Full_run_downloads_and_records_status` |
| `test_all_mirrors_failing_keeps_links_in_memory` | `OrchestratorTests.All_mirrors_failing_keeps_links_in_memory` |
| `test_stale_link_report_is_removed` | `OrchestratorTests.Stale_link_report_is_removed` |
| `test_log_listener_receives_events` | `OrchestratorTests.Log_events_are_emitted` |

## Adaptations (not behavior changes)

- **Batched saves.** Python's test patches `SAVE_EVERY = 2` and pins `_last_save` to now.
  The C# test cannot patch constants, so it asserts the production rule instead: the first
  note saves (interval counts from process start, exactly as Python's `_last_save = 0.0`
  does), then seven notes stay in memory, and the eighth (`SaveEvery`) flushes.
- **`StatusSink`.** Python wraps `progress.update()` in a `StatusSink` object; the C# port
  passes `TaskBoard.SetMessage` as an `Action<string>` directly. The test checks the same
  contract through a captured sink.
- **Direct `search_one` 400 test.** `SearchOneAsync` is private in C#; the test drives the
  public `SearchSetsAsync` with a legacy config and three 400 responses. `SearchRejected`
  still surfaces after the fallback chain, matching Python's `SearchRejected` exception.
- **`FakeProgress` / `FakeSpinner`.** Replaced by the real `TaskBoard` and `RunLog`, which
  are cheap, thread-safe and already the production types.
- **`test_app` wiring.** Python patches module globals; the C# orchestrator takes a
  `Func<HttpMessageHandler>` so the same scripted handler is injected without patching.

## Extra C# tests (beyond the Python suite)

`ParityTests.cs` adds the C6 checks from `rewrite.md`:

- golden Python `status.json` v1/v2 and `mania_dl_config.json` round-trips (byte-level
  assertions: UTF-8 without BOM, key order, no `.tmp` left behind);
- a pre-existing valid `.osz` is recorded in `status.json` but does not bump `Stats.Ok`;
- status IDs skip sets even after the `.osz` was removed;
- `.part` leftovers are removed at run end and the folder holds only `.osz` + `status.json`;
- Stop mid-run leaves queued sets absent from `status.json`;
- concurrent stats/mirror-choice stress (200 parallel tasks, exact totals);
- host gate spacing measured from the previous request start.

`ConfigTests.MigrationTests.Save_preserves_unknown_keys_and_uses_python_names` also guards
the Python-compatible JSON key names and unknown-key preservation, which the Python suite
only checks indirectly.

## Python quirks preserved (C7)

The tests pin the quirks listed in `rewrite.md` C7: `=` in the date parser is an upper
bound, low disk fails the whole set, pre-existing valid `.osz` files do not count as
downloads, `valid_osz` only requires one `.osu` entry, speed is a whole-run average, and
`scan_existing` never writes `status.json`.

**Deliberate deviation:** failed sets are retried by ID on the next run even when the
search does not return them again (`OrchestratorTests.Previously_failed_sets_are_retried_even_when_search_omits_them`).
Python only retried them when the search returned them.
