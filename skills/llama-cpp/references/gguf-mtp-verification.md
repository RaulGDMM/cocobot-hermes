# GGUF MTP Verification — Session Findings (2026-04-29)

## Case: Qwen3.6-27B-UD-Q4_K_XL.gguf

### Filename suggested MTP, metadata disagreed
- **Filename**: `Qwen3.6-27B-UD-Q4_K_XL.gguf` (UD = Unified Decoder, usually means MTP variant)
- **Architecture in GGUF**: `qwen35` (NOT `qwen3` or `qwen36`)
- **MTP tensors**: **None found** — `grep -E '^mtp'` returned empty
- **Actual architecture**: Hybrid SSM-Transformer (Qwen3.5-style), with `qwen35.ssm.*` metadata
- **Served by**: llama.cpp at `http://host.docker.internal:30000/v1`
- **Throughput measured**: ~71 tok/s predicted (without MTP, SSM hybrid is fast on RTX 5090)

### How we verified (no Python dependencies needed)

```bash
# 1. Read architecture from GGUF header (first 2MB)
dd if=/mnt/e/Workspace/Openclaw/models/qwen36-27b/Qwen3.6-27B-UD-Q4_K_XL.gguf bs=1M count=2 2>/dev/null \
  | strings | grep -E '^(general\.|qwen35\.)' | head -30

# Results showed:
#   general.architecture → qwen35
#   qwen35.block_count, qwen35.ssm.conv_kernel, qwen35.ssm.state_size, etc.

# 2. Search for MTP tensors (first 3MB)
dd if=/path/to/model.gguf bs=1M count=3 2>/dev/null | strings | grep -E '^mtp'
# Result: EMPTY — no MTP tensors

# 3. Verify via llama.cpp API
curl -s http://localhost:30000/v1/models | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(json.dumps(d['data'][0].get('meta', {}), indent=2))
"
# Result: No MTP-specific metadata fields
```

### Key takeaway
The `UD` (Unified Decoder) prefix in GGUF filenames is **not authoritative**. Always verify MTP presence by:
1. Checking `general.architecture` in GGUF metadata
2. Searching for `mtp.*` tensor names
3. Reviewing llama-server startup logs for MTP messages

### Related
- See `references/speculative-decoding.md` for MTP and D-Flash documentation
- See `references/advanced-usage.md` for speculative decoding config
