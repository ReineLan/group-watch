"""Generate offline DS review statistics; never used for runtime rate limits."""
import argparse
import json
from pathlib import Path

from group_watch.ds.stats import write_stats
from group_watch.paths import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT/'logs'/'ds-requests')
    args = parser.parse_args()
    print(json.dumps(write_stats(args.root), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
