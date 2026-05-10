"""Entry point for python -m traxistransfer."""

from traxistransfer import __version__


def main():
    print(f"TraxisTransfer v{__version__}")
    from traxistransfer.main import run
    run()


if __name__ == "__main__":
    main()
