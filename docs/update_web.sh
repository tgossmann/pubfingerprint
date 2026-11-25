#!/bin/sh
# Copy the current Python code into docs/py so that the web version uses exactly the same code.
# Run from the repository root before committing: sh docs/update_web.sh
cp pubfingerprint.py publication_map.py web_adapter.py docs/py/
echo "docs/py updated"
