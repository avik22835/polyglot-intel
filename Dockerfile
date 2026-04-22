# MetaCall Polyglot Intelligence
# Base: python:3.11-slim — NOT metacall/core (that image uses Python 3.9,
# incompatible with the MCP SDK which requires 3.10+)
FROM python:3.11-slim

# System packages: all language runtimes + build tools MetaCall loaders need
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

# Install ngrok inside the image so no separate container is needed
RUN curl -fsSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
    | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
    && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
    | tee /etc/apt/sources.list.d/ngrok.list \
    && apt-get update && apt-get install -y ngrok \
    && rm -rf /var/lib/apt/lists/*

# Install MetaCall runtime via universal installer
RUN curl -sL https://raw.githubusercontent.com/metacall/install/master/install.sh | sh

# Install MetaCall language ports — py and node only (rb/rs loaders not in distributable)
RUN pip install --no-cache-dir metacall
RUN npm install -g metacall

# Discover the actual MetaCall library path after installation and write it to /etc/metacall.env.
# The universal installer may place libs in /usr/local/lib or /gnu/store depending on the system.
RUN METACALL_LIB_DIR=$(dirname $(find / -name "librapid_json_serial.so" 2>/dev/null | head -n1)) \
    && echo "LOADER_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "SERIAL_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "DETOUR_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "PORT_LIBRARY_PATH=${METACALL_LIB_DIR}" >> /etc/metacall.env \
    && echo "Resolved MetaCall lib dir: ${METACALL_LIB_DIR}"

RUN METACALL_CFG=$(find / -name "global.json" -path "*/configurations/*" 2>/dev/null | head -n1) \
    && echo "CONFIGURATION_PATH=${METACALL_CFG}" >> /etc/metacall.env \
    && echo "Resolved config: ${METACALL_CFG}"

# Source the resolved paths at runtime
RUN echo 'set -a; source /etc/metacall.env; set +a' >> /etc/bash.bashrc

ENV LD_LIBRARY_PATH="/usr/local/lib:/usr/lib"

# Default project and registry paths — overridden at runtime via docker run -e or compose
ENV PROJECT_DIR="/project"
ENV REGISTRY_PATH="/app/metacall-registry.json"

WORKDIR /app

# Copy requirements first for Docker layer cache — this layer only rebuilds when
# requirements.txt changes, not every time source files change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy intelligence layer source files
COPY parser.py .
COPY registry_writer.py .
COPY registry_manager.py .
COPY mcp_server.py .
COPY metacall_runner.py .
COPY startup.sh .
RUN chmod +x /app/startup.sh

# MCP server port
EXPOSE 8000
# FaaS execution engine port
EXPOSE 9000

ENTRYPOINT ["/bin/bash", "/app/startup.sh"]
