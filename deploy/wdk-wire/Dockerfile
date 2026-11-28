FROM python:3.14-slim

ARG VEUPATHDB_PY_REF
RUN test -n "$VEUPATHDB_PY_REF" \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
        "veupathdb-py[wire] @ git+https://github.com/VEuPathDB/ai-veupathdb-client.git@${VEUPATHDB_PY_REF}"

ENV WIRE_MODE=replay
EXPOSE 8080
CMD ["sh", "-c", "exec python -m veupathdb.testing.wire serve --mode \"$WIRE_MODE\" --wire /wire/recordings --sites /wire/sites.yaml --host 0.0.0.0 --port 8080 --confdir /wire/ca ${WIRE_OAUTH_URL:+--oauth-url \"$WIRE_OAUTH_URL\"} ${WIRE_UPSTREAM:+--upstream \"$WIRE_UPSTREAM\"}"]
