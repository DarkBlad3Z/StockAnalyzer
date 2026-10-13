# Reproduce everything from the raw pulls in data/raw.
# Requires python3 (standard library only) and, for `make test`, node.

.PHONY: all prep model build test clean

all: build

prep:
	python3 src/prep.py

model:
	python3 src/model.py

build: prep model
	python3 src/build.py

test: build
	node test/check-charts.js

clean:
	rm -f index.html data/derived/today.json data/derived/forward.json
