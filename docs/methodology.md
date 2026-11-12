# Methodology

Zero-shot uses the question and schema constraints. Few-shot adds a relevant question/SQL pair. The structured CoT strategy returns only a concise plan, never hidden reasoning. The correction chain measures retries after initial generation. Agent runs are independent tool-oriented executions. External providers should record model, latency, and token metadata when available.

