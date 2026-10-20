#!/usr/bin/env python3
"""Generate the dragon-and-rider model with the Meshy Text-to-3D API.

Runs the two Meshy stages (preview mesh, then refine with PBR textures),
polls until each finishes and downloads the GLB plus thumbnail to ./assets.

Usage:
    export MESHY_API_KEY=msy_...
    python3 generate_meshy.py                    # full run
    python3 generate_meshy.py --resume           # continue from assets/meshy_tasks.json
    python3 generate_meshy.py --seed 7           # different variation

The API key is read from the environment only and never written to disk.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.meshy.ai/openapi/v2/text-to-3d"
HERE = os.path.dirname(os.path.abspath(__file__))

# Meshy limits prompts to 600 characters.
PROMPT = (
    "Epic colossal fantasy dragon in powerful flight, huge bat-like wings spread "
    "wide and horizontal, torn wing membranes, armored dark crimson and obsidian "
    "scales, golden horns crowning a fierce head with open fanged jaws, spiked spine, "
    "long whipping tail. Riding on its back between the wings: Link from The Legend "
    "of Zelda, young elf hero with green tunic, long green pointed cap, blond hair, "
    "pointed ears, brown leather belts, raising the Master Sword, Hylian shield on "
    "his back. Highly detailed, heroic, cinematic masterpiece"
)

TEXTURE_PROMPT = (
    "Dark crimson dragon scales with obsidian black plates, glowing ember-orange "
    "cracks, golden horns and claws, amber eyes, leathery wing membranes in deep red "
    "with dark veins. Rider: vivid green tunic and cap, white sleeves, brown leather "
    "belts and boots, blond hair, silver sword with violet hilt, blue shield with "
    "silver rim and red bird emblem"
)


def log(msg):
    print(msg, flush=True)


def request(method, url, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")
        sys.exit(f"Meshy API {method} {url} failed with HTTP {err.code}: {detail}")


def create_task(key, body):
    task_id = request("POST", API, key, body)["result"]
    log(f"  task {task_id} created ({body['mode']})")
    return task_id


def wait_for(key, task_id, label):
    last = -1
    while True:
        task = request("GET", f"{API}/{task_id}", key)
        status, progress = task.get("status"), task.get("progress", 0)
        if progress != last:
            log(f"  {label}: {status} {progress}%")
            last = progress
        if status == "SUCCEEDED":
            return task
        if status in ("FAILED", "CANCELED", "EXPIRED"):
            message = (task.get("task_error") or {}).get("message", "no details")
            sys.exit(f"{label} task {task_id} ended with {status}: {message}")
        time.sleep(6)


def download(url, path):
    with urllib.request.urlopen(url, timeout=300) as resp, open(path, "wb") as out:
        while chunk := resp.read(1 << 16):
            out.write(chunk)
    log(f"  saved {os.path.relpath(path, HERE)} ({os.path.getsize(path) / 1e6:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.path.join(HERE, "assets"))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--polycount", type=int, default=150000)
    parser.add_argument("--resume", action="store_true",
                        help="reuse task ids stored in meshy_tasks.json")
    args = parser.parse_args()

    key = os.environ.get("MESHY_API_KEY")
    if not key:
        sys.exit("Set MESHY_API_KEY first.")
    os.makedirs(args.out, exist_ok=True)
    state_path = os.path.join(args.out, "meshy_tasks.json")
    state = {}
    if args.resume and os.path.exists(state_path):
        with open(state_path) as fh:
            state = json.load(fh)

    def save_state():
        with open(state_path, "w") as fh:
            json.dump(state, fh, indent=2)

    log("1/3 Preview mesh")
    if "preview" not in state:
        body = {
            "mode": "preview",
            "prompt": PROMPT,
            "art_style": "realistic",
            "ai_model": "latest",
            "topology": "triangle",
            "should_remesh": True,
            "target_polycount": args.polycount,
            "symmetry_mode": "auto",
        }
        if args.seed is not None:
            body["seed"] = args.seed
        state["preview"] = create_task(key, body)
        save_state()
    preview = wait_for(key, state["preview"], "preview")
    if preview.get("thumbnail_url"):
        download(preview["thumbnail_url"], os.path.join(args.out, "preview.png"))

    log("2/3 Refine with PBR textures")
    if "refine" not in state:
        state["refine"] = create_task(key, {
            "mode": "refine",
            "preview_task_id": state["preview"],
            "enable_pbr": True,
            "texture_prompt": TEXTURE_PROMPT,
            "ai_model": "latest",
        })
        save_state()
    refined = wait_for(key, state["refine"], "refine")

    log("3/3 Download")
    download(refined["model_urls"]["glb"], os.path.join(args.out, "dragon_raw.glb"))
    if refined.get("thumbnail_url"):
        download(refined["thumbnail_url"], os.path.join(args.out, "thumbnail.png"))
    meta = {k: refined.get(k) for k in ("id", "prompt", "art_style", "created_at", "finished_at")}
    with open(os.path.join(args.out, "meshy_task.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    log("Done. Next: ./optimize.sh to make the web-sized assets/dragon.glb")


if __name__ == "__main__":
    main()
