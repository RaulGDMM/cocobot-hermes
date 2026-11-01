# Open-H3-Regenerate-2K (refiner) via broker — lessons

Pieces: LoRA C:/ComfyUI/models/loras/open_h3_regenerate_2k_comfy_swiglu_fixed.safetensors (DrakenZA, SwiGLU-fixed; unfixed conversions break), latent_upscale_models/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors, node pack Comfyui_Minimax_h3_latent_Upscaler + own node Cocobot-H3-Refine-Init (E: ComfyUI custom_nodes). Test script: /root/workspace/openh3-ab/openh3_test.py.

- Broker ComfyUI console is cp1252: any print() with emoji raises UnicodeEncodeError and KILLS the worker thread -> ComfyUI zombie, GPU idle, broker waits to timeout. Strip non-ASCII from prints of every new custom node (done for this pack, .bak-cocobot backups). Diagnose: grep UnicodeEncodeError in /mnt/e/Workspace/Hermes/comfyui-process.log; fix by taskkill the ComfyUI PID -> broker restores Strata.
- v3 io.Schema DynamicCombo inputs are sent as dotted keys ("mode.width"), else HTTP 500 on validation.
- SamplerCustomAdvanced already noises latent at sigmas[0]; pass CLEAN upscaled latent (OpenH3RefineInit sigma=0). Double noising -> unrelated hallucination.
- 5090 limits: 5 s @1080p 178 s, 5 s @2560x1440 293 s OK; 15 s @2K OOMs -> chunk 5 s.
- QA result (husky intro): big real detail gain (mic, leather), but identity drift: pink nose->black, eye duller, paw reshaped, warmer whites. Always identity-QA before using in multi-clip edits.
- Logs: /mnt/e/Workspace/Hermes/comfyui-{broker,process}.log. Never find over /mnt/c|/mnt/e; always timeout.
