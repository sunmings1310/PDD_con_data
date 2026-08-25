# SKU-EVIDENCE-001 Existing Evidence Inventory

- Baseline：`main@42610e15cf683158eb2f96a3dc3d08e8b1f5e018`
- Inventory date：2026-08-25
- Result：`REAL-DEVICE GATE BLOCKED — EXPLICIT APPROVAL REQUIRED`

## 1. Accepted capabilities that can be reused

- `server/raw_capture.py` and `scripts/raw_capture_replay.py` provide immutable Raw validation, tenant/workspace identity, SHA-256 manifest verification and offline replay.
- `RawCaptureReplayTest` provides the Android Raw → `DetailReader` → `ProductQualityGate` → DTO path, but skips when `PDD_CAPTURE_DIRS` is absent.
- `SKU_PANEL` is a representable Raw source type. The Accepted default PDD path does not open the purchase panel or traverse combinations.
- Phase 1～6A strict regression, Product Golden Sample and Legacy read already have fixed entry points.

## 2. Existing evidence matrix

| Evidence | Existing coverage | Decision status |
|---|---|---|
| Normal/abnormal collection fixtures | 10 offline fixtures; abnormal pages cannot create pseudo products | Sufficient for quality baseline, not SKU reality |
| SKU combinations | Synthetic fixture has 2 rows; parser tests include two-dimensional panel text | Not real platform evidence |
| Dimensions ≥ 3 | No committed Raw Capture | `NOT_OBSERVED` |
| Disabled/unavailable option | No committed SKU_PANEL Raw sample | `NOT_OBSERVED` |
| Invalid combination | No committed SKU_PANEL Raw sample | `NOT_OBSERVED` |
| SKU image association | Golden Sample has product media, not SKU→image binding | `NOT_OBSERVED` |
| Direct platform SKU ID | Synthetic `sku-1/sku-2` only | `NOT_OBSERVED` |
| Raw identity/hash/manifest | Mechanism and synthetic tests exist | Mechanism PASS; real SKU evidence missing |
| Raw → Replay → DTO | Tool/tests exist; real `PDD_CAPTURE_DIRS` absent | Real evidence `BLOCKED` |
| Default Generic SKU runtime | Negative JVM behavior gate | Disabled / PASS |

The synthetic fixture IDs and Golden Sample combinations must not be promoted to direct platform SKU identity evidence.

## 3. Historical investigation material not in Accepted main

The historical branch `13b4301445eda9768069a807a13d9f43cedb8e8f` retains investigation-only tools and tests:

- `scripts/schema_discovery.py`
- `scripts/sku_panel_discovery.py`
- `scripts/generic_sku_validation.py`
- corresponding discovery/validation tests and Proposed ADR

They are evidence sources, not Accepted production runtime. This Task does not automatically restore or ship them.

## 4. Reusable commands

Server Raw replay:

```powershell
python scripts/raw_capture_replay.py <capture_id> `
  --root <capture-root> `
  --enterprise-id <enterprise_id> `
  --workspace-id <workspace_id> `
  --version original `
  --output <replay-output.json>
```

Android real-Raw replay:

```powershell
$env:PDD_CAPTURE_DIRS = '<capture-dir-1>;<capture-dir-2>'
$env:PDD_REPLAY_OUTPUT = '<output-json>'
cd android_collector
.\gradlew.bat testDebugUnitTest --tests com.collector.pdd.parser.RawCaptureReplayTest
```

Full regression:

```powershell
.\scripts\test-baseline.ps1 -Strict
```

Golden Sample / Legacy read:

```powershell
python scripts/product_consistency_p0.py
```

## 5. Minimum new evidence matrix

Each target must record:

```text
device_model
android_version
pdd_app_version
capture_id
platform_product_id
opened_before_hash
opened_after_hash
source_manifest_hash
dimension_count
option_count_by_dimension
disabled_options
invalid_combinations
sku_image_relation
platform_sku_id = OBSERVED / NOT_OBSERVED
replay_result
dto_result
parser_version
quality_rules_version
```

Minimum target set:

1. one product with at least three purchase dimensions;
2. one product with disabled/unavailable options and an invalid combination;
3. one product where SKU image association can be observed;
4. direct platform SKU ID evidence, or explicit `NOT_OBSERVED` for every inspected source.

## 6. Current blocker

The missing evidence requires a real Android device, a logged-in test account, selected target pages and human supervision while entering the purchase specification panel. Offline fixtures and JVM tests cannot replace this gate. Per Task Stop Condition, Control must obtain explicit Product Owner approval before those steps. Until then:

```text
SKU MODEL NEEDS MORE EVIDENCE
platform_sku_id = NOT_OBSERVED
sku_media_association = NOT_OBSERVED
disabled/unavailable semantics = NOT_OBSERVED
```
