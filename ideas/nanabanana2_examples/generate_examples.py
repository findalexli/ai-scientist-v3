"""
Generate concrete side-by-side examples of tool-augmented vs baseline image generation.

Demonstrates the "NanaBanana2" idea: use an LLM orchestrator with web search to enrich
prompts before sending them to an image model, vs sending raw prompts directly.

Generates images in up to 5 conditions:
  1. Direct baseline (raw prompt -> Imagen4)
  2. Tool-augmented Imagen4 (enriched prompt -> Imagen4)
  3. Direct Qwen (raw prompt -> Qwen-Image via ImageRouter)
  4. Tool-augmented Qwen (enriched prompt -> Qwen-Image via ImageRouter)
  5. NB2 native (raw prompt -> Gemini native image gen)

Usage:
  set -a && source /home/alex/ai-scientist-v3/.env && set +a
  python3 generate_examples.py [--prompts 0 1 2] [--skip-baseline] [--skip-nb2] [--skip-qwen]
"""

import os
import sys
import json
import time
import re
import requests
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types

# --- Config ---
CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
ORCHESTRATOR = "gemini-2.5-flash"
IMAGE_MODEL = "imagen-4.0-generate-001"
NB2_MODEL = "gemini-2.0-flash-exp-image-generation"
JUDGE_MODEL = "gemini-2.5-flash"

# ImageRouter for Qwen-Image
IMAGEROUTER_KEY = os.environ.get("IMAGEROUTER", "")
IMAGEROUTER_URL = "https://api.imagerouter.io/v1/openai/images/generations"
QWEN_MODEL = "qwen/qwen-image-2512"

IMAGES_DIR = Path(__file__).parent / "images"
RESULTS_FILE = Path(__file__).parent / "results.json"

# --- Prompts designed to show where tool augmentation matters most ---
EXAMPLE_PROMPTS = [
    {
        "id": "weather_tokyo",
        "category": "weather/time",
        "prompt": "A photorealistic view from a window seat on a plane landing in Tokyo right now, showing the current weather conditions and city skyline",
        "why_tools_help": "Without tools, model doesn't know current time/weather in Tokyo. With tools, it fetches live conditions.",
    },
    {
        "id": "stock_aapl",
        "category": "live_data",
        "prompt": "A stylized infographic poster showing Apple's (AAPL) current stock price, today's change, and a mini price chart",
        "why_tools_help": "Stock prices change every second. Without web search, the model hallucinates a price from training data.",
    },
    {
        "id": "sphere_vegas",
        "category": "temporal_knowledge",
        "prompt": "A photograph showing the Las Vegas Sphere venue at night with its current LED exterior display",
        "why_tools_help": "The Sphere's display changes constantly. Tool augmentation can find what's currently showing.",
    },
    {
        "id": "cybertruck",
        "category": "product_knowledge",
        "prompt": "A realistic photograph of a Tesla Cybertruck parked in front of a modern house, showing accurate design details",
        "why_tools_help": "Cybertruck's final production design differs from early prototypes in training data.",
    },
    {
        "id": "latest_iphone",
        "category": "product_knowledge",
        "prompt": "A product photograph of the latest iPhone model on a wooden desk with natural lighting, showing its exact design",
        "why_tools_help": "The latest iPhone design isn't in older training data. Tools fetch current specs.",
    },
    {
        "id": "paris_weather",
        "category": "weather/time",
        "prompt": "A cozy cafe terrace in Paris with the Eiffel Tower in the background, showing today's actual weather conditions",
        "why_tools_help": "Today's weather in Paris is specific - cloudy? rainy? sunny? Only live data tells.",
    },
    {
        "id": "breaking_news",
        "category": "live_data",
        "prompt": "A photorealistic news anchor desk with a large screen showing today's biggest global news headline",
        "why_tools_help": "News changes hourly. Without search, the model invents a plausible but fake headline.",
    },
    {
        "id": "grand_egyptian_museum",
        "category": "temporal_knowledge",
        "prompt": "A photograph of the interior of the Grand Egyptian Museum near the Pyramids of Giza, showing its main exhibition hall",
        "why_tools_help": "The GEM opened recently. Models trained before its opening don't know the interior.",
    },
]

ENRICHMENT_SYSTEM = """You are an image generation prompt enhancer with access to Google Search.
Your job: take the user's image prompt and enrich it with SPECIFIC, CURRENT, VERIFIABLE visual details.

Rules:
1. Search for current/live information mentioned in the prompt (weather, prices, events, products)
2. Add precise visual details: colors, lighting, textures, architectural features, product specs
3. Include specific numbers, names, dates where relevant
4. Keep the enriched prompt under 200 words
5. Output ONLY the enriched prompt, nothing else"""

ENRICHMENT_USER = """Original prompt: {prompt}

Search for any current/live information needed, then write an enriched, detailed image generation prompt."""

JUDGE_SYSTEM = """You are a strict image evaluator. Compare the generated image against ground truth facts.
Score on 4 dimensions (1-5 each):
1. prompt_faithfulness: Does it match the overall intent?
2. grounded_accuracy: Does it reflect SPECIFIC real-world facts (weather, prices, designs)?
3. visual_quality: Photorealism and aesthetics
4. factual_correctness: Are depicted real-world entities visually accurate?

Output ONLY valid JSON: {"prompt_faithfulness": X, "grounded_accuracy": X, "visual_quality": X, "factual_correctness": X, "reasoning": "..."}"""


def enrich_prompt(prompt: str) -> dict:
    """Enrich prompt using Gemini + Google Search."""
    resp = CLIENT.models.generate_content(
        model=ORCHESTRATOR,
        contents=ENRICHMENT_USER.format(prompt=prompt),
        config=types.GenerateContentConfig(
            system_instruction=ENRICHMENT_SYSTEM,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.7,
        ),
    )
    grounding = []
    queries = []
    if resp.candidates and resp.candidates[0].grounding_metadata:
        gm = resp.candidates[0].grounding_metadata
        if gm.grounding_chunks:
            for chunk in gm.grounding_chunks:
                if chunk.web:
                    grounding.append({"title": chunk.web.title, "uri": chunk.web.uri})
        queries = getattr(gm, 'web_search_queries', []) or []
    return {
        "enriched_prompt": resp.text.strip(),
        "grounding_sources": grounding,
        "search_queries": queries,
    }


def generate_imagen4(prompt: str) -> bytes | None:
    """Generate image using Imagen 4."""
    try:
        resp = CLIENT.models.generate_images(
            model=IMAGE_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        if resp.generated_images:
            return resp.generated_images[0].image.image_bytes
    except Exception as e:
        print(f"  [Imagen4 ERROR] {e}")
    return None


def generate_nb2(prompt: str) -> bytes | None:
    """Generate image using NanoBanana2 (Gemini native image gen)."""
    try:
        resp = CLIENT.models.generate_content(
            model=NB2_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
        for part in resp.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                return part.inline_data.data
    except Exception as e:
        print(f"  [NB2 ERROR] {e}")
    return None


def generate_qwen(prompt: str) -> bytes | None:
    """Generate image using Qwen-Image via ImageRouter API."""
    if not IMAGEROUTER_KEY:
        print("  [Qwen SKIP] IMAGEROUTER key not set")
        return None
    try:
        resp = requests.post(
            IMAGEROUTER_URL,
            headers={
                "Authorization": f"Bearer {IMAGEROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": QWEN_MODEL,
                "prompt": prompt,
                "quality": "auto",
                "size": "auto",
                "output_format": "webp",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI-compatible response: data.data[0].url or data.data[0].b64_json
        if "data" in data and len(data["data"]) > 0:
            img_data = data["data"][0]
            if "b64_json" in img_data:
                import base64
                return base64.b64decode(img_data["b64_json"])
            elif "url" in img_data:
                img_resp = requests.get(img_data["url"], timeout=60)
                img_resp.raise_for_status()
                return img_resp.content
        print(f"  [Qwen WARN] No image in response: {list(data.keys())}")
    except Exception as e:
        print(f"  [Qwen ERROR] {e}")
    return None


def judge_image(image_bytes: bytes, prompt: str, enriched_prompt: str) -> dict:
    """Judge image quality using VLM."""
    user_text = f"""Original prompt: {prompt}
Ground truth context (from web search): {enriched_prompt}
Score this image on 4 dimensions (1-5). Be strict on grounded_accuracy."""
    try:
        resp = CLIENT.models.generate_content(
            model=JUDGE_MODEL,
            contents=[
                types.Content(role="user", parts=[
                    types.Part(inline_data=types.Blob(mime_type="image/png", data=image_bytes)),
                    types.Part(text=user_text),
                ])
            ],
            config=types.GenerateContentConfig(
                system_instruction=JUDGE_SYSTEM,
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
        return json.loads(resp.text)
    except Exception as e:
        print(f"  [JUDGE ERROR] {e}")
        return {"prompt_faithfulness": -1, "grounded_accuracy": -1, "visual_quality": -1, "factual_correctness": -1, "reasoning": str(e)}


def run_single_example(idx: int, entry: dict, skip_baseline=False, skip_nb2=False, skip_qwen=False):
    """Run all conditions for one prompt and save results."""
    pid = entry["id"]
    prompt = entry["prompt"]
    n_steps = 6 - int(skip_baseline) - int(skip_nb2) - 2*int(skip_qwen)
    step = 0
    print(f"\n{'='*60}")
    print(f"[{idx+1}] {pid}: {prompt[:80]}...")
    print(f"    Why tools help: {entry['why_tools_help']}")
    print(f"{'='*60}")

    result = {
        "id": pid,
        "category": entry["category"],
        "prompt": prompt,
        "why_tools_help": entry["why_tools_help"],
        "timestamp": datetime.now().isoformat(),
        "conditions": {},
    }

    # Step 1: Enrich prompt with tools
    step += 1
    print(f"\n  [{step}/{n_steps}] Enriching prompt with Google Search...")
    enrichment = enrich_prompt(prompt)
    enriched = enrichment["enriched_prompt"]
    result["enriched_prompt"] = enriched
    result["grounding_sources"] = enrichment["grounding_sources"]
    result["search_queries"] = enrichment["search_queries"]
    print(f"    Enriched: {enriched[:120]}...")
    print(f"    Sources: {len(enrichment['grounding_sources'])} web results")
    time.sleep(2)

    # Step 2: Generate DIRECT baseline (raw prompt -> Imagen4)
    if not skip_baseline:
        step += 1
        print(f"\n  [{step}/{n_steps}] Generating DIRECT baseline (raw prompt -> Imagen4)...")
        direct_bytes = generate_imagen4(prompt)
        if direct_bytes:
            path = IMAGES_DIR / f"{pid}_direct.png"
            path.write_bytes(direct_bytes)
            scores = judge_image(direct_bytes, prompt, enriched)
            result["conditions"]["direct_imagen4"] = {
                "image_path": str(path), "scores": scores,
                "prompt_used": prompt, "model": "imagen4",
            }
            print(f"    Saved: {path.name} ({len(direct_bytes)//1024}KB)")
            print(f"    Scores: {json.dumps({k:v for k,v in scores.items() if k != 'reasoning'})}")
        else:
            result["conditions"]["direct_imagen4"] = {"error": "generation failed"}
        time.sleep(2)

    # Step 3: Generate TOOL-AUGMENTED (enriched prompt -> Imagen4)
    step += 1
    print(f"\n  [{step}/{n_steps}] Generating TOOL-AUGMENTED (enriched prompt -> Imagen4)...")
    aug_bytes = generate_imagen4(enriched)
    if aug_bytes:
        path = IMAGES_DIR / f"{pid}_tool_aug_imagen4.png"
        path.write_bytes(aug_bytes)
        scores = judge_image(aug_bytes, prompt, enriched)
        result["conditions"]["tool_aug_imagen4"] = {
            "image_path": str(path), "scores": scores,
            "prompt_used": enriched, "model": "imagen4",
        }
        print(f"    Saved: {path.name} ({len(aug_bytes)//1024}KB)")
        print(f"    Scores: {json.dumps({k:v for k,v in scores.items() if k != 'reasoning'})}")
    else:
        result["conditions"]["tool_aug_imagen4"] = {"error": "generation failed"}
    time.sleep(2)

    # Step 4: Generate DIRECT Qwen (raw prompt -> Qwen-Image)
    if not skip_qwen:
        step += 1
        print(f"\n  [{step}/{n_steps}] Generating DIRECT Qwen (raw prompt -> Qwen-Image)...")
        qwen_bytes = generate_qwen(prompt)
        if qwen_bytes:
            ext = "webp"
            path = IMAGES_DIR / f"{pid}_direct_qwen.{ext}"
            path.write_bytes(qwen_bytes)
            # Convert to PNG for judge (Gemini may not accept webp)
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(qwen_bytes))
                png_buf = io.BytesIO()
                img.save(png_buf, format="PNG")
                judge_bytes = png_buf.getvalue()
            except:
                judge_bytes = qwen_bytes
            scores = judge_image(judge_bytes, prompt, enriched)
            result["conditions"]["direct_qwen"] = {
                "image_path": str(path), "scores": scores,
                "prompt_used": prompt, "model": "qwen-image-2512",
            }
            print(f"    Saved: {path.name} ({len(qwen_bytes)//1024}KB)")
            print(f"    Scores: {json.dumps({k:v for k,v in scores.items() if k != 'reasoning'})}")
        else:
            result["conditions"]["direct_qwen"] = {"error": "generation failed"}
        time.sleep(2)

    # Step 5: Generate TOOL-AUGMENTED Qwen (enriched prompt -> Qwen-Image)
    if not skip_qwen:
        step += 1
        print(f"\n  [{step}/{n_steps}] Generating TOOL-AUGMENTED Qwen (enriched prompt -> Qwen-Image)...")
        qwen_aug_bytes = generate_qwen(enriched)
        if qwen_aug_bytes:
            ext = "webp"
            path = IMAGES_DIR / f"{pid}_tool_aug_qwen.{ext}"
            path.write_bytes(qwen_aug_bytes)
            try:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(qwen_aug_bytes))
                png_buf = io.BytesIO()
                img.save(png_buf, format="PNG")
                judge_bytes = png_buf.getvalue()
            except:
                judge_bytes = qwen_aug_bytes
            scores = judge_image(judge_bytes, prompt, enriched)
            result["conditions"]["tool_aug_qwen"] = {
                "image_path": str(path), "scores": scores,
                "prompt_used": enriched, "model": "qwen-image-2512",
            }
            print(f"    Saved: {path.name} ({len(qwen_aug_bytes)//1024}KB)")
            print(f"    Scores: {json.dumps({k:v for k,v in scores.items() if k != 'reasoning'})}")
        else:
            result["conditions"]["tool_aug_qwen"] = {"error": "generation failed"}
        time.sleep(2)

    # Step 6: Generate NB2 end-to-end (raw prompt -> NanoBanana2)
    if not skip_nb2:
        step += 1
        print(f"\n  [{step}/{n_steps}] Generating NB2 end-to-end (raw prompt -> NanoBanana2)...")
        nb2_bytes = generate_nb2(prompt)
        if nb2_bytes:
            path = IMAGES_DIR / f"{pid}_nb2.png"
            path.write_bytes(nb2_bytes)
            scores = judge_image(nb2_bytes, prompt, enriched)
            result["conditions"]["nb2_native"] = {
                "image_path": str(path), "scores": scores,
                "prompt_used": prompt, "model": "nb2",
            }
            print(f"    Saved: {path.name} ({len(nb2_bytes)//1024}KB)")
            print(f"    Scores: {json.dumps({k:v for k,v in scores.items() if k != 'reasoning'})}")
        else:
            result["conditions"]["nb2_native"] = {"error": "generation failed"}
        time.sleep(2)

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate tool-augmented image examples")
    parser.add_argument("--prompts", nargs="+", type=int, default=None,
                        help="Indices of prompts to run (0-indexed). Default: all")
    parser.add_argument("--skip-baseline", action="store_true", help="Skip direct baseline")
    parser.add_argument("--skip-nb2", action="store_true", help="Skip NB2 native generation")
    parser.add_argument("--skip-qwen", action="store_true", help="Skip Qwen-Image via ImageRouter")
    parser.add_argument("--force", action="store_true", help="Re-run even if already in results")
    args = parser.parse_args()

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    prompts = EXAMPLE_PROMPTS
    if args.prompts is not None:
        prompts = [EXAMPLE_PROMPTS[i] for i in args.prompts if i < len(EXAMPLE_PROMPTS)]

    # Load existing results if any
    all_results = []
    if RESULTS_FILE.exists():
        all_results = json.loads(RESULTS_FILE.read_text())
    existing_ids = {r["id"] for r in all_results}

    print(f"Running {len(prompts)} examples...")
    print(f"Images will be saved to: {IMAGES_DIR}")
    if IMAGEROUTER_KEY:
        print(f"ImageRouter: enabled (Qwen-Image)")
    else:
        print(f"ImageRouter: NOT SET (skipping Qwen conditions)")

    for idx, entry in enumerate(prompts):
        if entry["id"] in existing_ids and not args.force:
            print(f"\n  Skipping {entry['id']} (already in results, use --force to re-run)")
            continue
        if args.force and entry["id"] in existing_ids:
            all_results = [r for r in all_results if r["id"] != entry["id"]]
        result = run_single_example(idx, entry, args.skip_baseline, args.skip_nb2, args.skip_qwen)
        all_results.append(result)
        # Save incrementally
        RESULTS_FILE.write_text(json.dumps(all_results, indent=2, default=str))

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in all_results:
        print(f"\n{r['id']} ({r['category']}):")
        for cond, data in r.get("conditions", {}).items():
            if "scores" in data and data["scores"]:
                s = data["scores"]
                avg = sum(v for k,v in s.items() if k != "reasoning" and isinstance(v, (int,float))) / 4
                print(f"  {cond:20s}: avg={avg:.1f}  (faith={s.get('prompt_faithfulness','?')}, ground={s.get('grounded_accuracy','?')}, qual={s.get('visual_quality','?')}, fact={s.get('factual_correctness','?')})")
            elif "error" in data:
                print(f"  {cond:20s}: ERROR - {data['error']}")

    print(f"\nResults saved to: {RESULTS_FILE}")
    print(f"Images saved to: {IMAGES_DIR}")


if __name__ == "__main__":
    main()
