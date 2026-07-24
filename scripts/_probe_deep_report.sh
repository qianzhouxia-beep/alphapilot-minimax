#!/bin/bash
cd /home/ubuntu/alphapilot
ls -la analysis_engine.py 2>&1 | head -5
head -100 analysis_engine.py 2>&1 | head -100
echo "=== env ==="
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then echo HAS_DEEPSEEK_ENV; else echo NO_DEEPSEEK_ENV; fi
grep -n "DEEPSEEK\|OPENAI\|api.deepseek" alphapilot_pipeline_v3.py analysis_engine.py 2>/dev/null | head -20
echo "=== py packages ==="
python3 -c "import langchain; print('langchain', langchain.__version__)" 2>&1 || echo no_langchain
python3 -c "import langgraph; print('langgraph ok')" 2>&1 || echo no_langgraph
df -h /home/ubuntu | tail -1
