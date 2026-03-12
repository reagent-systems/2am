FROM python:3.12-slim

WORKDIR /2am

# System deps
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI (required for claude-agent-sdk)
RUN curl -fsSL https://claude.ai/install.sh | sh 2>/dev/null || \
    pip install claude-agent-sdk --quiet

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Each agent gets its own workspace via volume mount:
#   -v $(pwd)/agents/running/<id>/workspace:/2am/agents/running/<id>/workspace
# The agent ID and task are passed as env vars
ENV AGENT_ID=agent
ENV AGENT_TASK=""
ENV ANTHROPIC_API_KEY=""

CMD ["python", "-m", "main.run", "${AGENT_TASK}"]
