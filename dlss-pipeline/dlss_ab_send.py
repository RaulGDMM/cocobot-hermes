#!/usr/bin/env python3
"""Send DLSS A/B workflows through the ComfyUI broker and download outputs."""
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, "/root/.hermes/skills/media/comfyui-local/scripts")
from generate_video import request_json, download_file  # noqa: E402

BROKER = "http://172.23.176.1:8791"
OUT = Path("/root/workspace/dlss-ab")

PVSG = "openclaw-upload-9a8df35f7f85.mp4"  # perros vs gatos, first 5 s
CULL = "openclaw-upload-4aa069bcc612.mp4"  # amigos culturista, s3-s8

X = "\u00d7"  # unicode multiplication sign used by the node labels

NR_RECIPE = {
    "require_neural_upscaling": False,
    "nr_preset": "Default",
    "nr_style": "Default",
    "nr_intensity": 1.0,
    "local_tone_strength": 1.0,
    "local_structure_strength": 1.5,
    "skin_structure_strength": 2.0,
    "automatic_mask": True,
    "dlss_model_preset": "M",
    "encoding_quality": "Max",
    "video_codec": "H.264 (NVIDIA NVENC)",
    "container": "MP4",
    "rename": "Auto",
    "hdr_mode": False,
    "output_detail_strength": 1.0,
}


def upscale_wf(src, mode, prefix, suffix="_DLSS5"):
    up = {"video": ["1", 0], "upscale_mode": mode, "custom_suffix": suffix, **NR_RECIPE}
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": src}},
        "2": {"class_type": "NvidiaDLSSVideoUpscale", "inputs": up},
        "3": {"class_type": "SaveVideo", "inputs": {"video": ["2", 0], "filename_prefix": prefix, "format": "mp4", "codec": "auto"}},
    }


def fg_wf(src, prefix):
    return {
        "1": {"class_type": "LoadVideo", "inputs": {"file": src}},
        "2": {
            "class_type": "NvidiaDLSSFrameInterpolation",
            "inputs": {
                "video": ["1", 0],
                "output_fps": "60",
                "dlss_engine": "Auto",
                "encoding_quality": "Max",
                "video_codec": "H.264 (NVIDIA NVENC)",
                "container": "MP4",
                "rename": "Auto",
                "custom_suffix": "_DLSSFG",
                "hdr_mode": False,
            },
        },
        "3": {"class_type": "SaveVideo", "inputs": {"video": ["2", 0], "filename_prefix": prefix, "format": "mp4", "codec": "auto"}},
    }


JOBS = {
    # smoke
    "pvsg_nr": upscale_wf(PVSG, f"1{X} (DLAA / native)", "dlssab/pvsg_nr"),
    "cull_nr": upscale_wf(CULL, f"1{X} (DLAA / native)", "dlssab/cull_nr"),
    "pvsg_up3x": upscale_wf(PVSG, f"3{X} (Ultra Performance)", "dlssab/pvsg_up3x"),
    "cull_up3x": upscale_wf(CULL, f"3{X} (Ultra Performance)", "dlssab/cull_up3x"),
    "pvsg_fg60": fg_wf(PVSG, "dlssab/pvsg_fg60"),
    "cull_fg60": fg_wf(CULL, "dlssab/cull_fg60"),
}


def run_job(name, wf, timeout=900):
    payload = {"workflow": wf, "timeout_seconds": timeout}
    try:
        resp = request_json("POST", f"{BROKER}/v1/generate", payload=payload, timeout=timeout + 120)
    except Exception as exc:  # noqa: BLE001
        return name, {"error": str(exc)}
    (OUT / f"resp_{name}.json").write_text(json.dumps(resp, ensure_ascii=False, indent=1))
    if resp.get("status") != "ok":
        return name, {"error": json.dumps(resp)[:800]}
    results = resp.get("results") or []
    saved = []
    for res in results:
        for out in res.get("outputs") or []:
            q = urllib.parse.urlencode(
                {"type": out.get("type", "output"), "subfolder": out.get("subfolder", ""), "filename": out.get("filename", "")}
            )
            dest = OUT / ("dlss_" + name + "_" + Path(out["filename"]).name)
            try:
                download_file(f"{BROKER}/v1/file?{q}", dest, timeout=300)
                saved.append(str(dest))
            except Exception as exc:  # noqa: BLE001
                saved.append(f"DLFAIL {out.get('filename')}: {exc}")
    return name, {"saved": saved}


def main():
    names = sys.argv[1].split(",")
    timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        futs = [pool.submit(run_job, n, JOBS[n], timeout) for n in names]
        for fut in futs:
            name, info = fut.result()
            print(f"### {name}: {json.dumps(info, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    main()
