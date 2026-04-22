FROM python:3.11-slim

# python:3.11-slim base because metacall/core ships Python 3.9
# which is incompatible with the MCP SDK (requires 3.10+)

RUN apt-get update && apt-get install -y \
    curl \
    libatomic1 \
    gcc \
    g++ \
    make \
    cmake \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
    | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
    && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
    | tee /etc/apt/sources.list.d/ngrok.list \
    && apt-get update && apt-get install -y ngrok \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sL https://raw.githubusercontent.com/metacall/install/master/install.sh | sh

RUN pip install --no-cache-dir metacall
RUN npm install -g metacall

# Resolve MetaCall library paths at build time and write them to /etc/metacall.env
# so the runtime environment is correct regardless of where the Guix store lands
RUN METACALL_LIB_DIR=$(dirname $(find / -name "librapid_json_serial.so" 2>/dev/null | head -n1)) \
    && echo "LOADER_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "SERIAL_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "DETOUR_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "PORT_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env

RUN METACALL_CFG=$(find / -name "global.json" -path "*/configurations/*" 2>/dev/null | head -n1) \
    && echo "CONFIGURATION_PATH=${METACALL_CFG}" >> /etc/metacall.env

RUN echo 'set -a; source /etc/metacall.env; set +a' >> /etc/bash.bashrc

ENV LD_LIBRARY_PATH="/usr/local/lib:/usr/lib"
ENV PROJECT_DIR="/project"
ENV REGISTRY_PATH="/app/metacall-registry.json"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY parser.py .
COPY registry_writer.py .
COPY registry_manager.py .
COPY mcp_server.py .
COPY metacall_runner.py .
COPY startup.sh .
RUN chmod +x /app/startup.sh

EXPOSE 8000

ENTRYPOINT ["/bin/bash", "/app/startup.sh"]
