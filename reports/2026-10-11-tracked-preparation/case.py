"""Source/data-enabled preparation; scheduler boundaries remain mocked."""
import argparse
from benchmarks.thousand_items import measure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--local', action='store_true')
    parser.add_argument('--data', action='store_true')
    parser.add_argument('--profile', action='store_true')
    args = parser.parse_args()
    measure.run(argparse.Namespace(kind='flexlock-local' if args.local else 'flexlock-slurm',
        count=args.count, output=args.output, inputs=args.inputs, provenance=True,
        data=args.data, cache_search=False, record='dir', batch=16, profile=args.profile))


if __name__ == '__main__':
    main()
