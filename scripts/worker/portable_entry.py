"""PyInstaller entrypoint; uses the same protocol and executor as orion-worker."""

from orion_endpoint.portable import main

if __name__ == "__main__":
    main()
