# agent-core

Dialogue management and LLM orchestration for VoiceAgent. Owns conversation
state (`memory.py`), the LLM provider wrapper (`llm_client.py`), and
tool calling (`tools/`). Payment capture and any other PCI-scoped
interaction is deliberately kept out of the LLM's context; see
`tools/payment_capture.py` and `compliance/pci/README.md`.

## Test

```bash
python -m pytest
```
