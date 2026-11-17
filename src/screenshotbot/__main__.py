import argparse
import json
import sys

from .collector import ANCHORS, MODES, CHANNELS, CaptureError, capture


def main():
    parser = argparse.ArgumentParser(prog="python -m screenshotbot", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    cmd = commands.add_parser("capture", allow_abbrev=False)
    cmd.add_argument("--fixture", choices=sorted(ANCHORS), required=True)
    cmd.add_argument("--mode", choices=MODES, required=True)
    cmd.add_argument("--channel", choices=CHANNELS, default="chromium")
    args = parser.parse_args()
    try:
        folder = capture(args.fixture, args.mode, channel=args.channel)
    except CaptureError as exc:
        print(json.dumps({"status": "failure", "code": exc.code, "message": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "success", "image": str(folder / "original.png"),
                      "receipt": str(folder / "receipt.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
