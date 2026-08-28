# SKU-EVIDENCE-VALIDATION-001 Offline Excel Matrix

## Boundary

- Source：`123.xlsx`，SHA-256 `bb5f02ca3d4995619f179ae1a58ccd889c0576bbb1b27af0c73d453f365cd557`
- Sheet/range：`导入模板!A1:D6`
- 原文件未修改；隔离副本 hash 一致。
- Current server helpers：`_read_excel_rows`、header lookup、`_search_keyword`、`_result_row` empty-catalog branch。
- Current Web helpers：`normalizeExcelRows`、`prepareDraftRows`、`reviewDraft`。
- Offline catalog match 未连接 tenant catalog；`unmatched` 只是 empty-catalog branch 结果，不是实际商品资料库结论。

## Five-row state matrix

| Excel row | Certificate class | Name preservation | Required | Dedupe | Offline catalog | ProductAttribute | SKU inferred |
|---:|---|---|---|---|---|---|---|
| 2 | drug approval | leading `●` preserved | VALID | UNIQUE | NOT_EXECUTED | candidate only | No |
| 3 | drug approval | preserved | VALID | UNIQUE | NOT_EXECUTED | candidate only | No |
| 4 | medical-device registration (`湘械注准`) | preserved | VALID | UNIQUE | NOT_EXECUTED | candidate only | No |
| 5 | drug approval | preserved | VALID | UNIQUE | NOT_EXECUTED | candidate only | No |
| 6 | drug approval | preserved | VALID | UNIQUE | NOT_EXECUTED | candidate only | No |

## Literal results

```text
EXCEL_PARSE=PASS sheet=导入模板 range=A1:D6 rows=5 headers=4
MIXED_CERTIFICATE_TYPES=PASS drug=4 medical_device=1
SPECIAL_CHARACTER=PASS bullet_preserved=1
REQUIRED_COMPLETE=5/5
OFFLINE_MATCH=EMPTY_CATALOG_BRANCH_ONLY_NOT_A_LIBRARY_VERDICT
TASK_DRAFT_PIPELINE=PASS rows=5 valid=5 ready=5 duplicate=0 invalid=0
SKU_INFERENCE=PASS dimension=0 combination=0 spec=product_attribute_candidate_only
CATALOG_MATCH=NOT_EXECUTED_OFFLINE_NO_TENANT_CATALOG
```

## Finding

当前 `stableDedupKey()` 对所有四字段目标使用字面 namespace `drug`，因此 `湘械注准` 行虽然完整保留且未丢弃，其 dedup key 仍带 `|drug|`。本 Task 只记录该事实，不修改产品分类或 dedup 契约；是否需要改为通用 regulated-product identity 属于后续独立产品/契约决策。
