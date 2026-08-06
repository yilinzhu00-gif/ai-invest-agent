#!/usr/bin/env bash
set -euo pipefail

if [ "${DRILL_ENV:-}" != "test" ]; then
  echo "refusing non-test target; set DRILL_ENV=test for the isolated drill" >&2
  exit 2
fi

drill_dir="$(mktemp -d)"
suffix="$$"
network="investment-agent-drill-$suffix"
source_db="investment-agent-drill-source-$suffix"
restore_db="investment-agent-drill-restore-$suffix"
object_store="investment-agent-drill-minio-$suffix"
trap 'docker rm -f "$source_db" "$restore_db" "$object_store" >/dev/null 2>&1 || true; docker network rm "$network" >/dev/null 2>&1 || true; rm -rf "$drill_dir"' EXIT

docker network create "$network" >/dev/null
docker run --rm -d --name "$source_db" --network "$network" \
  -e POSTGRES_USER=drill -e POSTGRES_PASSWORD=drill-password -e POSTGRES_DB=drill \
  pgvector/pgvector:pg16 >/dev/null
docker run --rm -d --name "$restore_db" --network "$network" \
  -e POSTGRES_USER=drill -e POSTGRES_PASSWORD=drill-password -e POSTGRES_DB=drill \
  pgvector/pgvector:pg16 >/dev/null
docker run --rm -d --name "$object_store" --network "$network" \
  -e MINIO_ROOT_USER=drill-access -e MINIO_ROOT_PASSWORD=drill-secret-password \
  minio/minio:RELEASE.2024-10-13T13-34-11Z server /data >/dev/null

for container in "$source_db" "$restore_db"; do
  until docker exec "$container" pg_isready -U drill -d drill >/dev/null; do sleep 1; done
done
until docker run --rm --network "$network" minio/mc alias set local "http://$object_store:9000" drill-access drill-secret-password >/dev/null 2>&1; do sleep 1; done

docker exec "$source_db" psql -U drill -d drill -c "CREATE TABLE drill_records (id integer PRIMARY KEY, payload text NOT NULL); INSERT INTO drill_records VALUES (1, 'workspace-isolated-artifact');" >/dev/null
docker exec "$source_db" pg_dump -U drill -d drill -Fc > "$drill_dir/backup.dump"
source_checksum="$(shasum -a 256 "$drill_dir/backup.dump" | awk '{print $1}')"

docker run --rm --network "$network" -v "$drill_dir:/drill" --entrypoint /bin/sh minio/mc -c "mc alias set local http://$object_store:9000 drill-access drill-secret-password && mc mb --ignore-existing local/drill-backups && mc cp /drill/backup.dump local/drill-backups/backup.dump" >/dev/null
docker run --rm --network "$network" -v "$drill_dir:/drill" --entrypoint /bin/sh minio/mc -c "mc alias set local http://$object_store:9000 drill-access drill-secret-password && mc cp local/drill-backups/backup.dump /drill/restored.dump" >/dev/null
restored_checksum="$(shasum -a 256 "$drill_dir/restored.dump" | awk '{print $1}')"
[ "$source_checksum" = "$restored_checksum" ]

docker exec -i "$restore_db" pg_restore -U drill -d drill < "$drill_dir/restored.dump"
row_count="$(docker exec "$restore_db" psql -U drill -d drill -Atc 'SELECT count(*) FROM drill_records')"
[ "$row_count" = "1" ]
printf '{"postgres_rows":%s,"object_checksum":"%s","restored_checksum":"%s"}\n' "$row_count" "$source_checksum" "$restored_checksum"
