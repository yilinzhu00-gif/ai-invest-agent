import argparse
import asyncio
from pathlib import Path

from backend.app.ingestion.parser import DocumentParser, sha256_file


async def _main(path: Path) -> None:
    parsed = await DocumentParser().parse_path(path)
    print(f"sha256={sha256_file(path)} parser_version={parsed.parser_version} blocks={len(parsed.blocks)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    asyncio.run(_main(args.path))


if __name__ == "__main__":
    main()
