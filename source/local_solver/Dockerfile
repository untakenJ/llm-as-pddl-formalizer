# Pin the public Planutils base by manifest digest. Updating it is an explicit
# runtime revision, never an ambient change caused by a mutable `latest` tag.
ARG PLANUTILS_BASE=aiplanning/planutils@sha256:b6b01594520bdbfaba32121517d9ee9696a36b195c5cd3d6bbc23aaee2c82bbc
FROM ${PLANUTILS_BASE}

# The benchmark uses dual-bfws-ffparser. Keep the default image to that single
# package; lama-first remains an opt-in compatibility add-on for callers that
# need it. Both use the public worker's Planutils package mechanism.
ARG INSTALL_LAMA=0
RUN planutils install -f -y dual-bfws-ffparser \
    && if [ "${INSTALL_LAMA}" = "1" ]; then \
         planutils install -f -y lama-first; \
       fi

COPY planutils_runner.py /opt/pddl-local-solver/planutils_runner.py

LABEL org.opencontainers.image.title="llm-as-pddl-formalizer local Planutils worker"
LABEL org.opencontainers.image.source="source/local_solver"

CMD ["tail", "-f", "/dev/null"]
