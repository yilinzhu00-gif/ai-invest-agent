# Isolated backup and restore

Backups and restores must use a disposable database and object-store bucket. Record table counts, checksums, elapsed time, RPO and RTO. Do not run downgrade migrations or target production data from this repository.

Run the isolated drill with `DRILL_ENV=test ./scripts/backup-restore-drill.sh`. It creates temporary PostgreSQL and MinIO containers, uploads a PostgreSQL custom dump to an isolated bucket, downloads it, restores it into a second database, and checks the SHA-256 and row count before removing all drill resources.
