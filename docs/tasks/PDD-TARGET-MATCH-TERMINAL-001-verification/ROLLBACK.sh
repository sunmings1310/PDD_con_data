#!/usr/bin/env sh
set -eu
SOURCE_REPO="${1:?usage: ROLLBACK.sh SOURCE_REPO TARGET_ROOT}"
TARGET_ROOT="${2:?usage: ROLLBACK.sh SOURCE_REPO TARGET_ROOT}"
BASE="80b3435558e67850c9cba4215ca81456721ef0db"
for path in \
  android_collector/app/src/main/java/com/collector/pdd/engine/TaskEngine.kt \
  android_collector/app/src/main/java/com/collector/pdd/net/AgentCoordinator.kt \
  android_collector/app/src/main/java/com/collector/pdd/net/TaskStatusMapping.kt \
  android_collector/app/src/test/java/com/collector/pdd/engine/ProductTargetMatcherTest.kt \
  android_collector/app/src/test/java/com/collector/pdd/engine/TaskEngineCollectorLifecycleTest.kt \
  android_collector/app/src/test/java/com/collector/pdd/net/TaskStatusMappingTest.kt \
  server/job_service.py \
  tests/test_job_service.py \
  docs/backlog.md
do
  git -C "$SOURCE_REPO" show "$BASE:$path" > "$TARGET_ROOT/$path"
done
rm -f "$TARGET_ROOT/docs/tasks/PDD-TARGET-MATCH-TERMINAL-001.md"
rm -rf "$TARGET_ROOT/docs/tasks/PDD-TARGET-MATCH-TERMINAL-001-verification"
printf 'ROLLBACK_RESTORED_BASE=%s\n' "$BASE"